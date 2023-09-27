from django.utils.translation import ugettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import APIException


class TokenAlreadyUsed(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = _('The link has already been used.')
    default_code = 'authentication_failed'
