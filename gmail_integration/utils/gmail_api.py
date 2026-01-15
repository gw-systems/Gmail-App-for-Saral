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
import bleach

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
    
    # Sanitize HTML to prevent XSS
    if body_html:
        try:
            allowed_tags = [
                'a', 'abbr', 'acronym', 'b', 'blockquote', 'br', 'code', 'div',
                'em', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'i', 'img',
                'li', 'ol', 'p', 'pre', 'span', 'strong', 'table', 'tbody',
                'td', 'th', 'thead', 'tr', 'ul', 'u'
            ]
            allowed_attrs = {
                '*': ['class', 'style', 'title'],
                'a': ['href', 'target', 'rel'],
                'img': ['src', 'alt', 'width', 'height', 'style'],
                'table': ['border', 'cellpadding', 'cellspacing', 'style'],
                'td': ['colspan', 'rowspan', 'style'],
                'th': ['colspan', 'rowspan', 'style'],
                'div': ['style'],
                'span': ['style'],
                'p': ['style'],
            }
            # Cleaning the HTML
            # Note: For full CSS sanitization we would need more complex logic,
            # but this prevents script injection.
            body_html = bleach.clean(
                body_html, 
                tags=allowed_tags, 
                attributes=allowed_attrs, 
                strip=True
            )
        except Exception as e:
            logger.error(f"Error sanitizing HTML for email {message_id}: {e}")
            # Fallback: escape everything if sanitization fails
            body_html = bleach.clean(body_html, tags=[], strip=True)

    # Extract attachment metadata
    attachments_metadata = extract_attachment_metadata(payload)

    return {
        'gmail_id': message_id,
        'thread_id': thread_id,
        'subject': subject,
        'sender_email': sender,
        'sender_name': sender_name,
        'recipient_list': [e.strip() for e in recipient.split(',') if e.strip()],
        'cc_list': [e.strip() for e in cc.split(',') if e.strip()],
        'bcc_list': [e.strip() for e in bcc.split(',') if e.strip()],
        'date': email_date,
        'snippet': snippet,
        'body_text': body_text,
        'body_html': body_html,
        'labels': labels,
        'is_read': is_read,
        'has_attachments': has_attachments,
        'attachments_metadata': attachments_metadata,
    }


def extract_attachment_metadata(payload):
    """
    Extract attachment metadata from email payload
    Returns list of dicts with attachment info
    """
    attachments = []
    
    def process_parts(parts):
        for part in parts:
            # Check if part has filename (is an attachment)
            filename = part.get('filename', '')
            if filename and 'body' in part:
                attachment_id = part['body'].get('attachmentId')
                if attachment_id:
                    attachments.append({
                        'attachment_id': attachment_id,
                        'filename': filename,
                        'mime_type': part.get('mimeType', 'application/octet-stream'),
                        'size': part['body'].get('size', 0)
                    })
            
            # Recursively process nested parts
            if 'parts' in part:
                process_parts(part['parts'])
    
    if 'parts' in payload:
        process_parts(payload['parts'])
    
    return attachments


def download_attachment(service, message_id, attachment_id):
    """
    Download attachment from Gmail API
    Returns attachment data as bytes
    """
    try:
        attachment = service.users().messages().attachments().get(
            userId='me',
            messageId=message_id,
            id=attachment_id
        ).execute()
        
        # Decode base64 data
        data = attachment['data']
        file_data = base64.urlsafe_b64decode(data)
        return file_data
    except Exception as e:
        logger.error(f"Error downloading attachment {attachment_id}: {e}")
        return None


def get_or_create_contact(email_addr, name=''):
    """Helper to get or create a contact"""
    if not email_addr:
        return None
    
    from ..models import Contact
    contact, created = Contact.objects.get_or_create(
        email=email_addr,
        defaults={'name': name}
    )
    # Update name if we have a new one and the old one was empty
    if not created and name and not contact.name:
        contact.name = name
        contact.save()
    return contact


def save_email_to_db(email_data, service=None):
    """
    Save or update email in database
    Returns the Email object
    
    Args:
        email_data: Parsed email data dict
        service: Gmail API service (needed for downloading attachments)
    """
    # 1. Handle Sender Contact
    sender_email = email_data.get('sender_email', '')
    sender_name = email_data.get('sender_name', '')
    sender_contact = get_or_create_contact(sender_email, sender_name)
    
    # NEW: Link to GmailToken FK
    from ..models import GmailToken
    account_email_str = email_data.get('account_email')
    account_token = GmailToken.objects.filter(email_account=account_email_str).first()

    # Add to defaults/data
    # Note: we filter defaults to only include model fields
    defaults = {
        'subject': email_data['subject'],
        'date': email_data['date'],
        'snippet': email_data['snippet'],
        'body_text': email_data['body_text'],
        'body_html': email_data['body_html'],
        'labels': email_data['labels'],
        'is_read': email_data['is_read'],
        'has_attachments': email_data['has_attachments'],
        'thread_id': email_data['thread_id'],
        'account_email': account_email_str,
        'account_link': account_token,
        'sender_contact': sender_contact
    }
    
    # 3. Save Email
    email_obj, created = Email.objects.update_or_create(
        gmail_id=email_data['gmail_id'],
        defaults=defaults
    )
    
    # 4. Handle Recipients (M2M) - post save
    all_recipients = []
    all_recipients.extend(email_data.get('recipient_list', []))
    all_recipients.extend(email_data.get('cc_list', []))
    all_recipients.extend(email_data.get('bcc_list', []))
    
    # Create contacts and link
    if all_recipients:
        contact_objs = []
        for email_addr in set(all_recipients): # dedup
            c = get_or_create_contact(email_addr)
            if c:
                contact_objs.append(c)
        
        email_obj.recipients.set(contact_objs)
    
    # 5. Handle Attachments
    attachments_metadata = email_data.get('attachments_metadata', [])
    if attachments_metadata and service:
        from ..models import Attachment
        from django.core.files.base import ContentFile
        
        for att_meta in attachments_metadata:
            # Check if attachment already exists
            existing = Attachment.objects.filter(
                email=email_obj,
                gmail_attachment_id=att_meta['attachment_id']
            ).first()
            
            if not existing:
                # Download attachment
                file_data = download_attachment(
                    service,
                    email_data['gmail_id'],
                    att_meta['attachment_id']
                )
                
                if file_data:
                    # Create Attachment object
                    attachment = Attachment(
                        email=email_obj,
                        gmail_attachment_id=att_meta['attachment_id'],
                        filename=att_meta['filename'],
                        mime_type=att_meta['mime_type'],
                        size_bytes=att_meta['size']
                    )
                    
                    # Save file
                    attachment.file.save(
                        att_meta['filename'],
                        ContentFile(file_data),
                        save=True
                    )
                    
                    logger.info(f"Downloaded attachment: {att_meta['filename']} ({att_meta['size']} bytes)")
        
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
                
                # Save to database (pass service for attachment downloads)
                email_obj, created = save_email_to_db(email_data, service=service)
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
