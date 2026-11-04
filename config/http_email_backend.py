import os
import json
import logging
import urllib.request
import urllib.error
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.smtp import EmailBackend as SmtpEmailBackend
from django.conf import settings

logger = logging.getLogger('skillbridge.mail')

class HybridEmailBackend(BaseEmailBackend):
    """
    Hybrid Email Backend for Render & Cloud deployments:
    - On Render Free Tier, outbound SMTP ports 25, 465, and 587 are blocked at the firewall.
    - If RESEND_API_KEY is configured: sends via Resend REST API (HTTPS Port 443).
    - If BREVO_API_KEY is configured: sends via Brevo REST API (HTTPS Port 443).
    - Otherwise: sends via standard SMTP (works on localhost, VPS, or paid Render tiers).
    """
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.smtp_backend = SmtpEmailBackend(fail_silently=fail_silently, **kwargs)

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        resend_key = os.getenv('RESEND_API_KEY', '').strip()
        brevo_key = os.getenv('BREVO_API_KEY', '').strip()

        sent_count = 0
        for msg in email_messages:
            if resend_key:
                if self._send_resend(msg, resend_key):
                    sent_count += 1
            elif brevo_key:
                if self._send_brevo(msg, brevo_key):
                    sent_count += 1
            else:
                try:
                    sent_count += self.smtp_backend.send_messages([msg])
                except Exception as exc:
                    logger.warning(
                        "SMTP delivery failed (Render Free Tier blocks outbound ports 25/465/587). "
                        "Add RESEND_API_KEY or BREVO_API_KEY to Render environment variables to send over HTTPS port 443. Details: %s",
                        exc
                    )
                    if not self.fail_silently:
                        raise exc
        return sent_count

    def _send_resend(self, msg, api_key: str) -> bool:
        try:
            url = "https://api.resend.com/emails"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "SkillBridge/1.0"
            }
            from_addr = os.getenv('RESEND_FROM_EMAIL', '').strip() or getattr(settings, 'DEFAULT_FROM_EMAIL', 'SkillBridge <onboarding@resend.dev>')
            # If default sender is still local or user hasn't set custom domain, fallback to onboarding@resend.dev
            if '@gmail.com' in from_addr or '@skillbridge.local' in from_addr:
                from_addr = 'SkillBridge <onboarding@resend.dev>'

            html_body = None
            if hasattr(msg, 'alternatives'):
                for alt_content, alt_mimetype in msg.alternatives:
                    if alt_mimetype == 'text/html':
                        html_body = alt_content
                        break

            payload = {
                "from": from_addr,
                "to": list(msg.to),
                "subject": msg.subject,
                "text": str(msg.body),
            }
            if html_body:
                payload["html"] = html_body

            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers=headers,
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                logger.info("Resend delivered email to %s", msg.to)
                return True
        except Exception as exc:
            logger.error("Resend API delivery failed for %s: %s", msg.to, exc)
            return False

    def _send_brevo(self, msg, api_key: str) -> bool:
        try:
            url = "https://api.brevo.com/v3/smtp/email"
            headers = {
                "api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            sender_email = os.getenv('BREVO_SENDER_EMAIL', 'trexrifat8@gmail.com').strip()
            sender_name = os.getenv('BREVO_SENDER_NAME', 'SkillBridge').strip()

            html_body = None
            if hasattr(msg, 'alternatives'):
                for alt_content, alt_mimetype in msg.alternatives:
                    if alt_mimetype == 'text/html':
                        html_body = alt_content
                        break

            payload = {
                "sender": {"name": sender_name, "email": sender_email},
                "to": [{"email": addr} for addr in msg.to],
                "subject": msg.subject,
                "textContent": str(msg.body),
            }
            if html_body:
                payload["htmlContent"] = html_body

            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers=headers,
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                logger.info("Brevo delivered email to %s", msg.to)
                return True
        except Exception as exc:
            logger.error("Brevo API delivery failed for %s: %s", msg.to, exc)
            return False
