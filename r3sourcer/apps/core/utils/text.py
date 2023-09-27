from inflector import Inflector, English

from django.utils import six
from django.utils.functional import lazy
from django.utils.module_loading import import_string

try:  # pragma: no cover
    from django.utils.text import format_lazy  # Django 1.11+
except ImportError:  # pragma: no cover
    def format_wrapper(format_text, *args, **kwargs):
        return format_text.format(*args, **kwargs)

    format_lazy = lazy(format_wrapper, six.text_type)


def pluralize(singular, language=English):
    if isinstance(language, str):
        language = import_string(language)

    inflector = Inflector(language)
    return inflector.pluralize(singular)
