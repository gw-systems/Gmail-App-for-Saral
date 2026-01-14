from django.db.models import Q, Count, Max, Subquery, OuterRef
from .models import Email, GmailToken

class EmailService:
    @staticmethod
    def get_threads_for_user(user, account_filter='all', search_query=None):
        """
        Retrieves email threads for a user, applying permissions, filters, and search.
        Returns a list of dictionaries representing threads.
        """
        # 1. Determine accessible accounts
        if user.is_staff:
            # Admins see all active accounts
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
                Q(sender__icontains=search_query) |
                Q(sender_name__icontains=search_query) |
                Q(recipient__icontains=search_query) |
                Q(cc__icontains=search_query) |
                Q(bcc__icontains=search_query)
            ).distinct()

        # 5. Thread Aggregation
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
        latest_email_ids = [t['latest_email_id'] for t in threads if t['latest_email_id'] is not None]
        latest_emails = Email.objects.in_bulk(latest_email_ids)
        
        # 6. Build Result List
        thread_list = []
        for thread in threads:
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
        
        return thread_list, available_accounts
