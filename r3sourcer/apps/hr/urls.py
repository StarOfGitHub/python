from django.conf.urls import url

from r3sourcer.apps.hr.api import views


urlpatterns = [
    url(r'^distances/', views.CandidateDistanceView.as_view(), name='get_candidate_distance'),
    url(r'^available_recruitees_for_date/',
        views.AvailableCandidatesDateView.as_view(),
        name='available_recruitees_for_date'),
]
