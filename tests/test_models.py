import pytest
from django.contrib.auth.models import User
from gmail_integration.models import Email, GmailToken, SyncStatus
from django.utils import timezone


@pytest.mark.django_db
@pytest.mark.unit
class TestGmailToken:
    """Tests for the GmailToken model."""

    def test_create_gmail_token(self, test_user):
        """Test creating a Gmail token."""
        token = GmailToken.objects.create(
            user=test_user,
            email_account='test@example.com',
            token_data={'token': 'test_token'},
            is_active=True
        )
        assert token.email_account == 'test@example.com'
        assert token.user == test_user
        assert token.is_active is True

    def test_gmail_token_string_representation(self, gmail_token):
        """Test the string representation of GmailToken."""
        expected = f"{gmail_token.email_account} (User: {gmail_token.user.username})"
        assert str(gmail_token) == expected

    def test_get_token_for_user(self, test_user, gmail_token):
        """Test getting token for a specific user."""
        token_data = GmailToken.get_token_for_user(test_user)
        assert token_data is not None
        assert token_data == gmail_token.token_data

    def test_save_token_for_user(self, test_user):
        """Test saving a token for a user."""
        token_data = {'token': 'new_token', 'refresh_token': 'new_refresh'}
        token = GmailToken.save_token_for_user(
            user=test_user,
            email_account='new@example.com',
            token_data=token_data
        )
        assert token.email_account == 'new@example.com'
        assert token.token_data == token_data

    def test_get_all_active_tokens(self, gmail_token):
        """Test getting all active tokens."""
        active_tokens = GmailToken.get_all_active_tokens()
        assert active_tokens.count() >= 1
        assert gmail_token in active_tokens


@pytest.mark.django_db
@pytest.mark.unit
class TestEmail:
    """Tests for the Email model."""

    def test_create_email(self, sample_email):
        """Test creating an email."""
        assert sample_email.subject == 'Test Email Subject'
        assert sample_email.sender == 'sender@example.com'
        assert sample_email.is_read is False

    def test_email_string_representation(self, sample_email):
        """Test the string representation of Email."""
        result = str(sample_email)
        assert sample_email.account_email in result
        assert sample_email.sender in result

    def test_is_inbox_property(self, sample_email):
        """Test the is_inbox property."""
        assert sample_email.is_inbox is True

    def test_is_sent_property(self, sample_email):
        """Test the is_sent property."""
        assert sample_email.is_sent is False
        # Add SENT label
        sample_email.labels.append('SENT')
        sample_email.save()
        assert sample_email.is_sent is True

    def test_label_list_property(self, sample_email):
        """Test the label_list property."""
        labels = sample_email.label_list
        assert isinstance(labels, list)
        assert 'INBOX' in labels


@pytest.mark.django_db
@pytest.mark.unit
class TestSyncStatus:
    """Tests for the SyncStatus model."""

    def test_create_sync_status(self, sync_status):
        """Test creating a sync status."""
        assert sync_status.status == 'success'
        assert sync_status.emails_synced == 10

    def test_sync_status_string_representation(self, sync_status):
        """Test the string representation of SyncStatus."""
        result = str(sync_status)
        assert sync_status.account_email in result
        assert sync_status.status in result

    def test_create_sync_record(self):
        """Test creating a sync record using class method."""
        record = SyncStatus.create_sync_record(
            status='success',
            history_id='test_123',
            emails_synced=5,
            account_email='test@example.com'
        )
        assert record.status == 'success'
        assert record.emails_synced == 5
        assert record.account_email == 'test@example.com'

    def test_get_latest_sync_status(self, sync_status):
        """Test getting the latest sync status."""
        latest = SyncStatus.get_latest()
        assert latest is not None
        assert latest.account_email == sync_status.account_email
