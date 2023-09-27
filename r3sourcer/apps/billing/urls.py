from django.conf.urls import url

from r3sourcer.apps.billing import views


urlpatterns = [
    # billing page
    url(r'^billing/subscription/list/$', views.SubscriptionListView.as_view(), name='subscription_list'),
    url(r'^billing/subscription/create/$', views.SubscriptionCreateView.as_view(), name='subscription_create'),
    url(r'^billing/subscription/status/$', views.SubscriptionStatusView.as_view(), name='subscription_status'),
    url(r'^billing/subscription/cancel/$', views.SubscriptionCancelView.as_view(), name='subscription_cancel'),
    url(r'^billing/stripe_customer/$', views.StripeCustomerView.as_view(), name='stripe_customer'),
    url(r'^billing/payments/$', views.PaymentListView.as_view(), name='payment_list'),
    url(r'^billing/check_payment_information/$', views.CheckPaymentInformationView.as_view(), name='check_payment_information'),
    url(r'^billing/disable_sms/company/(?P<id>[\w\-]+)$', views.DisableSMSCompanyView.as_view(), name='disable_sms_company'),
    url(r'^billing/disable_sms/contact/(?P<id>[\w\-]+)$', views.DisableSMSContactView.as_view(), name='disable_sms_contact'),
    url(r'^billing/add_funds_twilio/$', views.TwilioFundCreateView.as_view(), name='add_funds_twilio'),
    url(r'^billing/auto_charge_twilio/$', views.TwilioAutoChargeView.as_view(), name='auto_charge_twilio'),
    url(r'^billing/subscription_type/$', views.SubscriptionTypeView.as_view(), name='subscription_type'),
    url(r'^billing/country_account/$', views.StripeCountryAccountView.as_view(), name='stripe_country_account'),

    # subscription management page
    url(r'^billing/companies/$', views.CompanyListView.as_view(), name='company_list'),
    url(r'^billing/discounts/$', views.DiscountView.as_view(), name='discounts'),
]

app_name = 'billing'
