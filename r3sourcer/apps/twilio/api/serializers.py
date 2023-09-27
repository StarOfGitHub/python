from r3sourcer.apps.core.api import serializers as core_serializers
from r3sourcer.apps.twilio import models


class TwilioPhoneNumberSerializer(core_serializers.ApiBaseModelSerializer):
    class Meta:
        model = models.TwilioPhoneNumber
        fields = (
            'sid', 'phone_number', 'friendly_name', 'company', 'sms_enabled',
            'mms_enabled', 'voice_enabled', 'is_default',
        )
