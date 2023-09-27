from r3sourcer.apps.core.api.router import router

from r3sourcer.apps.core.api.endpoints import ApiEndpoint
from r3sourcer.apps.company_settings.api import filters
from r3sourcer.apps.company_settings.models import GlobalPermission


class GlobalPermissionEndpoint(ApiEndpoint):

    model = GlobalPermission
    filter_class = filters.GlobalPermissiontFilter

    serializer_fields = ('id', 'name', )

    search_fields = ['name']


router.register(endpoint=GlobalPermissionEndpoint())
