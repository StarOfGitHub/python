from django.db.models import F

from r3sourcer.helpers.models.abs import TimeZone


class CompanyTimeZoneMixin(TimeZone):

    class Meta:
        abstract = True

    @property
    def geo(self):
        return self.__class__.objects.filter(
            pk=self.pk,
            company__company_addresses__hq=True,
        ).annotate(
            longitude=F('company__company_addresses__address__longitude'),
            latitude=F('company__company_addresses__address__latitude')
        ).values_list('longitude', 'latitude').get()
