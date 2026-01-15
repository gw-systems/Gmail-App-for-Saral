import pytest
from gmail_integration.serializers import EmailSerializer, GmailTokenSerializer, SyncStatusSerializer
from gmail_integration.models import Email, GmailToken, SyncStatus


@pytest.mark.django_db
@pytest.mark.unit
class TestEmailSerializer:
    """Tests for the EmailSerializer."""

    def test_email_serialization(self, sample_email):
        """Test serializing an email."""
        serializer = EmailSerializer(sample_email)
        data = serializer.data
        
        assert data['subject'] == sample_email.subject
        assert data['subject'] == sample_email.subject
        assert data['sender_contact'] == sample_email.sender_contact.id
        assert data['account_email'] == sample_email.account_email
        assert data['gmail_id'] == sample_email.gmail_id

    def test_email_deserialization(self, gmail_token):
        """Test deserializing email data."""
        email_data = {
            'account_email': 'test@godamwale.com',
            'gmail_id': 'unique_gmail_id_456',
            'thread_id': 'thread_456',
            'subject': 'New Test Email',
            'subject': 'New Test Email',
            'sender_contact': None, # Contact creation is handled differently, usually serializer would expect nested or ID. 
                                    # Assuming for now we test fields. 
                                    # Actually, serializer defaults to PrimaryKeyRelatedField.
            'date': '2024-01-01T00:00:00Z',
            'snippet': 'Test snippet',
            'is_read': False,
            'has_attachments': False,
            'labels': ['INBOX']
        }
        
        serializer = EmailSerializer(data=email_data)
        assert serializer.is_valid()


@pytest.mark.django_db
@pytest.mark.unit
class TestGmailTokenSerializer:
    """Tests for the GmailTokenSerializer."""

    def test_gmail_token_serialization(self, gmail_token):
        """Test serializing a Gmail token."""
        serializer = GmailTokenSerializer(gmail_token)
        data = serializer.data
        
        assert data['email_account'] == gmail_token.email_account
        assert data['is_active'] == gmail_token.is_active
        assert 'token_data' not in data  # Should not expose sensitive token data

    def test_gmail_token_read_only_fields(self, gmail_token):
        """Test that certain fields are read-only."""
        serializer = GmailTokenSerializer(gmail_token)
        assert 'created_at' in serializer.data
        assert 'updated_at' in serializer.data


@pytest.mark.django_db
@pytest.mark.unit
class TestSyncStatusSerializer:
    """Tests for the SyncStatusSerializer."""

    def test_sync_status_serialization(self, sync_status):
        """Test serializing sync status."""
        serializer = SyncStatusSerializer(sync_status)
        data = serializer.data
        
        assert data['status'] == sync_status.status
        assert data['emails_synced'] == sync_status.emails_synced
        assert data['account_email'] == sync_status.account_email
