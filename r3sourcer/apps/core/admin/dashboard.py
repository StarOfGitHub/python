from django.contrib import admin
from django.contrib.contenttypes.models import ContentType

from .. import forms
from .. import models
from .base import GuardianModelAdmin


class DashboardModuleAdmin(GuardianModelAdmin):

    form = forms.DashboardModuleForm
    fields = ('content_type', 'is_active', 'endpoint', 'description', 'label', 'add_label')

    def get_form(self, request, obj=None, **kwargs):
        excluded_ids = set(models.DashboardModule.objects.values_list('content_type', flat=True))

        if obj:
            excluded_ids.remove(obj.content_type_id)

        form = super(DashboardModuleAdmin, self).get_form(request, obj=obj, **kwargs)
        form.base_fields['content_type'].queryset = ContentType.objects.exclude(
            id__in=excluded_ids
        )
        return form


admin.site.register(models.DashboardModule, DashboardModuleAdmin)
admin.site.register(models.UserDashboardModule)
