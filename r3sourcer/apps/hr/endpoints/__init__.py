from r3sourcer.apps.core.api.endpoints import ApiEndpoint
from r3sourcer.apps.core.api.router import router
from r3sourcer.apps.hr import models as hr_models
from r3sourcer.apps.hr.api import filters as hr_filters, viewsets as hr_viewsets
from r3sourcer.apps.hr.api.serializers import job as job_serializers, timesheet as timesheet_serializer
from r3sourcer.apps.hr.endpoints.payment import InvoiceEndpoint
from r3sourcer.apps.hr.endpoints.timesheet_endpoint import TimeSheetEndpoint, ExtranetCandidateTimesheetEndpoint, TimeSheetRateEndpoint


class JobsiteEndpoint(ApiEndpoint):
    model = hr_models.Jobsite
    base_viewset = hr_viewsets.JobsiteViewset
    filter_class = hr_filters.JobsiteFilter
    serializer = job_serializers.JobsiteSerializer
    search_fields = (
        'address__city__search_names', 'address__street_address', 'master_company__name', 'regular_company__name',
    )


class JobEndpoint(ApiEndpoint):
    model = hr_models.Job
    base_viewset = hr_viewsets.JobViewset
    serializer = job_serializers.JobSerializer
    filter_class = hr_filters.JobFilter
    search_fields = (
        'workers', 'jobsite__address__city__search_names', 'publish_on', 'expires_on', 'position__name__name',
        'jobsite__address__street_address', 'jobsite__master_company__name', 'jobsite__regular_company__name'
    )


class FavouriteListEndpoint(ApiEndpoint):

    model = hr_models.FavouriteList
    filter_class = hr_filters.FavouriteListFilter
    serializer = job_serializers.FavouriteListSerializer


class JobOfferEndpoint(ApiEndpoint):

    model = hr_models.JobOffer
    base_viewset = hr_viewsets.JobOfferViewset
    serializer = job_serializers.JobOfferSerializer
    filter_class = hr_filters.JobOfferFilter


class CarrierListEndpoint(ApiEndpoint):

    model = hr_models.CarrierList
    serializer = job_serializers.CarrierListSerializer
    filter_class = hr_filters.CarrierListFilter


class BlackListEndpoint(ApiEndpoint):

    model = hr_models.BlackList
    filter_class = hr_filters.BlackListFilter
    serializer = job_serializers.BlackListSerializer


class CandidateEvaluationEndpoint(ApiEndpoint):

    model = hr_models.CandidateEvaluation
    filter_class = hr_filters.CandidateEvaluationFilter
    serializer = timesheet_serializer.CandidateEvaluationSerializer


class ShiftEndpoint(ApiEndpoint):

    model = hr_models.Shift
    serializer = job_serializers.ShiftSerializer
    filter_class = hr_filters.ShiftFilter
    base_viewset = hr_viewsets.ShiftViewset
    search_fields = ('date__job', )


class ShiftDateEndpoint(ApiEndpoint):

    model = hr_models.ShiftDate
    serializer = job_serializers.ShiftDateSerializer


class CandidateJobOfferEndpoint(ApiEndpoint):

    model = hr_models.JobOffer
    serializer = job_serializers.CandidateJobOfferSerializer
    base_viewset = hr_viewsets.JobOffersCandidateViewset
    filter_class = hr_filters.JobOfferCandidateFilter


class JobTagEndpoint(ApiEndpoint):

    model = hr_models.JobTag
    filter_class = hr_filters.JobTagFilter


class JobRateEndpoint(ApiEndpoint):

    model = hr_models.JobRate
    filter_class = hr_filters.JobRateFilter
    serializer = job_serializers.JobRateSerializer


class JobAmountEndpoint(ApiEndpoint):

    model = hr_models.JobAmount
    filter_class = hr_filters.JobAmountFilter
    serializer = job_serializers.JobAmountSerializer


router.register(endpoint=JobsiteEndpoint())
router.register(hr_models.JobsiteUnavailability)
router.register(endpoint=JobEndpoint())
router.register(endpoint=JobTagEndpoint())
router.register(endpoint=ShiftDateEndpoint())
router.register(endpoint=ShiftEndpoint())
router.register(endpoint=TimeSheetEndpoint())
router.register(endpoint=TimeSheetRateEndpoint())
router.register(endpoint=ExtranetCandidateTimesheetEndpoint(), url='hr/timesheets-candidate')
router.register(hr_models.TimeSheetIssue)
router.register(endpoint=JobOfferEndpoint())
router.register(endpoint=CandidateEvaluationEndpoint())
router.register(endpoint=BlackListEndpoint())
router.register(endpoint=FavouriteListEndpoint())
router.register(endpoint=CarrierListEndpoint())
router.register(hr_models.Payslip)
router.register(hr_models.PayslipLine)
router.register(hr_models.PayslipRule)
router.register(endpoint=InvoiceEndpoint(), replace=True)
router.register(endpoint=CandidateJobOfferEndpoint(), url='hr/joboffers-candidate')
router.register(endpoint=JobRateEndpoint())
router.register(endpoint=JobAmountEndpoint())
