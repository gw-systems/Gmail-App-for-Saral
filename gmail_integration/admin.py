from django.contrib import admin
from .models import GmailToken, Email, SyncStatus, Contact, Attachment


@admin.register(GmailToken)
class GmailTokenAdmin(admin.ModelAdmin):
    list_display = ('id', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at', 'token_data')


class AttachmentInline(admin.TabularInline):
    """Inline admin for attachments"""
    model = Attachment
    extra = 0
    readonly_fields = ('filename', 'mime_type', 'size_bytes', 'get_size_display', 'created_at')
    fields = ('filename', 'mime_type', 'get_size_display', 'file', 'created_at')
    can_delete = True


@admin.register(Email)
class EmailAdmin(admin.ModelAdmin):
    list_display = ('subject', 'sender_contact', 'date', 'is_read', 'label_list_display')
    list_filter = ('is_read', 'date', 'has_attachments')
    search_fields = ('subject', 'sender_contact__email', 'sender_contact__name', 'body_text')
    readonly_fields = ('gmail_id', 'thread_id', 'created_at', 'updated_at')
    date_hierarchy = 'date'
    inlines = [AttachmentInline]
    
    def label_list_display(self, obj):
        return ', '.join(obj.label_list)
    label_list_display.short_description = 'Labels'


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ('filename', 'email', 'mime_type', 'get_size_display', 'created_at')
    list_filter = ('mime_type', 'created_at')
    search_fields = ('filename', 'email__subject')
    readonly_fields = ('gmail_attachment_id', 'size_bytes', 'get_size_display', 'created_at')



@admin.register(SyncStatus)
class SyncStatusAdmin(admin.ModelAdmin):
    list_display = ('last_sync', 'status', 'emails_synced', 'history_id')
    list_filter = ('status',)
    readonly_fields = ('last_sync',)
