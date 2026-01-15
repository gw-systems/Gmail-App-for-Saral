from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, HttpRequest
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import Email, GmailToken
from .utils.gmail_auth import initiate_oauth_flow, handle_oauth_callback, is_authenticated, get_gmail_service
import logging
from .utils.gmail_api import check_for_new_emails, create_message, send_email
from django_q.tasks import async_task
from .tasks import sync_emails_task


from .services import AuthService, EmailService
 
logger = logging.getLogger(__name__)



def home(request: HttpRequest) -> HttpResponse:
    """Home page - redirect to inbox or login"""
    if request.user.is_authenticated:
        return redirect('inbox')
    return redirect('accounts:login')


@login_required
def start_auth(request: HttpRequest) -> HttpResponse:
    """Start OAuth flow for Gmail authentication"""
    try:
        auth_url, state = initiate_oauth_flow()
        # Store state and user ID in session for verification
        request.session['oauth_state'] = state
        request.session['oauth_user_id'] = request.user.id
        return redirect(auth_url)
    except Exception as e:
        logger.exception(f"Error starting authentication: {e}")
        return render(request, 'gmail_integration/oauth_error.html', {
            'error_message': "Could not start authentication process. Please check configuration."
        }, status=500)


@login_required
def oauth2callback(request: HttpRequest) -> HttpResponse:
    """Handle OAuth callback from Google"""
    try:
        # Delegate business logic to service
        success, result = AuthService.handle_oauth_callback(
            request_uri=request.build_absolute_uri(),
            session_state=request.session.get('oauth_state'),
            session_user_id=request.session.get('oauth_user_id'),
            current_user=request.user
        )
        
        # Cleanup session regardless of outcome to prevent stale state
        request.session.pop('oauth_state', None)
        request.session.pop('oauth_user_id', None)
        
        if success:
            # Result is the email account name
            messages.success(
                request, 
                f"Successfully connected {result}! Your emails are being synced in the background."
            )
            async_task(sync_emails_task)
            return redirect('accounts:profile')
        else:
            # Result is the error message
            logger.error(f"OAuth failed: {result}")
            return render(request, 'gmail_integration/oauth_error.html', {
                'error_message': result
            }, status=400)
            
    except Exception as e:
        logger.exception(f"Unexpected error during OAuth callback: {e}")
        return render(request, 'gmail_integration/oauth_error.html', {
            'error_message': "An unexpected system error occurred. Please contact support."
        }, status=500)


@login_required
def inbox_view(request: HttpRequest) -> HttpResponse:
    """Display all emails (inbox + sent) grouped by thread with multi-account support"""
    
    # Check if user is admin (using staff permission)
    is_admin = request.user.is_staff
    
    # Get selected account from query params
    selected_account = request.GET.get('account', 'all')
    
    # Get threads using service
    thread_list, available_accounts = EmailService.get_threads_for_user(
        request.user, 
        account_filter=selected_account
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
def sent_view(request: HttpRequest) -> HttpResponse:
    """Redirect to inbox (all emails shown there now)"""
    return redirect('inbox')


@login_required
def thread_view(request: HttpRequest, thread_id: str) -> HttpResponse:
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
    
    # Add unique attachments to each email to avoid duplicates in template
    for email in emails:
        # Get unique attachments by filename
        seen_filenames = set()
        unique_attachments = []
        for att in email.attachments.all():
            if att.filename not in seen_filenames:
                unique_attachments.append(att)
                seen_filenames.add(att.filename)
        email.unique_attachments = unique_attachments
    
    context = {
        'emails': emails,
        'thread_id': thread_id,
        'subject': first_email.subject,
        'message_count': emails.count(),
        'active_page': 'inbox' if first_email.is_inbox else 'sent'
    }
    
    return render(request, 'gmail_integration/thread_detail.html', context)


@login_required
def search_emails(request: HttpRequest) -> HttpResponse:
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
    
    # Get threads using service with search query
    thread_list, _ = EmailService.get_threads_for_user(
        request.user, 
        search_query=query
    )
    
    context = {
        'query': query,
        'threads': thread_list,
        # 'total_emails' was redundant/unused in previous logic's context for display, 
        # but we can get it from thread_list length or similar if needed. 
        # For now, sticking to providing threads.
        'total_threads': len(thread_list),
        'page_title': f'Search: {query}',
        'active_page': 'search'
    }
    
    return render(request, 'gmail_integration/search_results.html', context)


@login_required
def email_detail_view(request: HttpRequest, email_id: int) -> HttpResponse:
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
def force_sync_view(request: HttpRequest) -> HttpResponse:
    """Manually force a sync in the background"""
    async_task(sync_emails_task)
    messages.success(request, "Gmail sync started in the background.")
    return redirect('inbox')


@login_required
def compose_email_view(request: HttpRequest) -> HttpResponse:
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
            success = EmailService.send_email(
                user=request.user,
                sender_email=sender_email,
                to_email=to_email,
                subject=subject,
                message_text=message_text,
                cc=cc,
                bcc=bcc
            )
            
            if success:
                messages.success(request, f"Email sent successfully from {sender_email}!")
                return redirect('inbox')
            else:
                messages.error(request, "Failed to send email. Please check logs/connection.")

    context = {
        'authorized_accounts': authorized_accounts,
        'title': 'Compose Email'
    }
    return render(request, 'gmail_integration/compose_email.html', context)


@login_required
def download_attachment(request: HttpRequest, attachment_id: int) -> HttpResponse:
    """
    Download email attachment with permission check
    """
    from .models import Attachment, GmailToken
    from django.http import FileResponse, Http404
    
    # Get attachment
    try:
        attachment = Attachment.objects.select_related('email').get(id=attachment_id)
    except Attachment.DoesNotExist:
        raise Http404("Attachment not found")
    
    # Permission check: user must have access to the email's account
    email = attachment.email
    account_email = email.account_email
    
    # Check if user has access to this account
    if not request.user.is_staff:
        # Regular users can only access their own accounts
        has_access = GmailToken.objects.filter(
            user=request.user,
            email_account=account_email,
            is_active=True
        ).exists()
        
        if not has_access:
            return HttpResponse("Permission denied", status=403)
    
    # Serve file
    try:
        response = FileResponse(attachment.file.open('rb'), content_type=attachment.mime_type)
        response['Content-Disposition'] = f'attachment; filename="{attachment.filename}"'
        logger.info(f"User {request.user.username} downloaded attachment: {attachment.filename}")
        return response
    except Exception as e:
        logger.error(f"Error serving attachment {attachment_id}: {e}")
        raise Http404("File not found")

