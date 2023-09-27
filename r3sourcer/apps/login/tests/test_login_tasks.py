import mock
import pytest

from r3sourcer.apps.login.tasks import (
    send_login_sms, send_login_email, get_contact, send_login_token, send_login_message
)
from r3sourcer.apps.login.models import TokenLogin


@pytest.mark.django_db
class TestSendFuncs:

    def test_get_existed_contact(self, contact):
        contact = get_contact(contact.id)

        assert contact.id == contact.id

    @mock.patch('r3sourcer.apps.login.tasks.logger')
    def test_get_not_existed_contact(self, mock_logger):
        contact = get_contact('11111111-1111-1111-1111-111111111111')

        assert contact is None

    @mock.patch('r3sourcer.apps.login.tasks.get_site_master_company')
    def test_send_login_token(self, mocked_company, contact, company):
        send_func = mock.Mock()
        mocked_company.return_value = company

        send_login_token(contact, send_func, '', redirect_url='/', type_=TokenLogin.TYPES.email)

        assert mocked_company.called
        assert send_func.called
        assert TokenLogin.objects.filter(contact=contact).count() == 1

    @mock.patch('r3sourcer.apps.login.tasks.send_login_email')
    def test_send_message_for_email(self, mock_email_send, contact):
        send_login_message(contact.email, contact)

        assert mock_email_send.delay.called or mock_email_send.apply_async.called

    @mock.patch('r3sourcer.apps.login.tasks.send_login_sms')
    def test_send_message_for_phone_number(self, mock_sms_send, contact):
        send_login_message(contact.phone_mobile.as_e164, contact)

        assert mock_sms_send.delay.called or mock_sms_send.apply_async.called


@pytest.mark.django_db
class TestSendLoginSMS:

    @mock.patch('r3sourcer.apps.login.tasks.send_login_token')
    def test_send_login_sms_to_existed_contact(self, mock_send, contact):
        send_login_sms(contact.id)

        assert mock_send.called

    @mock.patch('r3sourcer.apps.login.tasks.send_login_token')
    def test_send_login_sms_to_not_existed_contact(self, mock_send):
        send_login_sms('11111111-1111-1111-1111-111111111111')

        assert not mock_send.called


@pytest.mark.django_db
class TestSendLoginEmail:

    @mock.patch('r3sourcer.apps.login.tasks.send_login_token')
    def test_send_login_sms_to_existed_contact(self, mock_send, contact):
        send_login_email(contact.id)

        assert mock_send.called

    @mock.patch('r3sourcer.apps.login.tasks.send_login_token')
    def test_send_login_sms_to_not_existed_contact(self, mock_send):
        send_login_email('11111111-1111-1111-1111-111111111111')

        assert not mock_send.called
