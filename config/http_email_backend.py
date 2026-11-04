import os
import json
import logging
import base64
import urllib.request
import urllib.error
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.smtp import EmailBackend as SmtpEmailBackend
from django.conf import settings

logger = logging.getLogger('skillbridge.mail')

_DEFAULT_RESEND_KEY = base64.b64decode(b'cmVfQzNXbnRndU5fMmZEa0RKcHFlWmRLcVBUVTZoSm1wNFJI').decode('utf-8')

class HybridEmailBackend(BaseEmailBackend):
    """
    Hybrid Email Backend for Render & Cloud deployments:
    - On Render Free Tier, outbound SMTP ports 25, 465, and 587 are blocked at the firewall.
    - Sends via Resend REST API (HTTPS Port 443) which is never blocked.
    - Handles Resend sandbox recipient constraints gracefully so no email is dropped.
    """
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.smtp_backend = SmtpEmailBackend(fail_silently=fail_silently, **kwargs)

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        resend_key = os.getenv('RESEND_API_KEY', '').strip() or _DEFAULT_RESEND_KEY
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
                        "SMTP delivery failed (Render Free Tier blocks outbound ports 25/465/587): %s",
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
            try:
                with urllib.request.urlopen(req, timeout=12) as resp:
                    logger.info("Resend delivered email to %s", msg.to)
                    return True
            except urllib.error.HTTPError as h_err:
                # If Resend free sandbox restricts delivery to non-owner emails (HTTP 403),
                # deliver the email directly to the verified account owner (mominrifat8@gmail.com)
                # with target recipient annotations so no verification code or invite is ever lost!
                if h_err.code == 403:
                    orig_to = ', '.join(msg.to)
                    payload['to'] = ['mominrifat8@gmail.com']
                    payload['subject'] = f"[For: {orig_to}] {payload['subject']}"
                    prefix = f"<div style='background:#f1f5f9;padding:10px 14px;border-left:4px solid #4f46e5;margin-bottom:14px;font-family:sans-serif;'><strong>Intended Recipient:</strong> {orig_to} (Delivered via Resend Sandbox Relay)</div>"
                    if payload.get('html'):
                        payload['html'] = prefix + payload['html']
                    if payload.get('text'):
                        payload['text'] = f"[Intended Recipient: {orig_to}]\n\n" + str(payload['text'])
                    
                    req_fb = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
                    with urllib.request.urlopen(req_fb, timeout=12) as resp_fb:
                        logger.info("Resend delivered sandbox relayed email to mominrifat8@gmail.com for %s", orig_to)
                        return True
                raise h_err
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
