import secrets
from datetime import timedelta

import bcrypt
from django.utils import timezone

from .models import User, Session


def authenticate(email: str, password: str):
    email = (email or '').strip().lower()
    if not email or not password:
        return None
    try:
        u = User.objects.get(email=email)
    except User.DoesNotExist:
        return None
    if not u.active:
        return None
    if not bcrypt.checkpw(password.encode('utf-8'), u.password_hash.encode('utf-8')):
        return None
    return u


def create_session(user_id, days=14):
    token = secrets.token_hex(32)
    expires_at = timezone.now() + timedelta(days=days)
    # sessions table has db defaults, but Django won't use them with managed=False unless we pass values.
    from uuid import uuid4
    Session.objects.create(id=uuid4(), user_id=user_id, token=token, created_at=timezone.now(), expires_at=expires_at)
    return token, expires_at


def get_session(token: str):
    if not token:
        return None
    s = Session.objects.filter(token=token).first()
    if not s:
        return None
    if s.expires_at <= timezone.now():
        return None
    try:
        u = User.objects.get(id=s.user_id)
    except User.DoesNotExist:
        return None
    if not u.active:
        return None
    return {'session': s, 'user': u}


def destroy_session(token: str):
    if not token:
        return
    Session.objects.filter(token=token).delete()


class SessionAuthMiddleware:
    """Attaches request.user_ctx = {user, session} when crm_session cookie is valid."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = request.COOKIES.get('crm_session')
        request.user_ctx = get_session(token)
        return self.get_response(request)
