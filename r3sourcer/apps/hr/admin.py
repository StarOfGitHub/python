from django.contrib import admin
from django.db.models import Q, Count
from r3sourcer.apps.candidate import models as candidate_models
from . import models


class TimeSheetRateInline(admin.TabularInline):
    model = models.TimeSheetRate
    extra = 0

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "worktype" and request._obj_:
            kwargs["queryset"] = models.WorkType.objects.filter(Q(skill_name=request._obj_.job_offer.shift.date.job.position.name) | \
                                                                Q(skill=request._obj_.job_offer.shift.date.job.position))
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class TimeSheetAdmin(admin.ModelAdmin):
    list_display = ('created_at', '__str__', 'regular_company', 'shift_started_at')
    ordering = ['-shift_started_at']
    inlines = [TimeSheetRateInline]

    def get_form(self, request, obj=None, **kwargs):
        request._obj_ = obj
        return super().get_form(request, obj, **kwargs)


class JobRateInline(admin.TabularInline):
    model = models.JobRate
    extra = 0

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "worktype" and request._obj_:
            kwargs["queryset"] = models.WorkType.objects.filter(Q(skill_name=request._obj_.position.name) | \
                                                                Q(skill=request._obj_.position))
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class JobAmountInline(admin.TabularInline):
    model = models.JobAmount
    extra = 0

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "worktype" and request._obj_:
            kwargs["queryset"] = models.WorkType.objects.filter(Q(skill_name=request._obj_.position.name) | \
                                                                Q(skill=request._obj_.position))
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class JobAdmin(admin.ModelAdmin):
    list_display = ('jobsite', 'position')
    search_fields = ('jobsite__short_name', 'position__name__name')
    inlines = [JobRateInline, JobAmountInline]


    def get_form(self, request, obj=None, **kwargs):
        request._obj_ = obj
        return super().get_form(request, obj, **kwargs)


class JobsiteAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'industry')
    search_fields = ('short_name',)


class CandidateContactListFilter(admin.SimpleListFilter):
    title = 'Candidate Contact'
    parameter_name = 'candidate_contact_id'

    def lookups(self, request, model_admin):
        candidate_contacts = candidate_models.CandidateContact.objects.annotate(job_offer_count=Count('job_offers'))\
            .filter(job_offer_count__gt=0).distinct()
        return [(c.pk, c.contact.__str__) for c in candidate_contacts]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(candidate_contact_id=self.value())
        return queryset


class JobOfferAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'candidate_contact', 'status')
    list_filter = (CandidateContactListFilter, 'created_at')
    search_fields = ('candidate_contact__contact__first_name', 'candidate_contact__contact__last_name')
    ordering = ['-created_at']


class CarrierListAdmin(admin.ModelAdmin):
    list_display = ('candidate_contact', 'target_date', 'confirmed_available', 'skill')
    ordering = ('-candidate_contact', '-target_date',)


class MasterCompanyListFilter(admin.SimpleListFilter):
    title = 'Master Company'
    parameter_name = 'master_company_id'

    def lookups(self, request, model_admin):
        qs = models.ShiftDate.objects.filter(cancelled=False).distinct('job__jobsite__master_company')
        companies = [shift_date.job.jobsite.master_company for shift_date in qs]
        return [(c.pk, c.name) for c in companies]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(job__jobsite__master_company_id=self.value())
        return queryset


class CustomerCompanyListFilter(admin.SimpleListFilter):
    title = 'Customer Company'
    parameter_name = 'customer_company_id'

    def lookups(self, request, model_admin):
        qs = models.ShiftDate.objects.filter(cancelled=False).distinct('job__jobsite__regular_company')
        companies = [shift_date.job.jobsite.regular_company for shift_date in qs]
        return [(c.pk, c.name) for c in companies]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(job__jobsite__regular_company_id=self.value())
        return queryset


class ShiftDateAdmin(admin.ModelAdmin):
    list_display = ('shift_date', 'primary_company', 'customer_company')
    list_filter = (MasterCompanyListFilter, CustomerCompanyListFilter,)

    def primary_company(self, obj):
        return obj.job.jobsite.master_company

    def customer_company(self, obj):
        return obj.job.jobsite.regular_company


admin.site.register(models.Jobsite, JobsiteAdmin)
admin.site.register(models.JobsiteUnavailability)
admin.site.register(models.Job, JobAdmin)
admin.site.register(models.JobTag)
admin.site.register(models.ShiftDate, ShiftDateAdmin)
admin.site.register(models.Shift)
admin.site.register(models.TimeSheet, TimeSheetAdmin)
admin.site.register(models.TimeSheetIssue)
admin.site.register(models.JobOffer, JobOfferAdmin)
admin.site.register(models.CandidateEvaluation)
admin.site.register(models.CandidateScore)
admin.site.register(models.BlackList)
admin.site.register(models.FavouriteList)
admin.site.register(models.CarrierList, CarrierListAdmin)
admin.site.register(models.Payslip)
admin.site.register(models.PayslipLine)
admin.site.register(models.PayslipRule)
