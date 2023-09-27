import sys
import types

from django.apps import apps
from django.conf import settings

from .manager import get_endless_logger
from .services import LocationLogger
from .query import get_logger_queryset
from .decorators import __name__ as __decorators_name__


endless_logger = get_endless_logger()
location_logger = LocationLogger()


def autodiscover():
    """
    Discovers models for logging and rewrite methods save and delete for
    every discovered model which needs logging
    """
    if not settings.LOGGER_ENABLED:
        return

    for model in apps.get_models():
        if hasattr(model, "use_logger") and getattr(model, "use_logger")():
            for method_name in ["save", "delete"]:
                decorator_name = "{}_decorator".format(method_name)
                setattr(model, method_name,
                        getattr(sys.modules[__decorators_name__], decorator_name)(getattr(model, method_name),
                                                                                  endless_logger))

            model.objects.get_queryset = types.MethodType(get_logger_queryset, model.objects)
