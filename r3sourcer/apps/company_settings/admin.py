from django.contrib import admin

from . import models


class MYOBSettingsAdmin(admin.ModelAdmin):
    list_display = ('company',)
    search_fields = ('company__name',)


class CompanySettings(admin.ModelAdmin):
    list_display = ('company',)


admin.site.register(models.MYOBSettings, MYOBSettingsAdmin)
admin.site.register(models.CompanySettings, CompanySettings)
admin.site.register(models.MYOBAccount)
admin.site.register(models.SAASCompanySettings)
