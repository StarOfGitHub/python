from django.conf.urls import url
from django.contrib import admin

from easy_select2.widgets import SELECT2_WIDGET_JS, SELECT2_WIDGET_CSS
from guardian.admin import GuardedModelAdminMixin
from guardian.compat import get_model_name

from .. import forms


__all__ = [
    'GuardianModelAdmin'
]


class GuardianModelAdmin(GuardedModelAdminMixin, admin.ModelAdmin):
    def get_obj_perms_user_select_form(self, request):
        return forms.CompanyContactUserManagePermissions

    def get_obj_perms_group_select_form(self, request):
        return forms.GroupManagePermissions

    def get_urls(self):
        urls = admin.ModelAdmin.get_urls(self)
        if self.include_object_permissions_urls:
            info = self.model._meta.app_label, get_model_name(self.model)
            extended_urls = [
                url(r'^(?P<object_pk>.+)/permissions/$',
                    view=self.admin_site.admin_view(self.obj_perms_manage_view),
                    name='%s_%s_permissions' % info),
                url(r'^(?P<object_pk>.+)/permissions/user-manage/(?P<user_id>.+)/$',
                    view=self.admin_site.admin_view(self.obj_perms_manage_user_view),
                    name='%s_%s_permissions_manage_user' % info),
                url(r'^(?P<object_pk>.+)/permissions/group-manage/(?P<group_id>.+)/$',
                    view=self.admin_site.admin_view(self.obj_perms_manage_group_view),
                    name='%s_%s_permissions_manage_group' % info),
            ]
            urls = extended_urls + urls
        return urls

    class Media:
        css = SELECT2_WIDGET_CSS
        js = SELECT2_WIDGET_JS
