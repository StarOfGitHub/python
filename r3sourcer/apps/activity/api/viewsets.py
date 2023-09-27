from r3sourcer.apps.activity.models import Activity
from r3sourcer.apps.core.api.viewsets import BaseApiViewset


class ActivityViewset(BaseApiViewset):
    def get_queryset(self):
        qs = Activity.objects.all()
        if not self.request.user.is_superuser:
            qs = qs.filter(
                contact__user_id=self.request.user.id
            )
        return qs
