"""
Gmail API Utilities
Handles fetching, parsing, and syncing emails from Gmail
"""
import base64
import email
from email.mime.text import MIMEText
from datetime import datetime
from django.utils import timezone
from .gmail_auth import get_gmail_service
from ..models import Email, SyncStatus


def parse_email_headers(headers):
    """Extract common headers from email"""
    header_dict = {}
    for header in headers:
        name = header.get('name', '').lower()
        value = header.get('value', '')
        header_dict[name] = value
    return header_dict


def extract_email_and_name(email_str):
    """
    Extract email address and name from format: 'Name <email@example.com>'
    Returns: (email, name)
    """
    if not email_str:
        return '', ''
    
    import re
    # Pattern: Name <email@example.com>
    match = re.match(r'(.+?)\s*<(.+?)>', email_str)
    if match:
        name = match.group(1).strip().strip('"')  # Remove quotes if present
        email_addr = match.group(2).strip()
        return email_addr, name
    else:
        # Just an email address
        return email_str.strip(), ''


def parse_recipients(recipient_str):
    """
    Parse comma-separated recipients into a clean string
    Handles: 'email1, Name <email2>, email3'
    Returns: comma-separated email addresses
    """
    if not recipient_str:
        return ''
    
    recipients = []
    # Split by comma
    for part in recipient_str.split(','):
        email_addr, _ = extract_email_and_name(part.strip())
        if email_addr:
            recipients.append(email_addr)
    
    return ', '.join(recipients)


def decode_base64(data):
    """Decode base64 URL-safe string"""
    try:
        # Add padding if needed
        missing_padding = len(data) % 4
        if missing_padding:
            data += '=' * (4 - missing_padding)
        return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Error decoding base64: {e}")
        return ""


def parse_email_body(payload):
    """Extract email body from payload"""
    body_text = ""
    body_html = ""
    
    if 'body' in payload and 'data' in payload['body']:
        # Simple body
        decoded = decode_base64(payload['body']['data'])
        if payload.get('mimeType') == 'text/html':
            body_html = decoded
        else:
            body_text = decoded
    
    # Check for parts (multipart emails)
    if 'parts' in payload:
        for part in payload['parts']:
            mime_type = part.get('mimeType', '')
            
            if mime_type == 'text/plain' and 'data' in part.get('body', {}):
                body_text = decode_base64(part['body']['data'])
            elif mime_type == 'text/html' and 'data' in part.get('body', {}):
                body_html = decode_base64(part['body']['data'])
            elif 'parts' in part:
                # Recursive for nested parts
                nested_text, nested_html = parse_email_body(part)
                if not body_text:
                    body_text = nested_text
                if not body_html:
                    body_html = nested_html
    
    return body_text, body_html


def parse_email_message(message_data):
    """
    Parse Gmail API message response into structured data
    """
    message_id = message_data['id']
    thread_id = message_data['threadId']
    snippet = message_data.get('snippet', '')
    
    payload = message_data.get('payload', {})
    headers = parse_email_headers(payload.get('headers', []))
    
    # Extract headers
    subject = headers.get('subject', '(No Subject)')
    sender_raw = headers.get('from', '')
    recipient_raw = headers.get('to', '')
    cc_raw = headers.get('cc', '')
    bcc_raw = headers.get('bcc', '')
    date_str = headers.get('date', '')
    
    # Parse sender (extract email and name)
    sender, sender_name = extract_email_and_name(sender_raw)
    
    # Parse recipients (just extract emails)
    recipient = parse_recipients(recipient_raw)
    cc = parse_recipients(cc_raw)
    bcc = parse_recipients(bcc_raw)
    
    # Parse date
    try:
        # Gmail provides date in RFC 2822 format
        from email.utils import parsedate_to_datetime
        email_date = parsedate_to_datetime(date_str)
        # Make timezone-aware
        if email_date.tzinfo is None:
            email_date = timezone.make_aware(email_date)
    except Exception as e:
        print(f"Error parsing date '{date_str}': {e}")
        email_date = timezone.now()
    
    # Parse body
    body_text, body_html = parse_email_body(payload)
    
    # Get labels
    labels = message_data.get('labelIds', [])
    
    # Check if read
    is_read = 'UNREAD' not in labels
    
    # Check for attachments
    has_attachments = any(
        part.get('filename') 
        for part in payload.get('parts', []) 
        if part.get('filename')
    )
    
    return {
        'gmail_id': message_id,
        'thread_id': thread_id,
        'subject': subject,
        'sender': sender,
        'sender_name': sender_name,
        'recipient': recipient,
        'cc': cc,
        'bcc': bcc,
        'date': email_date,
        'snippet': snippet,
        'body_text': body_text,
        'body_html': body_html,
        'labels': labels,
        'is_read': is_read,
        'has_attachments': has_attachments,
    }


def save_email_to_db(email_data):
    """
    Save or update email in database
    Returns the Email object
    """
    email_obj, created = Email.objects.update_or_create(
        gmail_id=email_data['gmail_id'],
        defaults=email_data
    )
    return email_obj, created


def fetch_email_detail(service, message_id):
    """
    Fetch full email details from Gmail API
    """
    try:
        message = service.users().messages().get(
            userId='me',
            id=message_id,
            format='full'
        ).execute()
        return message
    except Exception as e:
        print(f"Error fetching email {message_id}: {e}")
        return None


def fetch_emails(service, account_email, label='INBOX', max_results=100):
    """
    Fetch emails from Gmail and save to database with account tracking
    
    Args:
        service: Authenticated Gmail service for specific account
        account_email: Gmail account email address
        label: Gmail label to fetch (INBOX, SENT, etc.)
        max_results: Maximum number of emails to fetch
        
    Returns:
        Number of emails fetched
    """
    if not service:
        print(f"No service provided for {account_email}")
        return 0
    
    try:
        # List messages
        results = service.users().messages().list(
            userId='me',
            labelIds=[label],
            maxResults=max_results
        ).execute()
        
        messages = results.get('messages', [])
        
        if not messages:
            print(f"No messages found in {label} for {account_email}")
            return 0
        
        print(f"Fetching {len(messages)} emails from {label} for {account_email}...")
        
        emails_saved = 0
        for msg in messages:
            # Fetch full message details
            message_data = fetch_email_detail(service, msg['id'])
            
            if message_data:
                # Parse email
                email_data = parse_email_message(message_data)
                
                # ADD ACCOUNT EMAIL TO DATA
                email_data['account_email'] = account_email
                
                # Save to database
                email_obj, created = save_email_to_db(email_data)
                emails_saved += 1
                
                if created:
                    print(f"  ✓ Saved: {email_data['subject'][:50]}")
                else:
                    print(f"  ↻ Updated: {email_data['subject'][:50]}")
        
        return emails_saved
        
    except Exception as e:
        print(f"Error fetching emails for {account_email}: {e}")
        return 0


def sync_all_emails(max_inbox=100, max_sent=100):
    """
    Sync emails for all active Gmail accounts
    Returns dict with sync stats per account
    """
    from ..models import GmailToken
    from .gmail_auth import get_gmail_service
    
    print("Starting multi-account email sync...")
    
    # Get all active tokens
    active_tokens = GmailToken.get_all_active_tokens()
    
    if not active_tokens.exists():
        print("⚠️  No active Gmail accounts found. Please connect a Gmail account first.")
        return {'total': 0, 'accounts': {}}
    
    sync_results = {}
    total_synced = 0
    
    for token in active_tokens:
        account_email = token.email_account
        print(f"\n{'='*60}")
        print(f"Syncing account: {account_email}")
        print(f"{'='*60}")
        
        # Get service for this specific account
        service = get_gmail_service(account_email=account_email)
        
        if not service:
            print(f"⚠️  Could not get service for {account_email}")
            sync_results[account_email] = {'inbox': 0, 'sent': 0, 'total': 0, 'error': 'Service unavailable'}
            continue
        
        # Sync inbox and sent for this account
        inbox_count = fetch_emails(service, account_email, 'INBOX', max_inbox)
        sent_count = fetch_emails(service, account_email, 'SENT', max_sent)
        
        account_total = inbox_count + sent_count
        total_synced += account_total
        
        # Get history ID for this account
        history_id = ''
        try:
            profile = service.users().getProfile(userId='me').execute()
            history_id = profile.get('historyId', '')
        except Exception as e:
            print(f"Error getting history ID for {account_email}: {e}")
        
        # Create sync record for this account
        SyncStatus.create_sync_record(
            status='success',
            history_id=history_id,
            emails_synced=account_total,
            account_email=account_email
        )
        
        sync_results[account_email] = {
            'inbox': inbox_count,
            'sent': sent_count,
            'total': account_total,
            'history_id': history_id
        }
        
        print(f"✓ {account_email}: {inbox_count} inbox, {sent_count} sent")
    
    print(f"\n{'='*60}")
    print(f"✓ Multi-account sync complete: {total_synced} total emails across {len(sync_results)} accounts")
    print(f"{'='*60}\n")
    
    return {
        'total': total_synced,
        'accounts': sync_results
    }


def check_for_new_emails():
    """
    Check and sync all active accounts
    Simplified version - just triggers full sync for all accounts
    Returns True if sync was performed
    """
    print("Checking for new emails across all accounts...")
    result = sync_all_emails()
    return result['total'] > 0
