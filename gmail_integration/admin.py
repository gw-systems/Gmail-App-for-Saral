from django.contrib import admin
from .models import GmailToken, Email, SyncStatus


@admin.register(GmailToken)
class GmailTokenAdmin(admin.ModelAdmin):
    list_display = ('id', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at', 'token_data')


@admin.register(Email)
class EmailAdmin(admin.ModelAdmin):
    list_display = ('subject', 'sender', 'date', 'is_read', 'label_list_display')
    list_filter = ('is_read', 'date', 'has_attachments')
    search_fields = ('subject', 'sender', 'recipient', 'body_text')
    readonly_fields = ('gmail_id', 'thread_id', 'created_at', 'updated_at')
    date_hierarchy = 'date'
    
    def label_list_display(self, obj):
        return ', '.join(obj.label_list)
    label_list_display.short_description = 'Labels'


@admin.register(SyncStatus)
class SyncStatusAdmin(admin.ModelAdmin):
    list_display = ('last_sync', 'status', 'emails_synced', 'history_id')
    list_filter = ('status',)
    readonly_fields = ('last_sync',)
