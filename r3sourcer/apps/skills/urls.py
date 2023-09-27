from django.conf.urls import url

from r3sourcer.apps.skills import views

urlpatterns = [
    url(r'^skills/skills/(?P<id>[\w\-]+)/make_default/$', views.MakeSkillBaseRateDefaultView.as_view(), name='make_skill_base_rate_default'),
    url(r'^skills/skills/(?P<id>[\w\-]+)/change_default/$', views.SkillDefaultRateView.as_view(), name='change_skill_default_rate'),
]
