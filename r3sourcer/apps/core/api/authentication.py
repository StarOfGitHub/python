from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from django.utils.translation import ugettext_lazy as _
from rest_framework import exceptions
from oauth2_provider_jwt import authentication


class JWTAuthentication(authentication.JWTAuthentication):
    def authenticate_credentials(self, payload):
        if getattr(settings, 'JWT_AUTH_DISABLED', False):
            return AnonymousUser()

        User = get_user_model()
        user_id = payload.get('user_id')

        if not user_id:
            msg = _('Invalid payload.')
            raise exceptions.AuthenticationFailed(msg)

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            msg = _('Invalid signature.')
            raise exceptions.AuthenticationFailed(msg)

        if not user.is_active:
            msg = _('User account is disabled.')
            raise exceptions.AuthenticationFailed(msg)

        return user
