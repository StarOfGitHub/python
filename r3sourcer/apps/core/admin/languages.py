from django.contrib import admin

from .core import BaseAdminPermissionMixin
from ..models import Language


class LanguageAdmin(BaseAdminPermissionMixin, admin.ModelAdmin):

    list_display = ('name', 'alpha_2')
    search_fields = ('name', 'alpha_2')


admin.site.register(Language, LanguageAdmin)
