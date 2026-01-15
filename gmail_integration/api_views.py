from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from .models import Email, GmailToken, SyncStatus
from .serializers import EmailSerializer, GmailTokenSerializer, SyncStatusSerializer

class EmailViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint that allows emails to be viewed.
    """
    queryset = Email.objects.all()
    serializer_class = EmailSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['account_email', 'is_read', 'has_attachments']
    search_fields = ['subject', 'body_text', 'sender_contact__email', 'sender_contact__name', 'snippet']
    ordering_fields = ['date', 'created_at']

    def get_queryset(self):
        user = self.request.user
        if user.has_perm('gmail_integration.view_all_gmail_accounts'):
            return Email.objects.all()
        
        user_accounts = GmailToken.objects.filter(user=user).values_list('email_account', flat=True)
        return Email.objects.filter(account_email__in=user_accounts)

class GmailTokenViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows Gmail tokens to be viewed or edited.
    """
    queryset = GmailToken.objects.all()
    serializer_class = GmailTokenSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Users only see their own tokens
        if self.request.user.has_perm('gmail_integration.view_all_gmail_accounts'):
            return GmailToken.objects.all()
        return GmailToken.objects.filter(user=self.request.user)

class SyncStatusViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint that allows sync status to be viewed.
    """
    queryset = SyncStatus.objects.all()
    serializer_class = SyncStatusSerializer
    permission_classes = [permissions.IsAuthenticated]
