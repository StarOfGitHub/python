from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from r3sourcer.apps.pricing.models import PriceListRate


class MakePriceListRateView(APIView):
    def post(self, *args, **kwargs):
        rate = get_object_or_404(PriceListRate, id=self.kwargs['id'])
        PriceListRate.objects.all().update(default_rate=False)
        rate.default_rate = True
        rate.save()
        return Response()
