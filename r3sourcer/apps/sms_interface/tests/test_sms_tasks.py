import pytest

import mock

from r3sourcer.apps.sms_interface.exceptions import SMSServiceError
from r3sourcer.apps.sms_interface.tasks import fetch_remote_sms


@pytest.mark.django_db
class TestTasks:

    @mock.patch('r3sourcer.apps.sms_interface.tasks.get_sms_service')
    def test_fetch_sms_messages(self, mock_get_service, fake_sms):
        mock_get_service.return_value.fetch.return_value = None

        fetch_remote_sms()

        assert mock_get_service.return_value.fetch.called

    @mock.patch('r3sourcer.apps.sms_interface.tasks.logger')
    @mock.patch('r3sourcer.apps.sms_interface.tasks.get_sms_service')
    def test_fetch_sms_messages_error(self, mock_get_service, mock_logger):
        mock_get_service.return_value.fetch.side_effect = SMSServiceError

        fetch_remote_sms()

        assert mock_logger.exception.called
