import pytest
from django.contrib.auth.models import User
from gmail_integration.models import Email, GmailToken, SyncStatus
from datetime import datetime
from django.utils import timezone


@pytest.fixture
def test_user():
    """Create a test user."""
    user = User.objects.create_user(
        username='testuser',
        email='testuser@example.com',
        password='testpass123'
    )
    return user


@pytest.fixture
def admin_user():
    """Create an admin test user."""
    user = User.objects.create_user(
        username='admin',
        email='systems@godamwale.com',
        password='adminpass123',
        is_superuser=True
    )
    return user


@pytest.fixture
def gmail_token(test_user):
    """Create a test Gmail token."""
    token = GmailToken.objects.create(
        user=test_user,
        email_account='test@godamwale.com',
        token_data={
            'token': 'test_token',
            'refresh_token': 'test_refresh_token',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'client_id': 'test_client_id',
            'client_secret': 'test_client_secret',
            'scopes': ['https://www.googleapis.com/auth/gmail.readonly']
        },
        is_active=True
    )
    return token


@pytest.fixture
def sample_email(gmail_token):
    """Create a sample email."""
    from gmail_integration.models import Contact
    
    sender_contact, _ = Contact.objects.get_or_create(email='sender@example.com', name='Test Sender')
    recipient_contact, _ = Contact.objects.get_or_create(email='test@godamwale.com', name='Test User')
    
    email = Email.objects.create(
        account_email='test@godamwale.com',
        account_link=gmail_token,
        gmail_id='test_gmail_id_123',
        thread_id='test_thread_123',
        subject='Test Email Subject',
        sender_contact=sender_contact,
        date=timezone.now(),
        snippet='This is a test email snippet',
        body_text='This is the body of the test email.',
        body_html='<p>This is the body of the test email.</p>',
        labels=['INBOX', 'UNREAD'],
        is_read=False,
        has_attachments=False
    )
    email.recipients.add(recipient_contact)
    return email


@pytest.fixture
def sync_status():
    """Create a sync status record."""
    status = SyncStatus.objects.create(
        account_email='test@godamwale.com',
        status='success',
        history_id='test_history_id',
        emails_synced=10
    )
    return status
