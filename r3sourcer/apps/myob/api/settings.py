from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


MYOB_APP = getattr(settings, 'MYOB_APP', None)

if not isinstance(MYOB_APP, dict):
    raise ImproperlyConfigured('Please provide MYOB_APP settings')

for key in ('api_key', 'api_secret', 'api_key_ssl', 'api_secret_ssl'):
    if key not in MYOB_APP:
        raise ImproperlyConfigured('Provide "%s" value for MYOB_APP' % key)
