from mock import patch

from r3sourcer.apps.core_adapter.utils import api_reverse


class TestApiReverse:

    @patch('r3sourcer.apps.core_adapter.utils.reverse',
           return_value='/countries')
    def test_api_reverse(self, mock_reverse):
        url = api_reverse('countries')

        assert url == '/countries'
