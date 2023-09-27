import string
from datetime import timedelta
from itertools import chain

from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

import mock
import pytest
from django_mock_queries.query import MockSet, MockModel

from r3sourcer.apps.sms_interface.models import (
    SMSMessage, SMSRelatedObject,
    )


fake_sms_qs = MockSet(
    MockModel(is_fake=False),
    MockModel(is_fake=True)
)


@pytest.mark.django_db
class TestSMSMessage:

    @pytest.fixture
    def first_sms(self, contact):
        return SMSMessage.objects.create(
            from_number=contact.phone_mobile,
            to_number='+12345678901',
            sent_at=timezone.now(),
            type=SMSMessage.TYPE_CHOICES.RECEIVED,
        )

    @pytest.fixture
    def second_sms(self, contact):
        return SMSMessage.objects.create(
            from_number='+12345678901',
            to_number=contact.phone_mobile,
            sent_at=timezone.now() - timedelta(minutes=30),
            type=SMSMessage.TYPE_CHOICES.SENT,
            check_reply=True,
        )

    @pytest.mark.parametrize(
        ['text', 'expected'],
        chain(
            [('y%ss' % c, True) for c in string.ascii_letters],
            [('ye%s' % c, True) for c in string.ascii_letters],
            [('ye', True), ('yse', True), ('yeah', True), ('yas', True),
             ('yass', True), ('yasss', True), ('yo', True), ('ok', True),
             ('yes, sure', True), ('ok,sure', True), ('', False), ('test', False),
             ('no', False), ],
        )
    )
    def test_positive_answer(self, text, expected):
        sms_message = SMSMessage(text=text)

        assert sms_message.is_positive_answer() is expected

    @pytest.mark.parametrize(
        ['text', 'expected'],
        [('yes', False), ('n', True), ('no', True), ('nah', True),
         ('nop', True), ('nope', True), ('not', True), ('sorry', True),
         ('nay', True), ('no, sorry', True), ('sorry,busy', True),
         ('test', False), ],
    )
    def test_negative_answer(self, text, expected):
        sms_message = SMSMessage(text=text)

        assert sms_message.is_negative_answer() is expected

    @pytest.mark.parametrize(
        ['pos', 'neg', 'expected'],
        [(True, True, True), (True, False, True), (False, True, True),
         (False, False, False), ]
    )
    @mock.patch('r3sourcer.apps.sms_interface.models.SMSMessage.is_positive_answer')
    @mock.patch('r3sourcer.apps.sms_interface.models.SMSMessage.is_negative_answer')
    def test_is_answer(self, mock_neg, mock_pos, pos, neg, expected):
        mock_neg.return_value = neg
        mock_pos.return_value = pos
        sms_message = SMSMessage()

        assert sms_message.is_answer() is expected

    @pytest.mark.parametrize(
        ['text', 'expected'],
        [('stop', True), ('stopall', True), ('cancel', True), ('end', True),
         ('quit', True), ('test', False), ],
    )
    def test_is_stop_message(self, text, expected):
        sms_message = SMSMessage(text=text)

        assert sms_message.is_stop_message() is expected

    @pytest.mark.parametrize(
        ['text', 'expected'],
        [('start', True), ('unstop', True), ('yes', True), ('test', False), ],
    )
    def test_is_start_message(self, text, expected):
        sms_message = SMSMessage(text=text)

        assert sms_message.is_start_message() is expected

    @pytest.mark.parametrize(
        ['text', 'expected'],
        [('log', True), ('login', True), ('log in', True), ('signin', True),
         ('sign in', True), ('test', False), ],
    )
    def test_is_login(self, text, expected):
        sms_message = SMSMessage(text=text)

        assert sms_message.is_login() is expected

    def test_sms_message_str(self):
        sms_message = SMSMessage(from_number='+12345678901',
                                 to_number='+12345678902')

        assert str(sms_message) == '+12345678901 -> +12345678902'

    def test_sms_related_obj_str(self):
        sms_message = SMSMessage.objects.create(sid='test')
        sms_message_second = SMSMessage.objects.create(sid='second')

        sms_related_obj = SMSRelatedObject(sms=sms_message,
                                           content_object=sms_message_second)

        res_str = '{}: {}'.format(_("SMS message"), str(sms_message_second))
        assert str(sms_related_obj) == res_str

    def test_get_all_related_sms(self, ):
        sms_message = SMSMessage.objects.create(sid='test')
        sms_message_second = SMSMessage.objects.create(sid='second')

        related_object = SMSRelatedObject.objects.create(sms=sms_message,
                                        content_object=sms_message_second)

        related_sms = related_object.sms

        assert related_sms == sms_message

    def test_get_sent_by_reply_check_reply(self, first_sms, second_sms):
        assert first_sms.get_sent_by_reply() == second_sms

    def test_get_sent_by_reply_check_reply_false_success(self, first_sms, second_sms):
        second_sms.check_reply = False
        second_sms.save()

        assert first_sms.get_sent_by_reply(check_reply=False) == second_sms

    def test_get_sent_by_reply_check_reply_false_none(self, first_sms, second_sms):
        second_sms.check_reply = False
        second_sms.save()

        assert first_sms.get_sent_by_reply() is None

    def test_get_sent_by_reply_does_not_exists(self, first_sms):
        assert first_sms.get_sent_by_reply() is None

    def test_has_contact_relation(self, first_sms):
        assert first_sms.has_contact_relation()

    def test_has_no_contact_relation(self, contact):
        sms_message = SMSMessage.objects.create(
            from_number='+12345987601',
            to_number='+12345987601',
            sent_at=timezone.now(),
            type=SMSMessage.TYPE_CHOICES.RECEIVED,
        )

        assert not sms_message.has_contact_relation()

    def test_is_late_reply(self, first_sms, second_sms):
        second_sms.check_reply = False
        second_sms.save()

        assert first_sms.is_late_reply()

    def test_not_late_reply_no_sent_sms_without_check_reply(self, first_sms):
        assert not first_sms.is_late_reply()

    def test_not_late_reply_sent_sms_with_check_reply(self, contact, first_sms):
        SMSMessage.objects.create(
            from_number=first_sms.to_number,
            to_number=contact.phone_mobile,
            sent_at=timezone.now() - timedelta(minutes=30),
            type=SMSMessage.TYPE_CHOICES.SENT,
            check_reply=True,
        )

        assert not first_sms.is_late_reply()

    def test_not_late_reply_another_reply_exists(self, contact, first_sms, second_sms):
        SMSMessage.objects.create(
            from_number=first_sms.from_number,
            to_number=first_sms.to_number,
            sent_at=timezone.now() - timedelta(minutes=15),
            type=SMSMessage.TYPE_CHOICES.RECEIVED,
        )

        assert not first_sms.is_late_reply()

    def test_get_related_objects(self, contact, second_sms):
        related_obj = SMSRelatedObject.objects.create(
            sms=second_sms, content_object=contact,
        )
        related_objects = second_sms.get_related_objects()

        assert related_objects == [related_obj.content_object]

    def test_get_related_objects_for_another_sms(self, contact, first_sms, second_sms):
        SMSRelatedObject.objects.create(
            sms=first_sms, content_object=contact,
        )
        related_objects = second_sms.get_related_objects()

        assert len(related_objects) == 0

    def test_get_related_objects_deleted_related(self, contact, second_sms):
        SMSRelatedObject.objects.create(
            sms=second_sms, content_object=contact,
        )
        contact.delete()
        related_objects = second_sms.get_related_objects()

        assert len(related_objects) == 0

    def test_add_related_objects(self, contact, second_sms):
        related_objects = second_sms.add_related_objects(contact)

        assert len(related_objects) == 1
        assert related_objects[0][0].content_object == contact

    def test_add_related_objects_not_model(self, contact, second_sms):
        related_objects = second_sms.add_related_objects(1)

        assert len(related_objects) == 0

    def test_no_check_reply(self, second_sms):
        second_sms.no_check_reply()

        assert not second_sms.check_reply
