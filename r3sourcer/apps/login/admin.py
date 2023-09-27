from django.contrib import admin

from . import models


class TokenLoginAdmin(admin.ModelAdmin):

    readonly_fields = ('auth_token',)

admin.site.register(models.TokenLogin, TokenLoginAdmin)
