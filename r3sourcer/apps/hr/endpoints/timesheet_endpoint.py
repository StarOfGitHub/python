import logging

from r3sourcer.apps.core.api.endpoints import ApiEndpoint
from r3sourcer.apps.hr import models as hr_models
from r3sourcer.apps.hr.api import viewsets, filters
from r3sourcer.apps.hr.api.serializers import timesheet as timesheet_serializers


__all__ = [
    'TimeSheetEndpoint'
]

logger = logging.getLogger(__name__)


class TimeSheetEndpoint(ApiEndpoint):

    model = hr_models.TimeSheet
    base_viewset = viewsets.TimeSheetViewset
    serializer = timesheet_serializers.TimeSheetSerializer
    filter_class = filters.TimesheetFilter


class ExtranetCandidateTimesheetEndpoint(ApiEndpoint):

    model = hr_models.TimeSheet
    base_viewset = viewsets.TimeSheetCandidateViewset
    serializer = timesheet_serializers.TimeSheetSerializer
    filter_class = filters.TimesheetFilter


class TimeSheetRateEndpoint(ApiEndpoint):

    model = hr_models.TimeSheetRate
    serializer = timesheet_serializers.TimeSheetRateSerializer
    filter_class = filters.TimeSheetRateFilter
