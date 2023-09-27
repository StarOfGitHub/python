from r3sourcer.apps.core.api.router import router

from r3sourcer.apps.core.api import endpoints as core_endpoints
from r3sourcer.apps.twilio import models
from r3sourcer.apps.twilio.api import serializers, viewsets


class TwilioPhoneNumberEndpoint(core_endpoints.ApiEndpoint):

    model = models.TwilioPhoneNumber
    serializer = serializers.TwilioPhoneNumberSerializer
    base_viewset = viewsets.TwilioPhoneNumberViewset


router.register(endpoint=TwilioPhoneNumberEndpoint())
