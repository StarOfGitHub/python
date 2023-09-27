from django.utils import six
from django.utils.functional import lazy

try:
    from django.core.urlresolvers import reverse  # pragma: no cover
except ImportError:  # pragma: no cover
    # Django 1.11+
    from django.urls import reverse  # pragma: no cover


def api_reverse(endpoint, methodname='list', *args, **kwargs):
    return reverse('api:{}-{}'.format(endpoint, methodname),
                   kwargs=kwargs)  # pragma: no cover


api_reverse_lazy = lazy(api_reverse, six.text_type)
