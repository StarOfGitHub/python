from django.conf.urls import url

from r3sourcer.apps.pricing import views

urlpatterns = [
    url(r'^pricing/pricelistrates/(?P<id>[\w\-]+)/make_default/$', views.MakePriceListRateView.as_view(), name='make_price_list_rate'),
]
