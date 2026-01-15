from django.core.management.base import BaseCommand
from gmail_integration.models import GmailToken
from gmail_integration.utils.encryption import EncryptionUtils


class Command(BaseCommand):
    help = 'Migrate plaintext tokens to encrypted format (GDPR compliance)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be migrated without actually migrating',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Find all tokens that have plaintext data but no encrypted data
        tokens_to_migrate = GmailToken.objects.filter(
            token_data__isnull=False
        ).exclude(
            encrypted_token_data__isnull=False,
            encrypted_token_data=''
        )
        
        count = tokens_to_migrate.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS('No tokens need migration. All tokens are already encrypted!'))
            return
        
        self.stdout.write(f'Found {count} token(s) to migrate.')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made'))
            for token in tokens_to_migrate:
                self.stdout.write(f'  - Would migrate: {token.email_account} (User: {token.user.username})')
            return
        
        # Perform migration
        migrated = 0
        errors = 0
        
        for token in tokens_to_migrate:
            try:
                # Encrypt the plaintext token data
                encrypted_data = EncryptionUtils.encrypt(token.token_data)
                token.encrypted_token_data = encrypted_data
                token.save(update_fields=['encrypted_token_data'])
                
                # Verify decryption works
                decrypted = EncryptionUtils.decrypt(encrypted_data)
                if decrypted == token.token_data:
                    migrated += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ Migrated: {token.email_account} (User: {token.user.username})')
                    )
                else:
                    errors += 1
                    self.stdout.write(
                        self.style.ERROR(f'✗ Verification failed: {token.email_account}')
                    )
            except Exception as e:
                errors += 1
                self.stdout.write(
                    self.style.ERROR(f'✗ Error migrating {token.email_account}: {str(e)}')
                )
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Migration complete: {migrated} migrated, {errors} errors'))
        
        if errors == 0:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'NOTE: Plaintext token_data is kept for backward compatibility. '
                'In production, you may want to clear it after verifying encryption works.'
            ))
