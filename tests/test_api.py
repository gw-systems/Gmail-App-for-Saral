import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from gmail_integration.models import Email, GmailToken


@pytest.mark.django_db
@pytest.mark.api
class TestEmailViewSet:
    """Tests for the Email API endpoints."""

    @pytest.fixture
    def api_client(self):
        """Create an API client."""
        return APIClient()

    def test_list_emails_unauthenticated(self, api_client):
        """Test that unauthenticated users cannot list emails."""
        url = reverse('email-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_emails_authenticated(self, api_client, test_user, gmail_token, sample_email):
        """Test listing emails as an authenticated user."""
        api_client.force_authenticate(user=test_user)
        url = reverse('email-list')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        # Handle both paginated and non-paginated responses
        if isinstance(response.data, dict) and 'results' in response.data:
            assert len(response.data['results']) >= 1
        else:
            assert len(response.data) >= 1

    def test_retrieve_email(self, api_client, test_user, sample_email):
        """Test retrieving a single email."""
        api_client.force_authenticate(user=test_user)
        url = reverse('email-detail', kwargs={'pk': sample_email.pk})
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['subject'] == sample_email.subject

    def test_filter_emails_by_account(self, api_client, test_user, gmail_token, sample_email):
        """Test filtering emails by account."""
        api_client.force_authenticate(user=test_user)
        url = reverse('email-list')
        response = api_client.get(url, {'account_email': 'test@godamwale.com'})
        
        assert response.status_code == status.HTTP_200_OK
        # Handle both paginated and non-paginated responses
        results = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        for email in results:
            assert email['account_email'] == 'test@godamwale.com'

    def test_search_emails(self, api_client, test_user, sample_email):
        """Test searching emails."""
        api_client.force_authenticate(user=test_user)
        url = reverse('email-list')
        response = api_client.get(url, {'search': 'Test Email'})
        
        assert response.status_code == status.HTTP_200_OK

    def test_admin_sees_all_emails(self, api_client, admin_user, sample_email):
        """Test that admin users can see all emails."""
        api_client.force_authenticate(user=admin_user)
        url = reverse('email-list')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
@pytest.mark.api
class TestGmailTokenViewSet:
    """Tests for the GmailToken API endpoints."""

    @pytest.fixture
    def api_client(self):
        """Create an API client."""
        return APIClient()

    def test_list_tokens_authenticated(self, api_client, test_user, gmail_token):
        """Test listing tokens as an authenticated user."""
        api_client.force_authenticate(user=test_user)
        url = reverse('token-list')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        # Handle both paginated and non-paginated responses
        if isinstance(response.data, dict) and 'results' in response.data:
            assert len(response.data['results']) >= 1
        else:
            assert len(response.data) >= 1

    def test_user_only_sees_own_tokens(self, api_client, test_user, admin_user, gmail_token):
        """Test that regular users only see their own tokens."""
        # Create a token for admin user
        admin_token = GmailToken.objects.create(
            user=admin_user,
            email_account='admin@godamwale.com',
            token_data={'token': 'admin_token'},
            is_active=True
        )
        
        # Test user should only see their own token
        api_client.force_authenticate(user=test_user)
        url = reverse('token-list')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        # Handle both paginated and non-paginated responses
        results = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        for token in results:
            assert token['email_account'] != 'admin@godamwale.com'


@pytest.mark.django_db
@pytest.mark.api
class TestSyncStatusViewSet:
    """Tests for the SyncStatus API endpoints."""

    @pytest.fixture
    def api_client(self):
        """Create an API client."""
        return APIClient()

    def test_list_sync_status_authenticated(self, api_client, test_user, sync_status):
        """Test listing sync status as an authenticated user."""
        api_client.force_authenticate(user=test_user)
        url = reverse('sync-status-list')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK

    def test_sync_status_read_only(self, api_client, test_user, sync_status):
        """Test that sync status endpoints are read-only."""
        api_client.force_authenticate(user=test_user)
        url = reverse('sync-status-list')
        
        # Try to create a new sync status (should fail)
        response = api_client.post(url, {'status': 'error'})
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED]
