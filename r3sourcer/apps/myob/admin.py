from django.contrib import admin
from django.utils.translation import ugettext_lazy as _

from .models import (
    MYOBRequestLog, MYOBAuthData, MYOBCompanyFile,
    MYOBCompanyFileToken, MYOBSyncObject,
)


class MYOBRequestLogAdmin(admin.ModelAdmin):
    list_display = (
        'method', 'url', 'resp_status_code', 'created', 'modified'
    )


class MYOBAuthDataAdmin(admin.ModelAdmin):
    list_display = (
        'client_id',
        'myob_user_uid',
        'myob_user_username',
        'expires_at',
        'created',
        'modified',
        'company_id',
        'user_id',
    )


class MYOBCompanyFileAdmin(admin.ModelAdmin):
    list_display = (
        'cf_name', 'cf_id', 'cf_uri', 'created', 'modified'
    )


class MYOBCompanyFileTokenAdmin(admin.ModelAdmin):
    list_display = (
        'cf_token', 'auth_data', 'company_file', 'created', 'modified'
    )


class MYOBSyncObjectAdmin(admin.ModelAdmin):
    list_display = (
        'app', 'model', 'record', 'direction', 'synced_at'
    )
    actions = ['confirm_legacy', 'reject_legacy']

    def confirm_legacy(self, request, queryset):
        queryset.update(legacy_confirmed=True)
        self.message_user(request, _("Legacy confirmation updated."))
    confirm_legacy.short_description = _("Confirm legacy object match.")

    def reject_legacy(self, request, queryset):
        queryset.update(legacy_confirmed=False)
        self.message_user(request, _("Legacy confirmation updated."))
    reject_legacy.short_description = _("Reject legacy object match.")


admin.site.register(MYOBRequestLog, MYOBRequestLogAdmin)
admin.site.register(MYOBAuthData, MYOBAuthDataAdmin)
admin.site.register(MYOBCompanyFile, MYOBCompanyFileAdmin)
admin.site.register(MYOBCompanyFileToken, MYOBCompanyFileTokenAdmin)
admin.site.register(MYOBSyncObject, MYOBSyncObjectAdmin)
