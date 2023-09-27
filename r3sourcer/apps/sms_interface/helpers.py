import math

from django.conf import settings
from django.db.models import Q

from r3sourcer.apps.sms_interface.models import PhoneNumber, SMSMessage
from r3sourcer.helpers.datetimes import utc_now


def get_phone_number(company=None):
    qry = Q()
    if company is not None:
        qry = Q(company=company)
    return PhoneNumber.objects.filter(qry).last()


def get_sms(from_number, to_number, text, reply_timeout=None,
            check_reply=True, delivery_timeout=None, company=None, **kwargs):
    assert to_number, "Number is required"
    assert text, "Message text is required"

    number_of_segments = math.ceil(len(text) / settings.SMS_SEGMENT_SIZE)
    params = dict(
        text=text,
        from_number=from_number,
        to_number=to_number,
        check_delivered=True,
        sent_at=utc_now(),
        check_reply=check_reply,
        type=SMSMessage.TYPE_CHOICES.SENT,
        company=company,
        segments=number_of_segments,
        template=kwargs.get('template'),
    )

    if reply_timeout is not None:
        params['reply_timeout'] = reply_timeout

    if delivery_timeout is not None:
        params['delivery_timeout'] = delivery_timeout

    return SMSMessage(**params)
