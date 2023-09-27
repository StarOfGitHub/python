import logging

import requests

from django.conf import settings


log = logging.getLogger(__name__)


class OpenExchangeClient:

    _base_url = 'https://openexchangerates.org/api/'
    _app_id = settings.OPENEXCHANGE_APP_ID

    def _make_request(self, action, params=None):
        url = '{}{}'.format(self._base_url, action)
        params = params or {}
        params['app_id'] = self._app_id

        response = requests.get(url, params=params)
        try:
            json_response = response.json()

            if json_response.get('error', False):
                log.warning(
                    'Request to %s returns an error. '
                    'message: %s, description: %s',
                    url, json_response.get('message'),
                    json_response.get('description'),
                    exc_info=True
                )
                json_response = None

            return json_response
        except ValueError:
            log.warning('Request to %s failed', url, exc_info=True)

    def latest(self, base=None, symbols=None):
        base = base or settings.DEFAULT_CURRENCY

        params = {'base': base}
        if symbols:
            params['symbols'] = symbols

        response = self._make_request('latest.json', params)
        if not response:
            return

        return response.get('rates')

client = OpenExchangeClient()
