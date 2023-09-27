from django.contrib import admin


class LanguageListFilter(admin.SimpleListFilter):
    title = 'Language'
    parameter_name = 'language_id'

    def lookups(self, request, model_admin):
        languages = set([c.language for c in model_admin.model.objects.all()])
        return [(c.pk, c.name) for c in languages]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(language_id=self.value())
        return queryset


class CompanyListFilter(admin.SimpleListFilter):
    title = 'Master Company'
    parameter_name = 'company_id'

    def lookups(self, request, model_admin):
        companies = set([c.company for c in model_admin.model.objects.filter(company__isnull=False).all()])
        return [(c.pk, c.name) for c in companies]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(company__type='master', company_id=self.value())
        return queryset.filter(company__type='master')
