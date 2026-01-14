import os
import django
from datetime import datetime
from django.utils import timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gmail_project.settings")
django.setup()

from gmail_integration.models import Email, Contact
from gmail_integration.utils.gmail_api import save_email_to_db

def verify_data_model():
    print("Verifying Data Model Upgrade...")
    
    # Mock Email Data
    email_data = {
        'gmail_id': 'test_msg_001',
        'thread_id': 'test_thread_001',
        'subject': 'Harsh Manager Review',
        'sender': 'manager@deepmind.com',
        'sender_name': 'Harsh Boss',
        'recipient': 'dev@saral.com, helper@saral.com',
        'cc': 'ceo@saral.com',
        'bcc': 'spy@saral.com',
        'date': timezone.now(),
        'snippet': 'Fix this mess.',
        'body_text': ' ASAP.',
        'account_email': 'dev@saral.com'
    }
    
    # Run Save Logic
    print("Saving email...")
    email_obj, created = save_email_to_db(email_data)
    
    print(f"Email Saved: {email_obj.subject} (Created: {created})")
    
    # Verify Sender Contact
    if email_obj.sender_contact:
        print(f"✅ Sender Contact Linked: {email_obj.sender_contact}")
        if email_obj.sender_contact.email == 'manager@deepmind.com' and email_obj.sender_contact.name == 'Harsh Boss':
            print("   ✅ Sender Data Correct")
        else:
            print("   ❌ Sender Data Mismatch")
    else:
        print("❌ Sender Contact Missing")

    # Verify Recipients
    recipients = email_obj.recipients.all()
    print(f"Recipients Found: {recipients.count()}")
    
    expected_emails = [
        'dev@saral.com', 'helper@saral.com', 
        'ceo@saral.com', 'spy@saral.com'
    ]
    
    found_emails = [c.email for c in recipients]
    
    for email in expected_emails:
        if email in found_emails:
            print(f"   ✅ Found Recipient: {email}")
        else:
            print(f"   ❌ Missing Recipient: {email}")
            
    # Clean up
    email_obj.delete()
    Contact.objects.filter(email__in=expected_emails + ['manager@deepmind.com']).delete()
    print("Cleanup done.")

if __name__ == "__main__":
    verify_data_model()
