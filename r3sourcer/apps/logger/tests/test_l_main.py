from django.db.models import QuerySet

from r3sourcer.apps.logger.main import autodiscover
from r3sourcer.apps.logger.query import LoggerQuerySet


class TestAutodiscover:
    def test_autodiscover(self, test_model_for_autodiscover, settings):
        settings.LOGGER_ENABLED = True
        assert isinstance(test_model_for_autodiscover.objects.get_queryset(), QuerySet)
        assert not isinstance(test_model_for_autodiscover.objects.get_queryset(), LoggerQuerySet)
        autodiscover()
        assert isinstance(test_model_for_autodiscover.objects.get_queryset(), LoggerQuerySet)
