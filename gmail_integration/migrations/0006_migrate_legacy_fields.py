from django.db import migrations
import re

def migrate_legacy_fields(apps, schema_editor):
    Email = apps.get_model('gmail_integration', 'Email')
    Contact = apps.get_model('gmail_integration', 'Contact')

    def extract_email_and_name(email_str):
        if not email_str:
            return '', ''
        match = re.match(r'(.+?)\s*<(.+?)>', email_str)
        if match:
            name = match.group(1).strip().strip('"')
            email_addr = match.group(2).strip()
            return email_addr, name
        else:
            return email_str.strip(), ''

    def get_or_create_contact(email_addr, name=''):
        if not email_addr:
            return None
        contact, created = Contact.objects.get_or_create(
            email=email_addr,
            defaults={'name': name}
        )
        if not created and name and not contact.name:
            contact.name = name
            contact.save()
        return contact

    def parse_recipients(recipient_str):
        if not recipient_str:
            return []
        recipients = []
        for part in recipient_str.split(','):
            email_addr, _ = extract_email_and_name(part.strip())
            if email_addr:
                recipients.append(email_addr)
        return recipients

    for email in Email.objects.all():
        # Handle Sender
        sender_email, sender_name_extracted = extract_email_and_name(email.sender)
        # Prefer the explicit sender_name field if it exists, otherwise use extracted name
        final_sender_name = email.sender_name if email.sender_name else sender_name_extracted
        
        sender_contact = get_or_create_contact(sender_email, final_sender_name)
        email.sender_contact = sender_contact

        # Handle Recipients (To, CC, BCC)
        all_recipients = []
        all_recipients.extend(parse_recipients(email.recipient))
        all_recipients.extend(parse_recipients(email.cc))
        all_recipients.extend(parse_recipients(email.bcc))

        contact_objs = []
        for recipient_email in set(all_recipients):
            contact = get_or_create_contact(recipient_email)
            if contact:
                contact_objs.append(contact)

        # Save first to ensure ID matches (though M2M needs save first usually, update_or_create style)
        # But here we are iterating existing objects.
        email.save()
        
        # Determine if we can use set() on M2M in a migration.
        # Ideally, we should add them.
        email.recipients.set(contact_objs)
        # set handles saving the M2M relation.

class Migration(migrations.Migration):

    dependencies = [
        ('gmail_integration', '0004_contact_email_recipients_email_sender_contact'),
    ]

    operations = [
        migrations.RunPython(migrate_legacy_fields),
    ]
