from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.db.models import Q, Count, Max
from django.contrib.auth.decorators import login_required
from .models import Email, GmailToken
from .utils.gmail_auth import initiate_oauth_flow, handle_oauth_callback, is_authenticated, get_gmail_service
import logging
from .utils.gmail_api import check_for_new_emails, create_message, send_email
from django_q.tasks import async_task
from .tasks import sync_emails_task

logger = logging.getLogger(__name__)


def home(request):
    """Home page - redirect to inbox or login"""
    if request.user.is_authenticated:
        return redirect('inbox')
    return redirect('accounts:login')


@login_required
def start_auth(request):
    """Start OAuth flow for Gmail authentication"""
    try:
        auth_url, state = initiate_oauth_flow()
        # Store state and user ID in session for verification
        request.session['oauth_state'] = state
        request.session['oauth_user_id'] = request.user.id
        return redirect(auth_url)
    except Exception as e:
        return HttpResponse(f"Error starting authentication: {e}", status=500)


@login_required
def oauth2callback(request):
    """Handle OAuth callback from Google"""
    try:
        # Get the full callback URL
        authorization_response = request.build_absolute_uri()
        state = request.session.get('oauth_state')
        user_id = request.session.get('oauth_user_id')
        
        # Verify user
        if not user_id or user_id != request.user.id:
            return HttpResponse("Invalid session. Please try again.", status=400)
        
        logger.info(f"OAuth callback started for user: {request.user.username}")
        logger.debug(f"State from session: {state}")
        
        # Handle the callback
        success, email_account = handle_oauth_callback(
            authorization_response, 
            state, 
            user=request.user
        )
        
        if success:
            # Clear state from session
            request.session.pop('oauth_state', None)
            request.session.pop('oauth_user_id', None)
            
            # Success message
            messages.success(
                request, 
                f"Successfully connected {email_account}! Your emails are being synced in the background."
            )
            
            # Start background sync
            async_task(sync_emails_task)
            
            # Redirect to profile instead of inbox
            return redirect('accounts:profile')
        else:
            error_msg = "Authentication failed. Please check the terminal for detailed error logs."
            return HttpResponse(f"""
                <h1>Authentication Failed</h1>
                <p>{error_msg}</p>
                <p>Please check the terminal/console for detailed error information.</p>
                <a href="/start-auth/">Try Again</a>
            """, status=400)
            
    except Exception as e:
        logger.exception(f"Error during OAuth callback: {e}")
        
        return HttpResponse(f"""
            <h1>Error during authentication</h1>
            <pre>{str(e)}</pre>
            <p>Check terminal for full traceback.</p>
            <a href="/start-auth/">Try Again</a>
        """, status=500)


@login_required
def inbox_view(request):
    """Display all emails (inbox + sent) grouped by thread with multi-account support"""
    from django.conf import settings
    from .models import GmailToken
    
    # Check if user is admin (using staff permission)
    is_admin = request.user.is_staff
    
    # Get selected account from query params
    selected_account = request.GET.get('account', 'all')
    
    if is_admin:
        # Admins see all active accounts
        available_accounts = GmailToken.objects.filter(
            is_active=True
        ).values_list('email_account', flat=True).distinct()
        
        # Filter emails by selected account
        if selected_account == 'all':
            all_emails = Email.objects.all().order_by('-date')
        else:
            all_emails = Email.objects.filter(
                account_email=selected_account
            ).order_by('-date')

    else:
        # Regular users only see their own accounts
        user_tokens = GmailToken.objects.filter(
            user=request.user, 
            is_active=True
        )
        available_accounts = user_tokens.values_list('email_account', flat=True)
        
        # Filter to user's accounts only
        all_emails = Email.objects.filter(
            account_email__in=available_accounts
        ).order_by('-date')
    
    # OPTIMIZED: Use database aggregation instead of in-memory grouping
    from django.db.models import Count, Max, Subquery, OuterRef
    
    # Build base queryset based on permissions
    if is_admin:
        if selected_account == 'all':
            base_emails = Email.objects.all()
        else:
            base_emails = Email.objects.filter(account_email=selected_account)
    else:
        base_emails = Email.objects.filter(account_email__in=available_accounts)
    
    # Subquery to get the ID of the latest email per thread
    latest_email_subquery = base_emails.filter(
        thread_id=OuterRef('thread_id')
    ).order_by('-date').values('id')[:1]
    
    # Aggregate threads with message count and latest email ID
    threads = base_emails.values('thread_id').annotate(
        message_count=Count('id'),
        latest_date=Max('date'),
        latest_email_id=Subquery(latest_email_subquery)
    ).order_by('-latest_date')
    
    # Fetch all latest emails in one query
    latest_email_ids = [t['latest_email_id'] for t in threads]
    latest_emails = Email.objects.in_bulk(latest_email_ids)
    
    # Build thread list
    thread_list = [
        {
            'thread_id': thread['thread_id'],
            'message_count': thread['message_count'],
            'latest_email': latest_emails[thread['latest_email_id']],
        }
        for thread in threads
    ]
    
    context = {
        'threads': thread_list,
        'page_title': 'All Mail',
        'active_page': 'inbox',
        'is_admin': is_admin,
        'available_accounts': available_accounts,
        'selected_account': selected_account,
    }
    
    return render(request, 'gmail_integration/inbox.html', context)


@login_required
def sent_view(request):
    """Redirect to inbox (all emails shown there now)"""
    return redirect('inbox')


@login_required
def thread_view(request, thread_id):
    """
    Display all emails in a thread (conversation view)
    """
    # Check authentication
    if not is_authenticated(user=request.user):
        return render(request, 'gmail_integration/auth_required.html')
    
    # Get all emails in this thread
    emails = Email.objects.filter(thread_id=thread_id).order_by('date')
    
    if not emails.exists():
        return HttpResponse("Thread not found", status=404)
    
    # Get thread metadata
    first_email = emails.first()
    
    context = {
        'emails': emails,
        'thread_id': thread_id,
        'subject': first_email.subject,
        'message_count': emails.count(),
        'active_page': 'inbox' if first_email.is_inbox else 'sent'
    }
    
    return render(request, 'gmail_integration/thread_detail.html', context)


@login_required
def search_emails(request):
    """
    Search emails by sender/recipient name or email address
    Results are grouped by thread
    """
    # Check authentication
    if not is_authenticated(user=request.user):
        return render(request, 'gmail_integration/auth_required.html')
    
    query = request.GET.get('q', '').strip()
    
    if not query:
        # No search query, redirect to inbox
        return redirect('inbox')
    
    # Search in sender, sender_name, recipient, cc, bcc
    emails = Email.objects.filter(
        Q(sender__icontains=query) |
        Q(sender_name__icontains=query) |
        Q(recipient__icontains=query) |
        Q(cc__icontains=query) |
        Q(bcc__icontains=query)
    ).distinct()
    
    # OPTIMIZED: Use database aggregation instead of in-memory grouping
    from django.db.models import Count, Max, Subquery, OuterRef
    
    # Subquery to get the ID of the latest email per thread
    latest_email_subquery = emails.filter(
        thread_id=OuterRef('thread_id')
    ).order_by('-date').values('id')[:1]
    
    # Aggregate threads with message count and latest email ID
    threads = emails.values('thread_id').annotate(
        message_count=Count('id'),
        latest_date=Max('date'),
        latest_email_id=Subquery(latest_email_subquery)
    ).order_by('-latest_date')
    
    # Fetch all latest emails in one query
    latest_email_ids = [t['latest_email_id'] for t in threads]
    latest_emails = Email.objects.in_bulk(latest_email_ids)
    
    # Build thread list
    thread_list = [
        {
            'thread_id': thread['thread_id'],
            'message_count': thread['message_count'],
            'latest_email': latest_emails[thread['latest_email_id']],
            'latest_date': thread['latest_date'],
            'first_subject': latest_emails[thread['latest_email_id']].subject,
            'latest_snippet': latest_emails[thread['latest_email_id']].snippet,
        }
        for thread in threads
    ]
    
    context = {
        'query': query,
        'threads': thread_list,
        'total_emails': emails.count(),
        'total_threads': len(thread_list),
        'page_title': f'Search: {query}',
        'active_page': 'search'
    }
    
    return render(request, 'gmail_integration/search_results.html', context)


@login_required
def email_detail_view(request, email_id):
    """Display individual email detail"""
    # Check authentication
    if not is_authenticated(user=request.user):
        return render(request, 'gmail_integration/auth_required.html')
    
    email = get_object_or_404(Email, id=email_id)
    
    context = {
        'email': email,
        'active_page': 'inbox' if email.is_inbox else 'sent'
    }
    
    return render(request, 'gmail_integration/email_detail.html', context)


@login_required
def force_sync_view(request):
    """Manually force a sync in the background"""
    async_task(sync_emails_task)
    messages.success(request, "Gmail sync started in the background.")
    return redirect('inbox')


@login_required
def compose_email_view(request):
    """
    Handle composing and sending emails.
    Admin can send from any account.
    """
    # Get authorized accounts
    if request.user.is_superuser:
        # Admin can see all active tokens
        authorized_accounts = GmailToken.objects.filter(is_active=True)
    else:
        # Regular user only sees their own
        authorized_accounts = GmailToken.objects.filter(user=request.user, is_active=True)
    
    if not authorized_accounts.exists():
        messages.warning(request, "Please connect a Gmail account before composing an email.")
        return redirect('home')

    if request.method == 'POST':
        sender_email = request.POST.get('from_account')
        to_email = request.POST.get('to')
        subject = request.POST.get('subject')
        message_text = request.POST.get('message')
        cc = request.POST.get('cc', '')
        bcc = request.POST.get('bcc', '')

        if not all([sender_email, to_email, subject, message_text]):
            messages.error(request, "Please fill in all required fields.")
        else:
            # Get service for the selected sender account
            service = get_gmail_service(account_email=sender_email)
            if service:
                # Create and send message
                msg = create_message(sender_email, to_email, subject, message_text, cc, bcc)
                sent_msg = send_email(service, 'me', msg)
                
                if sent_msg:
                    messages.success(request, f"Email sent successfully from {sender_email}!")
                    # Trigger a sync for the sent folder to show the email in the app
                    from .utils.gmail_api import fetch_emails
                    fetch_emails(service, sender_email, 'SENT', 1)
                    return redirect('inbox')
                else:
                    messages.error(request, "Failed to send email. Please check your connection and try again.")
            else:
                messages.error(request, f"Could not authenticate with {sender_email}.")

    context = {
        'authorized_accounts': authorized_accounts,
        'title': 'Compose Email'
    }
    return render(request, 'gmail_integration/compose_email.html', context)
