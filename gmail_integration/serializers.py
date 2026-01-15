from rest_framework import serializers
from .models import Email, GmailToken, SyncStatus

class GmailTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = GmailToken
        fields = ['id', 'email_account', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

class EmailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Email
        fields = [
            'id', 'account_email', 'gmail_id', 'thread_id', 'subject', 
            'sender_contact', 'recipients', 'date', 
            'snippet', 'is_read', 'has_attachments', 'labels'
        ]
        read_only_fields = ['gmail_id', 'thread_id', 'date']

class SyncStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyncStatus
        fields = '__all__'
