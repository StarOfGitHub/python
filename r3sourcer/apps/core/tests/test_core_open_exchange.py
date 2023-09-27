import mock
import pytest
import requests_mock

from r3sourcer.apps.core.open_exchange.client import OpenExchangeClient


class TestClient:

    @pytest.fixture
    def client(self):
        return OpenExchangeClient()

    def test_make_request_with_action(self, client):
        base_url = client._base_url

        with requests_mock.Mocker() as mock_request:
            mock_request.get('%s%s' % (base_url, 'latest.json'), json={
                'timestamp': 1449877801,
                'base': 'USD',
                'rates': {
                    'EUR': 0.913492,
                    'AUD': 1.330239,
                    'UAH': 26.5065,
                },
            })

            resp = client._make_request('latest.json')

        assert 'rates' in resp
        assert len(resp['rates']) == 3

    @mock.patch('r3sourcer.apps.core.open_exchange.client.log')
    def test_make_request_wrong_action(self, mock_log, client):
        base_url = client._base_url

        with requests_mock.Mocker() as mock_request:
            mock_request.get('%s%s' % (base_url, 'wrong'), json={
                'error': True,
                'message': 'not_found',
                'description': 'Error description',
            })

            resp = client._make_request('wrong')

        assert resp is None
        assert mock_log.warning.called

    @mock.patch('r3sourcer.apps.core.open_exchange.client.log')
    def test_make_request_wrong_response(self, mock_log, client):
        base_url = client._base_url

        with requests_mock.Mocker() as mock_request:
            mock_request.get('%s%s' % (base_url, 'latest.json'), text='text')

            resp = client._make_request('latest.json')

        assert resp is None
        assert mock_log.warning.called

    @mock.patch.object(OpenExchangeClient, '_make_request')
    def test_latest(self, mock_make_request, client):
        mock_make_request.return_value = {
            'timestamp': 1449877801,
            'base': 'USD',
            'rates': {
                'EUR': 0.913492,
                'AUD': 1.330239,
                'UAH': 26.5065,
            },
        }

        rates = client.latest()

        assert len(rates) == 3
        assert 'UAH' in rates

    @mock.patch.object(OpenExchangeClient, '_make_request')
    def test_latest_specific_currencies(self, mock_make_request, client):
        mock_make_request.return_value = {
            'timestamp': 1449877801,
            'base': 'USD',
            'rates': {
                'EUR': 0.913492,
                'AUD': 1.330239,
                'UAH': 26.5065,
            },
        }

        rates = client.latest(symbols=['EUR', 'AUD', 'UAH'])

        assert len(rates) == 3
        assert 'UAH' in rates

    @mock.patch.object(OpenExchangeClient, '_make_request')
    def test_latest_empty_rates(self, mock_make_request, client):
        mock_make_request.return_value = None

        rates = client.latest()

        assert rates is None
