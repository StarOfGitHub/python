from r3sourcer.apps.hr.api.filters import TimesheetFilter
from r3sourcer.apps.hr.models import TimeSheet


class TestTimesheetFilter:

    def test_filter_candidate(self, timesheet, timesheet_tomorrow,
                              candidate_contact):
        filter_obj = TimesheetFilter()

        res = filter_obj.filter_candidate(
            TimeSheet.objects, 'default', candidate_contact.id
        )

        assert len(res) == 2
