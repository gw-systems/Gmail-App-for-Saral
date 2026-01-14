from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.db.models import Q, Count, Max
from django.contrib.auth.decorators import login_required
from .models import Email
from .utils.gmail_auth import initiate_oauth_flow, handle_oauth_callback, is_authenticated
from .utils.gmail_api import check_for_new_emails, sync_all_emails


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
        
        print(f"\n{'='*60}")
        print(f"[OAUTH CALLBACK] Starting...")
        print(f"[OAUTH CALLBACK] User: {request.user.username}")
        print(f"[OAUTH CALLBACK] Full URL: {authorization_response}")
        print(f"[OAUTH CALLBACK] State from session: {state}")
        print(f"{'='*60}\n")
        
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
                f"Successfully connected {email_account}! Your emails will sync shortly."
            )
            
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
        import traceback
        error_trace = traceback.format_exc()
        print(f"\n[OAUTH CALLBACK ERROR] {str(e)}")
        print(f"[OAUTH CALLBACK ERROR] Traceback:\n{error_trace}\n")
        
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
    
    # Check if user is admin
    is_admin = request.user.email in settings.ADMIN_EMAILS
    
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
    
    # Group by thread - show only latest email per thread
    threads = {}
    for email in all_emails:
        if email.thread_id not in threads:
            threads[email.thread_id] = {
                'latest_email': email,
                'message_count': 1,
                'thread_id': email.thread_id,
            }
        else:
            threads[email.thread_id]['message_count'] += 1
            # Update to latest email if this one is newer
            if email.date > threads[email.thread_id]['latest_email'].date:
                threads[email.thread_id]['latest_email'] = email
    
    # Convert to list and sort by date
    thread_list = sorted(
        threads.values(),
        key=lambda x: x['latest_email'].date,
        reverse=True
    )
    
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
    if not is_authenticated():
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
    if not is_authenticated():
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
    ).distinct().order_by('-date')
    
    # Group by thread_id
    threads = {}
    for email in emails:
        if email.thread_id not in threads:
            threads[email.thread_id] = {
                'thread_id': email.thread_id,
                'emails': [],
                'message_count': 0,
                'participants': set(),
                'latest_date': email.date,
                'first_subject': email.subject,
                'latest_snippet': email.snippet,
            }
        
        thread = threads[email.thread_id]
        thread['emails'].append(email)
        thread['message_count'] += 1
        
        # Collect unique participants
        if email.sender:
            thread['participants'].add(email.sender)
        if email.recipient:
            for rec in email.recipient.split(','):
                thread['participants'].add(rec.strip())
        
        # Update latest date if this email is newer
        if email.date > thread['latest_date']:
            thread['latest_date'] = email.date
            thread['latest_snippet'] = email.snippet
    
    # Convert to list and sort by latest date
    thread_list = sorted(
        threads.values(),
        key=lambda x: x['latest_date'],
        reverse=True
    )
    
    context = {
        'query': query,
        'threads': thread_list,
        'total_emails': len(emails),
        'total_threads': len(thread_list),
        'page_title': f'Search: {query}',
        'active_page': 'search'
    }
    
    return render(request, 'gmail_integration/search_results.html', context)


@login_required
def email_detail_view(request, email_id):
    """Display individual email detail"""
    # Check authentication
    if not is_authenticated():
        return render(request, 'gmail_integration/auth_required.html')
    
    email = get_object_or_404(Email, id=email_id)
    
    context = {
        'email': email,
        'active_page': 'inbox' if email.is_inbox else 'sent'
    }
    
    return render(request, 'gmail_integration/email_detail.html', context)


@login_required
def force_sync_view(request):
    """Manually force a full sync (useful for testing)"""
    if not is_authenticated():
        return redirect('start_auth')
    
    sync_all_emails()
    messages.success(request, "Email sync completed!")
    
    return redirect('inbox')
