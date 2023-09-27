from r3sourcer.apps.activity.models import Activity
from r3sourcer.apps.core.api.router import router

from r3sourcer.apps.core.api.endpoints import ApiEndpoint
from r3sourcer.apps.activity.api import viewsets, filters, serializers


class ActivityEndpoint(ApiEndpoint):
    model = Activity
    base_viewset = viewsets.ActivityViewset
    filter_class = filters.ActivityFilter
    serializer = serializers.ActivitySerializer


router.register(endpoint=ActivityEndpoint())
