from __future__ import annotations
import logging
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.notifications.models import Notification, NotificationPreference, NotificationType
logger = logging.getLogger(__name__)

def notify(recipient, kind: str, title: str, *, message: str='', actor=None, target_url: str='', level: str=Notification.Level.INFO, email: bool | None=None, email_template: str='', email_context: dict | None=None, **metadata) -> Notification | None:
    if recipient is None or (actor is not None and actor.pk == recipient.pk):
        return None
    note = Notification.objects.create(recipient=recipient, actor=actor, notification_type=kind, level=level, title=title[:180], message=message[:500], target_url=target_url[:500], metadata=_clean(metadata))
    if email is None:
        prefs, _ = NotificationPreference.objects.get_or_create(user=recipient)
        email = prefs.allows_email(kind)
    if email:
        transaction.on_commit(lambda: _email(note, email_template, email_context or {}))
    return note

def notify_many(*recipients, kind: str, title: str, **kwargs) -> list[Notification]:
    seen: set[int] = set()
    created = []
    for recipient in recipients:
        if recipient is None or recipient.pk in seen:
            continue
        seen.add(recipient.pk)
        note = notify(recipient, kind, title, **kwargs)
        if note:
            created.append(note)
    return created

def mark_read(user, *, public_ids=None) -> int:
    qs = Notification.objects.for_user(user).unread()
    if public_ids:
        qs = qs.filter(public_id__in=public_ids)
    return qs.update(read_at=timezone.now())

def unread_count(user) -> int:
    if not (user and user.is_authenticated):
        return 0
    return Notification.objects.for_user(user).unread().count()

def _send_notification_email_sync(note_pk: int, template: str, context: dict):
    try:
        from apps.notifications.models import Notification
        from django.core.mail import EmailMultiAlternatives
        from django.template.loader import render_to_string
        note = Notification.objects.select_related('recipient', 'actor').filter(pk=note_pk).first()
        if not note or not note.recipient or not note.recipient.email:
            return

        if note.target_url and note.target_url.startswith('/'):
            site_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000').rstrip('/')
            note.target_url = f"{site_url}{note.target_url}"

        tmpl = template or 'emails/notification.html'
        ctx = {'note': note, 'recipient': note.recipient, 'skillcoin': settings.SKILLCOIN, **context}
        html = render_to_string(tmpl, ctx)
        text = render_to_string('emails/notification.txt', ctx)
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        mail = EmailMultiAlternatives(subject=f'[Skillbridge] {note.title}', body=text, from_email=from_email, to=[note.recipient.email])
        mail.attach_alternative(html, 'text/html')
        mail.send(fail_silently=False)
        Notification.objects.filter(pk=note.pk).update(emailed_at=timezone.now())
        logger.info('Notification email delivered to %s for note %s', note.recipient.email, note.pk)
    except Exception as exc:
        logger.error('Failed to send notification email for note %s: %s', note_pk, exc, exc_info=True)

def _email(note: Notification, template: str, context: dict):
    import sys
    import threading
    is_testing = 'test' in sys.argv or getattr(settings, 'TESTING', False)
    if is_testing:
        _send_notification_email_sync(note.pk, template, context)
    else:
        threading.Thread(target=_send_notification_email_sync, args=(note.pk, template, context), daemon=True).start()

def _clean(metadata: dict) -> dict:
    from decimal import Decimal
    from uuid import UUID

    def _convert(v):
        if isinstance(v, (Decimal, UUID)):
            return str(v)
        if isinstance(v, dict):
            return {str(k): _convert(val) for k, val in v.items()}
        if isinstance(v, (list, tuple, set)):
            return [_convert(val) for val in v]
        return v
    try:
        return {str(k): _convert(v) for k, v in (metadata or {}).items()}
    except Exception:
        return {}
__all__ = ['notify', 'notify_many', 'mark_read', 'unread_count', 'NotificationType']
