import mock
import pytest

from r3sourcer.apps.email_interface.services import BaseEmailService
from r3sourcer.apps.email_interface.tasks import send_email_default


class EmailTestService(BaseEmailService):

    def process_email_send(self, email_message):
        pass  # pragma: no cover


@pytest.mark.django_db
class TestSendEmailDefault:

    @mock.patch('r3sourcer.apps.email_interface.tasks.get_email_service')
    def test_send_email_default_text(self, mock_service):
        send_email_default('test@test.tt', 'subject', 'text')

        assert mock_service.return_value.send.called

    @mock.patch('r3sourcer.apps.email_interface.tasks.get_email_service')
    def test_send_email_default_template(self, mock_service):
        send_email_default('test@test.tt', email_tpl='email-template')

        assert mock_service.return_value.send_tpl.called
