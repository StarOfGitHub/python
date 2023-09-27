from r3sourcer.apps.core.api.endpoints import ApiEndpoint
from r3sourcer.apps.core.api.permissions import ReadonlyOrIsSuperUser
from r3sourcer.apps.core.api.router import router
from r3sourcer.apps.pricing import models
from r3sourcer.apps.pricing.api import serializers, viewsets, filters


class IndustryEndpoint(ApiEndpoint):

    model = models.Industry
    serializer = serializers.IndustrySerializer
    filter_class = filters.IndustryFilter
    search_fields = ('type', 'translations__value')
    permission_classes = (ReadonlyOrIsSuperUser, )


class DynamicCoefficientRuleEndpoint(ApiEndpoint):

    model = models.DynamicCoefficientRule
    serializer = serializers.DynamicCoefficientRuleSerializer


class RateCoefficientEndpoint(ApiEndpoint):

    model = models.RateCoefficient
    base_viewset = viewsets.RateCoefficientViewset
    serializer = serializers.RateCoefficientSerializer
    filter_class = filters.RateCoefficientFilter


class PriceListRateEndpoint(ApiEndpoint):

    model = models.PriceListRate
    serializer = serializers.PriceListRateSerializer
    filter_class = filters.PriceListRateFilter
    search_fields = ('skill__name',)


class RateCoefficientModifierEndpoint(ApiEndpoint):

    model = models.RateCoefficientModifier
    filter_class = filters.RateCoefficientModifierFilter
    base_viewset = viewsets.RateCoefficientModifierViewset


class PriceListEndpoint(ApiEndpoint):

    model = models.PriceList
    filter_class = filters.PriceListFilter
    serializer_fields = ('id', 'company', 'valid_from', 'valid_until', 'effective', 'approved_by', 'approved_at', 'timezone')


class PriceListRateModifierEndpoint(ApiEndpoint):

    model = models.PriceListRateModifier


router.register(endpoint=RateCoefficientEndpoint())
router.register(models.RateCoefficientGroup)
router.register(endpoint=RateCoefficientModifierEndpoint())
router.register(endpoint=IndustryEndpoint())
router.register(endpoint=PriceListEndpoint())
router.register(endpoint=PriceListRateEndpoint())
router.register(models.PriceListRateCoefficient)
router.register(endpoint=DynamicCoefficientRuleEndpoint())
router.register(endpoint=PriceListRateModifierEndpoint())

router.register(models.WeekdayWorkRule)
router.register(models.OvertimeWorkRule)
router.register(models.TimeOfDayWorkRule)
router.register(models.AllowanceWorkRule)
