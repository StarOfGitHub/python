import mock
import pytest

from r3sourcer.apps.login.services import LoginService


class TestLoginServices:

    @pytest.fixture
    def service(self):
        return LoginService()

    @mock.patch('r3sourcer.apps.login.services.send_login_sms')
    def test_send_login_sms(self, mock_send_sms, service, contact):
        service.send_login_sms(contact, redirect_url='')

        mock_send_sms.delay.assert_called_once_with(contact.id, '')
