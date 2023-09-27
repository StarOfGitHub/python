import mock
import pytest

from r3sourcer.apps.core.models import CurrencyExchangeRates
from r3sourcer.apps.core.open_exchange.client import OpenExchangeClient
from r3sourcer.apps.core.tasks import exchange_rates_sync


@pytest.mark.django_db
class TestExchangeRateSync:

    @mock.patch.object(OpenExchangeClient, '_make_request')
    def test_exchange_rate_sync(self, mock_make_request):
        mock_make_request.return_value = {
            'timestamp': 1449877801,
            'base': 'USD',
            'rates': {
                'EUR': 0.913492,
                'AUD': 1.330239,
                'UAH': 26.5065,
            },
        }

        exchange_rates_sync()

        assert CurrencyExchangeRates.objects.filter(to_currency='AUD').exists()

    @mock.patch.object(OpenExchangeClient, '_make_request')
    def test_exchange_rate_sync_no_rates(self, mock_make_request):
        mock_make_request.return_value = None

        exchange_rates_sync()

        assert not CurrencyExchangeRates.objects.exists()
