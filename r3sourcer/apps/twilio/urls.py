from django.conf.urls import url
from .views import SMSDialogTemplateView, callback

urlpatterns = [
    url(r'^$', SMSDialogTemplateView.as_view(), name='sms-view'),
    url(r'^incoming$', callback),
]

app_name = 'twilio'
