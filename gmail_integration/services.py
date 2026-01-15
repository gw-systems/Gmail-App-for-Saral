from typing import List, Dict, Any, Tuple, Optional
from django.db.models import Q, Count, Max, Subquery, OuterRef, QuerySet
from django.contrib.auth.models import User, AbstractBaseUser, AnonymousUser
from .models import Email, GmailToken
from .utils.gmail_auth import handle_oauth_callback
import logging

logger = logging.getLogger(__name__)

class AuthService:
    """
    Service to handle authentication logic separately from views
    """
    @staticmethod
    def handle_oauth_callback(request_uri, session_state, session_user_id, current_user):
        """
        Validate and process the OAuth callback.
        
        Args:
            request_uri: The full callback URL
            session_state: State stored in session
            session_user_id: User ID stored in session
            current_user: The currently logged in user instance
            
        Returns:
            tuple: (success, result_message_or_email)
        """
        # 1. Verify session validity
        if not session_user_id or session_user_id != current_user.id:
            logger.warning(f"Session mismatch: stored={session_user_id}, current={current_user.id}")
            return False, "Invalid session. Please try again."
        
        logger.info(f"OAuth callback processing for user: {current_user.username}")
        
        # 2. Delegate to the low-level utility to exchange code for token
        success, email_account = handle_oauth_callback(
            request_uri, 
            session_state, 
            user=current_user
        )
        
        if success:
            return True, email_account
        else:
            return False, "Authentication failed during token exchange."

class EmailService:
    @staticmethod
    def get_threads_for_user(
        user: User | AbstractBaseUser | AnonymousUser, 
        account_filter: str = 'all', 
        search_query: Optional[str] = None,
        page_number: int = 1,
        items_per_page: int = 20
    ) -> Tuple[List[Dict[str, Any]], Any, QuerySet]:
        """
        Retrieves email threads for a user, applying permissions, filters, and search.
        Returns (thread_list, page_obj, available_accounts).
        """
        from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

        # 1. Determine accessible accounts
        available_accounts: QuerySet
        if user.has_perm('gmail_integration.view_all_gmail_accounts'):
            # Authorized users see all active accounts
            available_accounts = GmailToken.objects.filter(
                is_active=True
            ).values_list('email_account', flat=True).distinct()
        else:
            # Regular users only see their own accounts
            user_tokens = GmailToken.objects.filter(
                user=user, 
                is_active=True
            )
            available_accounts = user_tokens.values_list('email_account', flat=True)

        # 2. Build base queryset
        emails = Email.objects.filter(account_email__in=available_accounts)

        # 3. Apply Account Filter (if specific account selected)
        if account_filter != 'all':
            emails = emails.filter(account_email=account_filter)

        # 4. Apply Search Query (if provided)
        if search_query:
            emails = emails.filter(
                Q(sender_contact__name__icontains=search_query) |
                Q(sender_contact__email__icontains=search_query) |
                Q(recipients__name__icontains=search_query) |
                Q(recipients__email__icontains=search_query)
            ).distinct()

        # 5. Thread Aggregation
        # Subquery to get the ID of the latest email per thread
        latest_email_subquery = emails.filter(
            thread_id=OuterRef('thread_id')
        ).order_by('-date').values('id')[:1]
        
        # Aggregate threads with message count and latest email ID
        threads_qs = emails.values('thread_id').annotate(
            message_count=Count('id'),
            latest_date=Max('date'),
            latest_email_id=Subquery(latest_email_subquery)
        ).order_by('-latest_date')

        # 6. Apply Pagination
        paginator = Paginator(threads_qs, items_per_page)
        
        try:
            page_obj = paginator.page(page_number)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)
            
        # 7. Fetch details only for the current page
        # Extract latest_email_ids from the paginated objects
        page_threads = page_obj.object_list
        latest_email_ids = [t['latest_email_id'] for t in page_threads if t['latest_email_id'] is not None]
        
        # Bulk fetch the Email objects
        latest_emails = Email.objects.in_bulk(latest_email_ids)
        
        # 8. Build Result List
        thread_list: List[Dict[str, Any]] = []
        for thread in page_threads:
            email_id = thread['latest_email_id']
            if email_id in latest_emails:
                email = latest_emails[email_id]
                thread_list.append({
                    'thread_id': thread['thread_id'],
                    'message_count': thread['message_count'],
                    'latest_email': email,
                    'latest_date': thread['latest_date'],
                    'first_subject': email.subject,
                    'latest_snippet': email.snippet,
                })
        
        
        return thread_list, page_obj, available_accounts

    @staticmethod
    def send_email(
        user: User,
        sender_email: str,
        to_email: str,
        subject: str,
        message_text: str,
        cc: str = '',
        bcc: str = ''
    ) -> bool:
        """
        Orchestrates sending an email:
        1. Authenticates
        2. Creates message
        3. Sends via Gmail API
        4. Syncs 'Sent' folder
        """
        from .utils.gmail_auth import get_gmail_service
        from .utils.gmail_api import create_message, send_email as send_gmail_api, fetch_emails

        # 1. Get service
        # Ensure the user owns this account
        if not user.has_perm('gmail_integration.view_all_gmail_accounts'):
            has_permission = GmailToken.objects.filter(user=user, email_account=sender_email, is_active=True).exists()
            if not has_permission:
                logger.warning(f"User {user.username} prevented from sending as {sender_email}")
                return False
        
        # For superusers/admins, we don't restrict to their own token - we find ANY valid token for the account
        # For regular users, strict ownership check applies
        if user.has_perm('gmail_integration.view_all_gmail_accounts'):
            service = get_gmail_service(user=None, account_email=sender_email)
        else:
            service = get_gmail_service(user=user, account_email=sender_email)
        if not service:
            logger.error(f"Could not authenticate with {sender_email}")
            return False

        # 2. Create message
        try:
            msg = create_message(sender_email, to_email, subject, message_text, cc, bcc)
            
            # 3. Send email
            sent_msg = send_gmail_api(service, 'me', msg)
            
            if sent_msg:
                # 4. Trigger sync for Sent folder
                # we don't await this, just let it run or run it here synchronously if it's fast
                # The original view ran it synchronously
                fetch_emails(service, sender_email, 'SENT', 1)
                return True
            else:
                return False
        except Exception as e:
            logger.exception(f"Error checking/sending email: {e}")
            return False
