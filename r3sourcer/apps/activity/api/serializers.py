from r3sourcer.apps.activity.models import Activity
from r3sourcer.apps.core.api.serializers import (
    ApiBaseModelSerializer,
    RELATED_DIRECT,
)


class ActivitySerializer(ApiBaseModelSerializer):

    class Meta:
        model = Activity
        fields = (
            'id',
            'contact',
            'done',
            'priority',
            'entity_object_id',
            'entity_object_name',
            'starts_at',
            'ends_at',
        )
        extra_kwargs = {'contact': {'read_only': True}}
        related = RELATED_DIRECT
