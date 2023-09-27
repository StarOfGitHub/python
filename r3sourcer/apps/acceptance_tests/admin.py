from django.contrib import admin

from . import models

admin.site.register(models.AcceptanceTest)
admin.site.register(models.AcceptanceTestAnswer)
admin.site.register(models.AcceptanceTestQuestion)
admin.site.register(models.AcceptanceTestSkill)
admin.site.register(models.AcceptanceTestTag)
admin.site.register(models.AcceptanceTestIndustry)
admin.site.register(models.AcceptanceTestWorkflowNode)
