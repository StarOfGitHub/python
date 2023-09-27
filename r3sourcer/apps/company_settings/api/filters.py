from django_filters.rest_framework import FilterSet

from r3sourcer.apps.company_settings.models import GlobalPermission


class GlobalPermissiontFilter(FilterSet):

    class Meta:
        model = GlobalPermission
        fields = ['user']
