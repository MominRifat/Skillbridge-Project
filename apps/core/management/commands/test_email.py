from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
import sys

class Command(BaseCommand):
    help = 'Send a test email to verify SMTP configuration'

    def add_arguments(self, parser):
        parser.add_argument('recipient', type=str, help='Email address to send test email to')

    def handle(self, *args, **options):
        recipient = options['recipient'].strip()
        self.stdout.write(self.style.NOTICE(f"=== Testing Email Configuration ==="))
        self.stdout.write(f"EMAIL_BACKEND:       {settings.EMAIL_BACKEND}")
        self.stdout.write(f"EMAIL_HOST:          {settings.EMAIL_HOST}")
        self.stdout.write(f"EMAIL_PORT:          {settings.EMAIL_PORT}")
        self.stdout.write(f"EMAIL_USE_TLS:       {settings.EMAIL_USE_TLS}")
        self.stdout.write(f"EMAIL_USE_SSL:       {settings.EMAIL_USE_SSL}")
        self.stdout.write(f"EMAIL_HOST_USER:     {settings.EMAIL_HOST_USER or '(Not set)'}")
        self.stdout.write(f"DEFAULT_FROM_EMAIL:  {settings.DEFAULT_FROM_EMAIL}")
        self.stdout.write(f"EMAIL_TIMEOUT:       {getattr(settings, 'EMAIL_TIMEOUT', 10)}s")
        self.stdout.write("------------------------------------")

        if not settings.EMAIL_HOST_USER or not getattr(settings, 'EMAIL_HOST_PASSWORD', None):
            self.stdout.write(self.style.WARNING(
                "NOTE: EMAIL_HOST_USER or EMAIL_HOST_PASSWORD is not set.\n"
                "In console mode, the email will print below rather than being sent over the internet.\n"
            ))

        try:
            self.stdout.write(f"Attempting to send test email to {recipient}...")
            sent = send_mail(
                subject='[SkillBridge] SMTP Test Email',
                message='Congratulations! Your SkillBridge email configuration is working properly.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient],
                fail_silently=False,
            )
            if sent:
                self.stdout.write(self.style.SUCCESS(f"\n[SUCCESS] Test email successfully dispatched to {recipient}!"))
            else:
                self.stdout.write(self.style.ERROR("\n[FAILED] Email was not dispatched (sent count = 0)."))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"\n[ERROR] Email sending failed: {exc}"))
            self.stdout.write(self.style.NOTICE(
                "\nTroubleshooting Gmail SMTP:\n"
                "1. Make sure you are using a 16-character Google 'App Password', NOT your personal Gmail password.\n"
                "   Generate one at: https://myaccount.google.com/apppasswords\n"
                "2. Set EMAIL_USE_TLS=True and EMAIL_PORT=587.\n"
                "3. Verify EMAIL_HOST_USER matches the Google account that generated the App Password."
            ))
            sys.exit(1)
