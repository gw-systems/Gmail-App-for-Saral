from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import json


class GmailToken(models.Model):
    """Store OAuth tokens for Gmail API authentication - Multi-Account Support"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, help_text="ERP user who owns this token")
    email_account = models.EmailField(db_index=True, help_text="Gmail address (e.g., support@godamwale.com)")
    token_data = models.JSONField(help_text="Stores access token, refresh token, and expiry", null=True, blank=True)
    encrypted_token_data = models.TextField(help_text="Encrypted token data (GDPR compliant)", null=True, blank=True)
    is_active = models.BooleanField(default=True, help_text="Whether this account is actively syncing")
    account_color = models.CharField(max_length=50, default='account-gray', help_text="CSS class for account color (e.g., account-purple)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Gmail Token"
        verbose_name_plural = "Gmail Tokens"
        unique_together = ['user', 'email_account']
    
    def __str__(self):
        return f"{self.email_account} (User: {self.user.username})"
    
    def get_decrypted_token(self):
        """Get decrypted token data (GDPR compliant)"""
        from gmail_integration.utils.encryption import EncryptionUtils
        
        # Prefer encrypted data if available
        if self.encrypted_token_data:
            decrypted = EncryptionUtils.decrypt(self.encrypted_token_data)
            if decrypted:
                return decrypted
        
        # Fallback to plaintext (for migration period)
        if self.token_data:
            return self.token_data
        
        return None
    
    def set_encrypted_token(self, token_data):
        """Encrypt and save token data (GDPR compliant)"""
        from gmail_integration.utils.encryption import EncryptionUtils
        
        if token_data:
            self.encrypted_token_data = EncryptionUtils.encrypt(token_data)
            # Keep plaintext for backward compatibility during migration
            self.token_data = token_data
    
    @classmethod
    def get_token_for_user(cls, user):
        """Get active Gmail token for a specific user"""
        token = cls.objects.filter(user=user, is_active=True).first()
        if token:
            return token.get_decrypted_token()
        return None
    
    @classmethod
    def save_token_for_user(cls, user, email_account, token_data):
        """Save or update token for a specific user (with encryption)"""
        token, created = cls.objects.update_or_create(
            user=user,
            email_account=email_account,
            defaults={
                'is_active': True,
            }
        )
        # Use encryption method
        token.set_encrypted_token(token_data)
        token.save()
        return token
    
    @classmethod
    def get_all_active_tokens(cls):
        """Get all active tokens for syncing"""
        return cls.objects.filter(is_active=True)


class Contact(models.Model):
    """Store contact details for senders and recipients"""
    email = models.EmailField(unique=True, db_index=True)
    name = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} <{self.email}>" if self.name else self.email

    class Meta:
        verbose_name = "Contact"
        verbose_name_plural = "Contacts"
        ordering = ['email']


class Email(models.Model):
    """Store email messages from Gmail - Multi-Account Support"""
    account_email = models.EmailField(max_length=255, db_index=True, help_text="Gmail account this email belongs to")
    account_link = models.ForeignKey(GmailToken, on_delete=models.SET_NULL, null=True, blank=True, related_name='emails', help_text="Link to the Gmail Token/Account")
    gmail_id = models.CharField(max_length=255, unique=True, help_text="Gmail message ID")
    thread_id = models.CharField(max_length=255, db_index=True, help_text="Gmail thread ID")
    subject = models.TextField(blank=True)
    
    
    # Relationships
    sender_contact = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True, related_name='sent_emails', help_text="Link to Sender Contact")
    recipients = models.ManyToManyField(Contact, related_name='received_emails', blank=True, help_text="All recipients (To, CC, BCC)")
    
    date = models.DateTimeField(db_index=True)
    snippet = models.TextField(blank=True, help_text="Email preview text")
    body_text = models.TextField(blank=True, help_text="Plain text body")
    body_html = models.TextField(blank=True, help_text="HTML body")
    labels = models.JSONField(default=list, help_text="Gmail labels (INBOX, SENT, etc.)")
    is_read = models.BooleanField(default=False)
    has_attachments = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Email"
        verbose_name_plural = "Emails"
        ordering = ['-date']
        indexes = [
            models.Index(fields=['-date']),
            models.Index(fields=['thread_id']),
            models.Index(fields=['account_email', '-date']),
        ]
    
    def __str__(self):
        subject_snippet = self.subject[:50] if self.subject else "(No Subject)"
        sender_str = str(self.sender_contact) if self.sender_contact else "Unknown Sender"
        return f"[{self.account_email}] {subject_snippet} - {sender_str}"
    
    def get_account_color_class(self):
        """Get CSS class for account color coding from the associated GmailToken"""
        # Fetch the color from the database instead of hardcoding
        token = GmailToken.objects.filter(email_account=self.account_email).first()
        if token:
            return token.account_color
        return 'account-gray'
    
    @property
    def is_inbox(self):
        """Check if email is in inbox"""
        return 'INBOX' in self.labels
    
    @property
    def is_sent(self):
        """Check if email is sent"""
        return 'SENT' in self.labels
    
    @property
    def label_list(self):
        """Get list of labels as strings"""
        if isinstance(self.labels, list):
            return self.labels
        return []


class Attachment(models.Model):
    """Store email attachments"""
    email = models.ForeignKey(Email, on_delete=models.CASCADE, related_name='attachments', help_text="Email this attachment belongs to")
    gmail_attachment_id = models.CharField(max_length=255, help_text="Gmail's attachment ID")
    filename = models.CharField(max_length=255, help_text="Original filename")
    mime_type = models.CharField(max_length=100, help_text="File MIME type (e.g., application/pdf)")
    size_bytes = models.IntegerField(help_text="File size in bytes")
    file = models.FileField(upload_to='attachments/%Y/%m/%d/', help_text="Stored file")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Attachment"
        verbose_name_plural = "Attachments"
        ordering = ['filename']
        indexes = [
            models.Index(fields=['email', 'filename']),
        ]
    
    def __str__(self):
        return f"{self.filename} ({self.get_size_display()})"
    
    def get_size_display(self):
        """Return human-readable file size"""
        size = self.size_bytes
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    
    @property
    def icon_class(self):
        """Return icon class based on MIME type"""
        if 'pdf' in self.mime_type:
            return '📄'
        elif 'image' in self.mime_type:
            return '🖼️'
        elif 'word' in self.mime_type or 'document' in self.mime_type:
            return '📝'
        elif 'excel' in self.mime_type or 'spreadsheet' in self.mime_type:
            return '📊'
        elif 'zip' in self.mime_type or 'compressed' in self.mime_type:
            return '📦'
        else:
            return '📎'



class SyncStatus(models.Model):
    """Track Gmail sync status and history - Multi-Account Support"""
    account_email = models.EmailField(max_length=255, db_index=True, help_text="Gmail account synced", null=True, blank=True)
    last_sync = models.DateTimeField(auto_now=True)
    history_id = models.CharField(max_length=255, blank=True, help_text="Gmail history ID for incremental sync")
    status = models.CharField(
        max_length=50,
        choices=[
            ('success', 'Success'),
            ('error', 'Error'),
            ('in_progress', 'In Progress'),
        ],
        default='success'
    )
    error_message = models.TextField(blank=True)
    emails_synced = models.IntegerField(default=0, help_text="Number of emails synced in last sync")
    
    class Meta:
        verbose_name = "Sync Status"
        verbose_name_plural = "Sync Statuses"
        ordering = ['-last_sync']
    
    def __str__(self):
        account_str = f" [{self.account_email}]" if self.account_email else ""
        return f"Sync Status{account_str}: {self.status} at {self.last_sync}"
    
    @classmethod
    def get_latest(cls):
        """Get the latest sync status"""
        return cls.objects.first()
    
    @classmethod
    def create_sync_record(cls, status='success', history_id='', emails_synced=0, error_message='', account_email=None):
        """Create a new sync status record"""
        return cls.objects.create(
            account_email=account_email,
            status=status,
            history_id=history_id,
            emails_synced=emails_synced,
            error_message=error_message
        )
