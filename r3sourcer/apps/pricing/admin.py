from django.db.models import Q
from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline

from r3sourcer.apps.skills.models import Skill, WorkType
from . import models


class RulesInline(GenericTabularInline):
    ct_field = "rule_type"
    ct_fk_field = "rule_id"
    extra = 0
    model = models.DynamicCoefficientRule


class RateCoefficientForRulesAdmin(admin.ModelAdmin):
    inlines = [RulesInline]

    list_display = ('__str__', 'master_company', 'industry')

    def master_company(self, obj):
        extra_obj = models.DynamicCoefficientRule.objects.filter(rule_id=obj.id)
        list_of_obj = []
        for i in extra_obj:
            for item in i.rate_coefficient.rate_coefficient_rels.all():
                list_of_obj.append(item.company)

        return list_of_obj
    master_company.allow_tags = True
    master_company.short_description = 'Master company'

    def industry(self, obj):
        extra_obj = models.DynamicCoefficientRule.objects.filter(
            rule_id=obj.id)
        list_of_obj = []
        for i in extra_obj:
            list_of_obj.append(i.rate_coefficient.industry)
        return list_of_obj


class RateCoefficientAdmin(admin.ModelAdmin):
    list_display = ('name', 'master_company', 'industry', 'rules')

    def master_company(self, obj):
        return [i.company for i in obj.rate_coefficient_rels.all()]


    def rules(self, obj):
        return [str(i) for i in obj.rate_coefficient_rules.all()]

    master_company.allow_tags = True
    master_company.short_description = 'Master company'


class IndustryLanguageInline(admin.TabularInline):
    model = models.IndustryLanguage


class IndustryAdmin(admin.ModelAdmin):
    list_display = ['type']
    search_fields = ('type',)
    inlines = (IndustryLanguageInline,)

class PriceListRateInline(admin.TabularInline):
    model = models.PriceListRate
    extra = 0

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "worktype" and request._obj_:
            industries = request._obj_.company.industries.all()
            kwargs["queryset"] = WorkType.objects.filter(Q(skill_name__industry__in=industries) |
                                                         Q(skill__company=request._obj_.company))
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class PriceListAdmin(admin.ModelAdmin):
    list_display = ['company', 'valid_from', 'valid_until']
    inlines = (PriceListRateInline,)

    def get_form(self, request, obj=None, **kwargs):
        # just save obj reference for future processing in Inline
        request._obj_ = obj
        return super().get_form(request, obj, **kwargs)


admin.site.register(models.Industry, IndustryAdmin)
admin.site.register(models.RateCoefficientGroup)
admin.site.register(models.RateCoefficient, RateCoefficientAdmin)
admin.site.register(models.PriceList, PriceListAdmin)
admin.site.register(models.PriceListRateCoefficient)
admin.site.register(models.RateCoefficientModifier)
admin.site.register(models.DynamicCoefficientRule)
admin.site.register(models.RateCoefficientRel)
admin.site.register(models.PriceListRateModifier)

admin.site.register(models.WeekdayWorkRule, RateCoefficientForRulesAdmin)
admin.site.register(models.OvertimeWorkRule, RateCoefficientForRulesAdmin)
admin.site.register(models.TimeOfDayWorkRule, RateCoefficientForRulesAdmin)
admin.site.register(models.AllowanceWorkRule, RateCoefficientForRulesAdmin)
