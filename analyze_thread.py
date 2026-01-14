#!/usr/bin/env python
"""
Script to find and analyze a specific email thread
"""
import os
import sys
import django

# Setup Django
sys.path.append(r'c:\Users\ADMIN\OneDrive\Desktop\Gmail App with Saral ERP')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gmail_project.settings')
django.setup()

from gmail_integration.models import Email
from gmail_integration.utils.gmail_auth import get_gmail_service
import json

# Find the email about warehouse shifting
print("=" * 60)
print("FINDING EMAIL...")
print("=" * 60)

email = Email.objects.filter(subject__icontains='Warehouse Facility Shifting').first()

if not email:
    print("❌ Email not found in database")
    print("\nSearching for similar subjects:")
    for e in Email.objects.all()[:10]:
        print(f"  - {e.subject[:60]}")
    sys.exit(1)

print(f"✅ Found email!")
print(f"Subject: {email.subject}")
print(f"From: {email.sender}")
print(f"Date: {email.date}")
print(f"Gmail ID: {email.gmail_id}")
print(f"Thread ID: {email.thread_id}")
print()

# Check how many emails are in this thread
thread_emails = Email.objects.filter(thread_id=email.thread_id).order_by('date')
print(f"📊 Emails in database for this thread: {thread_emails.count()}")
for i, te in enumerate(thread_emails, 1):
    print(f"  {i}. {te.date.strftime('%Y-%m-%d %H:%M')} - {te.sender}: {te.subject[:50]}")
print()

# Fetch full thread from Gmail API
print("=" * 60)
print("FETCHING FULL THREAD FROM GMAIL API...")
print("=" * 60)

service = get_gmail_service()
if not service:
    print("❌ Not authenticated")
    sys.exit(1)

# Get thread details
thread = service.users().threads().get(userId='me', id=email.thread_id, format='full').execute()

print(f"✅ Thread fetched!")
print(f"Total messages in thread: {len(thread['messages'])}")
print()

# Analyze each message in the thread
print("=" * 60)
print("THREAD CONVERSATION ANALYSIS")
print("=" * 60)

for i, msg in enumerate(thread['messages'], 1):
    msg_id = msg['id']
    snippet = msg.get('snippet', '')
    
    # Parse headers
    headers = {h['name'].lower(): h['value'] for h in msg['payload']['headers']}
    
    from_addr = headers.get('from', 'Unknown')
    to_addr = headers.get('to', '')
    cc_addr = headers.get('cc', '')
    bcc_addr = headers.get('bcc', '')
    subject = headers.get('subject', '')
    date = headers.get('date', '')
    
    print(f"\n📧 Message {i}/{len(thread['messages'])}")
    print(f"   Message ID: {msg_id}")
    print(f"   Date: {date}")
    print(f"   From: {from_addr}")
    print(f"   To: {to_addr}")
    if cc_addr:
        print(f"   CC: {cc_addr}")
    if bcc_addr:
        print(f"   BCC: {bcc_addr}")
    print(f"   Subject: {subject}")
    print(f"   Snippet: {snippet[:100]}...")
    print(f"   Labels: {msg.get('labelIds', [])}")

print("\n" + "=" * 60)
print("THREAD METADATA")
print("=" * 60)
print(f"Thread ID: {thread['id']}")
print(f"History ID: {thread.get('historyId', 'N/A')}")
print()

# Save full thread data to JSON for inspection
output_file = r'C:\Users\ADMIN\OneDrive\Desktop\Gmail App with Saral ERP\thread_analysis.json'
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(thread, f, indent=2, ensure_ascii=False)

print(f"💾 Full thread data saved to: thread_analysis.json")
print("\nYou can inspect the raw JSON to see ALL available data!")
