from django.conf.urls import url
from .views import TemplateCompileView, ContentTypeListView, TemplateSMSMessageListView, SMSMessageListView, SearchObjects, ErrorSMSMessageListView

urlpatterns = [
    url('^templates/$', TemplateSMSMessageListView.as_view(), name='templates'),
    url('^templates/compile/$', TemplateCompileView.as_view(), name='template-compile'),
    url('^find/contenttypes/$', ContentTypeListView.as_view(), name='find-contenttypes'),
    url(r'^find/objects/(?P<ct>\d+)/$', SearchObjects.as_view(), name='find-objects'),
    url('^message/$', SMSMessageListView.as_view(), name='sms_messages'),
    url('^error-message/$', ErrorSMSMessageListView.as_view(), name='error_sms_messages')
]

app_name = 'sms_interface'
