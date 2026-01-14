# Multi-Account Sync Fix - Quick Notes

## Problem Identified

The sync functions were using the **old single-user approach** and **not setting the `account_email` field** on emails. This caused:
1. Emails synced without account association
2. Tab filtering didn't work (no account_email to filter by)
3. Regular users saw no emails (filtering by empty account_email)

## What Was Fixed

### 1. Updated `fetch_emails()` Function
**Before:**
```python
def fetch_emails(label='INBOX', max_results=100):
    service = get_gmail_service()  # Old single-user method
    # ... fetch emails
    # email_data did NOT include account_email
```

**After:**
```python
def fetch_emails(service, account_email, label='INBOX', max_results=100):
    # Takes service and account_email as parameters
    # ... fetch emails
    email_data['account_email'] = account_email  # ✅ ADDED THIS
```

### 2. Rewrote `sync_all_emails()` Function
**Before:**
```python
def sync_all_emails():
    # Synced for single account only
    inbox_count = fetch_emails('INBOX')
    sent_count = fetch_emails('SENT')
```

**After:**
```python
def sync_all_emails():
    # Loop through ALL active Gmail tokens
    active_tokens = GmailToken.get_all_active_tokens()
    
    for token in active_tokens:
        account_email = token.email_account
        service = get_gmail_service(account_email=account_email)
        
        # Sync this specific account
        inbox_count = fetch_emails(service, account_email, 'INBOX')
        sent_count = fetch_emails(service, account_email, 'SENT')
```

### 3. Updated `check_for_new_emails()`
Simplified to just call the new `sync_all_emails()` which handles all accounts.

## Testing Instructions

**Delete old emails and re-sync:**

```bash
# Open Django shell
python manage.py shell

# Delete all existing emails (they don't have account_email set)
from gmail_integration.models import Email
Email.objects.all().delete()
exit()

# Now trigger a fresh sync
# Go to: http://localhost:8000/sync/
# Or use the Sync button in the app
```

**What should happen:**
1. Console shows syncing for each account separately
2. Each email gets `account_email` field set
3. Admin can filter by account tabs
4. Regular users see their own emails only

## Expected Console Output

```
Starting multi-account email sync...

============================================================
Sync account: kartik@godamwale.com
============================================================
Fetching 50 emails from INBOX for kartik@godamwale.com...
  ✓ Saved: Email subject 1
  ✓ Saved: Email subject 2
✓ kartik@godamwale.com: 50 inbox, 25 sent

============================================================
Syncing account: systems@godamwale.com
============================================================
Fetching 75 emails from INBOX for systems@godamwale.com...
  ✓ Saved: Email subject 3
✓ systems@godamwale.com: 75 inbox, 30 sent

============================================================
✓ Multi-account sync complete: 180 total emails across 2 accounts
============================================================
```
