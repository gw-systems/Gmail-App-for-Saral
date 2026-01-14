"""
Gmail API Utilities
Handles fetching, parsing, and syncing emails from Gmail
"""
import base64
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from django.utils import timezone
import logging
from .gmail_auth import get_gmail_service
from ..models import Email, SyncStatus

logger = logging.getLogger(__name__)


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
        logger.error(f"Error decoding base64: {e}")
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
        logger.error(f"Error parsing date '{date_str}': {e}")
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
        logger.error(f"Error fetching email {message_id}: {e}")
        return None


def fetch_emails(service, account_email, label='INBOX', max_results=100):
    """
    Fetch emails from Gmail using Batch API for performance
    
    Args:
        service: Authenticated Gmail service for specific account
        account_email: Gmail account email address
        label: Gmail label to fetch (INBOX, SENT, etc.)
        max_results: Maximum number of emails to fetch
        
    Returns:
        Number of emails fetched
    """
    if not service:
        logger.warning(f"No service provided for {account_email}")
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
            logger.info(f"No messages found in {label} for {account_email}")
            return 0
        
        logger.info(f"Batch fetching {len(messages)} emails from {label} for {account_email}...")
        
        # Batch processing setup
        emails_saved = 0
        
        def batch_callback(request_id, response, exception):
            nonlocal emails_saved
            if exception:
                logger.error(f"Error in batch request {request_id}: {exception}")
                return
            
            try:
                # Parse email
                email_data = parse_email_message(response)
                
                # ADD ACCOUNT EMAIL TO DATA
                email_data['account_email'] = account_email
                
                # Save to database
                email_obj, created = save_email_to_db(email_data)
                emails_saved += 1
                
                # Log occasionally to avoid spamming
                if emails_saved % 10 == 0:
                    logger.debug(f"  Processed {emails_saved} emails...")
                    
            except Exception as e:
                logger.error(f"Error processing batch email response: {e}")

        # Create batch request
        # Google API Rate Limit Fix: Split into chunks of 20
        chunk_size = 20
        total_chunks = (len(messages) + chunk_size - 1) // chunk_size
        
        for i in range(0, len(messages), chunk_size):
            chunk = messages[i:i + chunk_size]
            current_chunk = (i // chunk_size) + 1
            logger.debug(f"Processing chunk {current_chunk}/{total_chunks} ({len(chunk)} emails)...")
            
            batch = service.new_batch_http_request(callback=batch_callback)
            
            for msg in chunk:
                batch.add(service.users().messages().get(
                    userId='me', 
                    id=msg['id'], 
                    format='full'
                ))
            
            # Execute batch chunk
            try:
                batch.execute()
            except Exception as e:
                logger.error(f"Error executing batch chunk {current_chunk}: {e}")
                
        logger.info(f"Batch sync complete for {account_email} ({label}): {emails_saved} messages saved.")
        return emails_saved
        
    except Exception as e:
        logger.error(f"Error fetching emails for {account_email}: {e}")
        return 0


def sync_all_emails(max_inbox=100, max_sent=100):
    """
    Sync emails for all active Gmail accounts
    Returns dict with sync stats per account
    """
    from ..models import GmailToken
    from .gmail_auth import get_gmail_service
    
    logger.info("Starting multi-account email sync...")
    
    # Get all active tokens
    active_tokens = GmailToken.get_all_active_tokens()
    
    if not active_tokens.exists():
        logger.warning("⚠️  No active Gmail accounts found. Please connect a Gmail account first.")
        return {'total': 0, 'accounts': {}}
    
    sync_results = {}
    total_synced = 0
    
    for token in active_tokens:
        account_email = token.email_account
        logger.info(f"Syncing account: {account_email}")
        
        # Get service for this specific account
        service = get_gmail_service(account_email=account_email)
        
        if not service:
            logger.error(f"⚠️  Could not get service for {account_email}")
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
            logger.error(f"Error getting history ID for {account_email}: {e}")
        
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
        
        logger.info(f"✓ {account_email}: {inbox_count} inbox, {sent_count} sent")
    
    logger.info(f"Multi-account sync complete: {total_synced} total emails across {len(sync_results)} accounts")
    
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
    logger.info("Checking for new emails across all accounts...")
    result = sync_all_emails()
    return result['total'] > 0


def create_message(sender, to, subject, message_text, cc=None, bcc=None):
    """
    Create a message for an email.
    
    Args:
        sender: Email address of the sender.
        to: Email address of the receiver.
        subject: The subject of the email message.
        message_text: The text of the email message.
        cc: CC recipients (string)
        bcc: BCC recipients (string)

    Returns:
        An object containing a base64url encoded email object.
    """
    message = MIMEMultipart()
    message['to'] = to
    message['from'] = sender
    message['subject'] = subject
    
    if cc:
        message['cc'] = cc
    if bcc:
        message['bcc'] = bcc

    msg = MIMEText(message_text)
    message.attach(msg)

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
    return {'raw': raw_message}


def send_email(service, user_id, message):
    """
    Send an email message.

    Args:
        service: Authorized Gmail API service instance.
        user_id: User's email address. The special value "me" can be used to indicate the authenticated user.
        message: Message to be sent.

    Returns:
        Sent Message.
    """
    try:
        sent_message = service.users().messages().send(userId=user_id, body=message).execute()
        logger.info(f"Email sent. Message Id: {sent_message['id']}")
        return sent_message
    except Exception as e:
        logger.error(f"An error occurred while sending email: {e}")
        return None
