import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gmail_project.settings')
django.setup()

from gmail_integration.models import Email, GmailToken
from django.contrib.auth.models import User

print("=== DEBUGGING DB STATUS ===")

print(f"\n1. USERS: {User.objects.count()}")
for u in User.objects.all():
    print(f"   - {u.username} (email: {u.email})")

print(f"\n2. GMAIL TOKENS: {GmailToken.objects.count()}")
for t in GmailToken.objects.all():
    print(f"   - User: {repr(t.user.username)}")
    print(f"     Account: {repr(t.email_account)}")
    print(f"     Active: {t.is_active}")

print(f"\n3. EMAILS: {Email.objects.count()}")
emails_with_account = Email.objects.exclude(account_email="").exclude(account_email__isnull=True).count()
print(f"   - With account_email set: {emails_with_account}")

print("\n4. SAMPLE EMAILS (First 5):")
for e in Email.objects.all()[:5]:
    print(f"   - ID: {e.id}")
    print(f"     Subject: {e.subject[:30]}...")
    print(f"     Account Email: {repr(e.account_email)}")
