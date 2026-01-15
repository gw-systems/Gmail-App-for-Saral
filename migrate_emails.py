import os
import django
import sys

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gmail_project.settings')
django.setup()

from gmail_integration.models import Email, GmailToken

def migrate_data():
    print("Starting data migration...")
    tokens = GmailToken.objects.all()
    count = 0
    
    for token in tokens:
        print(f"Linking emails for {token.email_account}...")
        updated = Email.objects.filter(account_email=token.email_account).update(account_link=token)
        count += updated
        
    print(f"Done. Updated {count} emails.")

if __name__ == "__main__":
    migrate_data()
