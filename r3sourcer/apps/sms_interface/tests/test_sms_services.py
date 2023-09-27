from datetime import datetime

import freezegun
import mock
import pytest

from django.utils import timezone

from r3sourcer.apps.core.models import Contact
from r3sourcer.apps.core.service import factory
from r3sourcer.apps.sms_interface.exceptions import SMSServiceError
from r3sourcer.apps.sms_interface.models import SMSMessage
from r3sourcer.apps.sms_interface.services import (
    BaseSMSService, FakeSMSService
)
from r3sourcer.apps.sms_interface.utils import get_sms_service


class SMSTestService(BaseSMSService):

    def process_sms_send(self, sms_message):
        pass  # pragma: no cover

    def process_sms_fetch(self):
        pass  # pragma: no cover


@pytest.mark.django_db
class TestSMSServices:

    @pytest.fixture
    @freezegun.freeze_time(datetime(2017, 1, 1))
    def fake_sms(self, contact):
        return SMSMessage.objects.create(
            from_number=contact.phone_mobile,
            to_number='+12345678901',
            text='fake message',
            is_fake=True,
            check_reply=True,
            sent_at=timezone.now(),
        )

    @pytest.fixture
    def service(self):
        return SMSTestService()

    @pytest.fixture
    def sent_sms(self):
        sent_sms = mock.Mock()
        sent_sms.get_related_objects.return_value = []

        mock_related = mock.PropertyMock()
        type(sent_sms).related_object = mock_related

        return sent_sms

    # @pytest.fixture
    # def sms_activity(self):
    #     ac = mock.Mock()
    #     ac.create_activity = mock.Mock()

    #     from_contact = mock.PropertyMock()
    #     to_contact = mock.PropertyMock()
    #     type(ac).from_contact = from_contact
    #     type(ac).to_contact = to_contact

    #     return ac

    def test_get_default_fake_sms_service(self):
        service = get_sms_service()

        assert isinstance(service, FakeSMSService)

    def test_get_service_by_name(self):
        service_class_name = '%s.%s' % (SMSTestService.__module__,
                                        SMSTestService.__name__)
        service = get_sms_service(service_class_name)

        assert isinstance(service, SMSTestService)

    def test_get_service_by_name_settings_set(self, settings):
        service_class_name = '%s.%s' % (SMSTestService.__module__,
                                        SMSTestService.__name__)
        settings.SMS_SERVICE_ENABLED = True
        settings.SMS_SERVICE_CLASS = '%s.%s' % (
            FakeSMSService.__module__, FakeSMSService.__name__
        )
        service = get_sms_service(service_class_name)

        assert isinstance(service, SMSTestService)

    def test_get_service_from_settings(self, settings):
        service_class_name = '%s.%s' % (SMSTestService.__module__,
                                        SMSTestService.__name__)
        settings.SMS_SERVICE_ENABLED = True
        settings.SMS_SERVICE_CLASS = service_class_name
        service = get_sms_service()

        assert isinstance(service, SMSTestService)

    def test_get_fake_service_settings_sms_service_disabled(self, settings):
        service_class_name = '%s.%s' % (SMSTestService.__module__,
                                        SMSTestService.__name__)
        settings.SMS_SERVICE_ENABLED = False
        settings.SMS_SERVICE_CLASS = service_class_name
        service = get_sms_service()

        assert isinstance(service, FakeSMSService)

    def test_sms_service_fetch(self, fake_sms):
        service = SMSTestService()
        service.process_sms_fetch = mock.Mock()
        service.process_sms_fetch.return_value = [fake_sms]
        service._process_sms = mock.Mock()
        service.fetch()

        assert service.process_sms_fetch.called
        assert service._process_sms.called

    @mock.patch('r3sourcer.apps.sms_interface.services.logger')
    def test_sms_service_fetch_error(self, mock_log, fake_sms):
        service = SMSTestService()
        service.process_sms_fetch = mock.Mock()
        service.process_sms_fetch.side_effect = SMSServiceError
        service._process_sms = mock.Mock()
        service.fetch()

        assert service.process_sms_fetch.called
        assert mock_log.exception.called
        assert not service._process_sms.called

    @mock.patch('r3sourcer.apps.sms_interface.services.get_site_master_company')
    @mock.patch.object(factory, 'get_instance')
    @mock.patch.object(FakeSMSService, 'can_send_sms')
    @mock.patch('r3sourcer.apps.sms_interface.utils.get_sms_service', return_value=FakeSMSService)
    def test_fake_sms_service_send(
        self, mock_get_service, mock_can_send, mock_factory, mock_master, twilio_account, phone_number, company
    ):
        company.sms_enabled=True
        mock_can_send.return_value = company
        mock_master.return_value = company

        service = FakeSMSService()
        service.send(
            from_number=phone_number.phone_number,
            to_number='+12345678901',
            text='test message'
        )

        sms_message = SMSMessage.objects.all().first()
        assert sms_message.sid.startswith('FAKE')

    @mock.patch.object(factory, 'get_instance')
    @mock.patch.object(SMSTestService, 'can_send_sms')
    @mock.patch.object(SMSTestService, 'process_sms_send')
    def test_send_sms_text(
        self, mock_sms_send, mock_can_send, mock_factory, contact, twilio_account, phone_number, company
    ):
        company.sms_enabled=True
        company.sms_balance.balance = 10
        mock_sms_send.return_value = None
        mock_can_send.return_value = company

        service = SMSTestService()
        service.send(from_number=phone_number.phone_number,
                     to_number=contact.phone_mobile,
                     text='test message')

        assert SMSMessage.objects.all().count() == 1
        assert mock_sms_send.called

    @mock.patch.object(factory, 'get_instance')
    @mock.patch.object(SMSTestService, 'can_send_sms')
    @mock.patch.object(SMSTestService, 'process_sms_send')
    def test_send_sms_text_service_exception(
        self, mock_sms_send, mock_can_send, mock_factory, contact, twilio_account, phone_number, company
    ):
        company.sms_enabled=True
        company.sms_balance.balance = 10
        mock_sms_send.side_effect = SMSServiceError
        mock_can_send.return_value = company

        service = SMSTestService()
        service.send(
            from_number=phone_number.phone_number,
            to_number=contact.phone_mobile,
            text='test message',
            delivery_timeout=1,
        )

        sms_message = SMSMessage.objects.all().first()
        assert sms_message.error_message is not None

    @mock.patch.object(factory, 'get_instance')
    def test_fake_sms_service_fetch(self, mock_factory, fake_sms):
        sms_service = FakeSMSService()
        sms_service.fetch()

        assert SMSMessage.objects.all().count() == 1
        assert not SMSMessage.objects.filter(is_fake=True).exists()

    @mock.patch('r3sourcer.apps.sms_interface.services.logger')
    def test_process_not_new_sms(self, mock_log, fake_sms):
        fake_sms.is_fetched = True
        fake_sms.save()

        service = SMSTestService()
        service._process_sms(fake_sms)

        assert SMSMessage.objects.all().count() == 1
        assert mock_log.info.called

    @mock.patch.object(factory, 'get_instance')
    @mock.patch.object(SMSMessage, 'get_sent_by_reply')
    def test_process_sms_received(self, mock_sent_by_reply, mock_factory, service, fake_sms):
        fake_sms.status = SMSMessage.STATUS_CHOICES.RECEIVED
        service._process_sms(fake_sms)

        assert mock_sent_by_reply.called

    @mock.patch.object(factory, 'get_instance')
    @mock.patch('r3sourcer.apps.sms_interface.services.logger')
    def test_process_new_sms(self, mock_log, mock_factory, fake_sms):
        service = SMSTestService()
        service._process_sms(fake_sms)

        assert SMSMessage.objects.all().count() == 1
        assert mock_log.info.called

    @mock.patch('r3sourcer.apps.sms_interface.services.logger')
    def test_process_sms_answer_no_contact_relation(self, mock_log, fake_sms):
        mock_contact_relation = mock.Mock()
        mock_contact_relation.return_value = False
        fake_sms.has_contact_relation = mock_contact_relation

        service = SMSTestService()

        service.process_sms_answer(fake_sms, None)

        assert mock_log.error.called

    def test_get_related_object_exists(self, service, fake_sms,
                                       sent_sms):
        related = sent_sms.get_related_objects()

        assert related is not None

    def test_is_positive_true(self, service, fake_sms):
        with mock.patch.object(SMSMessage, 'is_positive_answer', return_value=True):
            positive = service._is_positive(fake_sms)

            assert positive

    def test_is_positive_false(self, service, fake_sms):
        with mock.patch.object(SMSMessage, 'is_positive_answer', return_value=False):
            with mock.patch.object(SMSMessage, 'is_negative_answer', return_value=True):
                positive = service._is_positive(fake_sms)

                assert not positive

    def test_is_positive_none(self, service, fake_sms):
        with mock.patch.object(SMSMessage, 'is_positive_answer', return_value=False):
            with mock.patch.object(SMSMessage, 'is_negative_answer', return_value=False):
                positive = service._is_positive(fake_sms)

                assert positive is None

    def test_process_sms_answer_sms_sent_exists(self, service, fake_sms,
                                                sent_sms):
        fake_sms_mock_kwargs = {
            'target': SMSMessage,
            'attribute': 'add_related_objects',
            'return_value': None,
        }
        with mock.patch.object(**fake_sms_mock_kwargs) as mock_add_related:
            service.process_sms_answer(fake_sms, sent_sms)

            assert mock_add_related.called
            assert sent_sms.no_check_reply.called

    @mock.patch.object(SMSMessage, 'add_related_objects', return_value=None)
    @mock.patch.object(SMSMessage, 'is_late_reply', return_value=True)
    def test_process_sms_answer_sms_sent_not_exists_late_reply(
                self, mock_late_reply, mock_add_related, service, fake_sms,
                sent_sms
            ):
        fake_sms_mock_kwargs = {
            'target': SMSMessage,
            'attribute': 'get_sent_by_reply',
            'return_value': sent_sms,
        }
        with mock.patch.object(**fake_sms_mock_kwargs) as mock_sent_by_reply:
            service.process_sms_answer(fake_sms, None)

            assert mock_sent_by_reply.called
            assert mock_add_related.called
            assert sent_sms.late_reply == fake_sms

    @mock.patch.object(SMSMessage, 'add_related_objects', return_value=None)
    @mock.patch.object(SMSMessage, 'is_late_reply', return_value=False)
    def test_process_sms_answer_sms_sent_not_exists_not_late_reply(
                self, mock_late_reply, mock_add_related, service, fake_sms,
                sent_sms
            ):
        fake_sms_mock_kwargs = {
            'target': SMSMessage,
            'attribute': 'get_sent_by_reply',
            'return_value': sent_sms,
        }
        with mock.patch.object(**fake_sms_mock_kwargs) as mock_sent_by_reply:
            service.process_sms_answer(fake_sms, None)

            assert not mock_sent_by_reply.called
            assert not mock_add_related.called

    # @mock.patch.object(SMSTestService, 'process_sms_reply')
    # def test_process_sms_answer_can_process(
    #             self, service, fake_sms, sent_sms
    #         ):
    #     related = mock.Mock()
    #     mock_related = mock.PropertyMock()
    #     mock_related.return_value = related
    #     service.process_sms_answer(fake_sms, None)

    #     assert related.process_sms_reply.called

    # @mock.patch.object(SMSTestService, '_get_related_object')
    # def test_process_sms_answer_cannot_process(
    #             self, mock_related, service, fake_sms, sent_sms, sms_activity
    #         ):
    #     mock_related.return_value = None
    #     service.process_sms_answer(fake_sms, None, sms_activity)

    #     assert not mock_related.process_sms_reply.called

    # @mock.patch.object(SMSTestService, 'send')
    # @mock.patch.object(SMSMessage, 'add_related_objects')
    # def test_process_ambiguous_answer_has_sent_message(
    #             self, mock_add_related_objs, mock_send,
    #             service, fake_sms, sent_sms, sms_activity
    #         ):
    #     service.process_ambiguous_answer(fake_sms, sent_sms, sms_activity)

    #     assert mock_add_related_objs.called
    #     assert sent_sms.get_related_objects.called

    # @mock.patch.object(SMSTestService, 'send')
    # def test_process_ambiguous_answer_create_activity(
    #             self, mock_send, service, fake_sms, sms_activity
    #         ):
    #     service.process_ambiguous_answer(fake_sms, None, sms_activity)

    #     assert sms_activity.create_activity.called

    # @mock.patch.object(SMSTestService, 'send')
    # @mock.patch('r3sourcer.apps.sms_interface.services.get_phone_number')
    # def test_process_ambiguous_answer_to_from_company_contact_exists(
    #     self, mock_get_phone, mock_send, service, fake_sms, sms_activity
    # ):
    #     # sms_activity.from_contact.company_contact.last.return_value = None

    #     service.process_ambiguous_answer(fake_sms, None, sms_activity)

    #     message_text = '{}: {}\n{}'.format(
    #         str(sms_activity.from_contact), fake_sms.from_number, fake_sms.text
    #     )

    #     mock_send.assert_called_once_with(
    #         sms_activity.to_contact.phone_mobile, message_text,
    #         sms_activity.from_contact, from_number=mock_get_phone.return_value,
    #         check_reply=False
    #     )

    @mock.patch.object(Contact, 'objects')
    @mock.patch.object(SMSMessage, 'is_answer', return_value=False)
    @mock.patch.object(SMSMessage, 'is_stop_message', return_value=True)
    def test_process_sms_stop_message(
                self, mock_is_stop, mock_is_answer, mock_objects, service, fake_sms
            ):
        fake_sms.type = SMSMessage.TYPE_CHOICES.RECEIVED

        mock_update = mock.Mock()
        mock_objects.filter.return_value = mock_update

        service._process_sms(fake_sms)

        mock_update.update.assert_called_once_with(is_available=False)

    @mock.patch.object(Contact, 'objects')
    @mock.patch.object(SMSMessage, 'is_answer', return_value=False)
    @mock.patch.object(SMSMessage, 'is_start_message', return_value=True)
    def test_process_sms_start_message(
                self, mock_is_stop, mock_is_answer, mock_objects, service, fake_sms
            ):
        fake_sms.type = SMSMessage.TYPE_CHOICES.RECEIVED

        mock_update = mock.Mock()
        mock_objects.filter.return_value = mock_update

        service._process_sms(fake_sms)

        mock_update.update.assert_called_once_with(is_available=True)

    # @mock.patch.object(Contact, 'objects')
    # @mock.patch.object(SMSMessage, 'is_answer', return_value=False)
    # @mock.patch.object(SMSMessage, 'is_login', return_value=True)
    # @mock.patch('r3sourcer.apps.sms_interface.services.factory.get_instance')
    # def test_process_sms_login_message_without_contact(
    #             self, mock_get_instance, mock_is_stop, mock_is_answer,
    #             mock_objects, service, fake_sms
    #         ):
    #     fake_sms.type = SMSMessage.TYPE_CHOICES.RECEIVED

    #     mock_update = mock.Mock()
    #     mock_objects.filter.return_value = mock_update

    #     mock_send_sms = mock.Mock()
    #     mock_get_instance.return_value = mock_send_sms

    #     service._process_sms(fake_sms)

    #     mock_objects.filter.assert_called_once_with(phone_mobile=fake_sms.from_number)
    #     assert mock_send_sms.send_login_sms.called

    # @mock.patch.object(SMSTestService, 'process_ambiguous_answer')
    # @mock.patch.object(SMSMessage, 'is_answer', return_value=False)
    # def test_process_sms_ambiguous_answer(
    #             self, mock_is_answer, mock_process_answer, service, fake_sms
    #         ):
    #     fake_sms.type = SMSMessage.TYPE_CHOICES.RECEIVED

    #     mock_activity_service = mock.PropertyMock()
    #     SMSTestService.activity_service = mock_activity_service

    #     service._process_sms(fake_sms)

    #     assert mock_process_answer.called

    @mock.patch.object(SMSTestService, 'send')
    def test_send_tpl_slug(self, mock_send, service, sms_template, candidate_contact, company):
        service.send_tpl(candidate_contact.contact, company, 'sms-template')

        mock_send.assert_called_with(candidate_contact.contact.phone_mobile, 'template', None, [])

    @mock.patch('r3sourcer.apps.sms_interface.services.logger')
    @mock.patch.object(SMSTestService, 'send')
    def test_send_tpl_not_found(self, mock_send, mock_log, service, candidate_contact, company):
        service.send_tpl(candidate_contact.contact, company, 'sms')

        assert mock_log.exception.called
        assert not mock_send.called
