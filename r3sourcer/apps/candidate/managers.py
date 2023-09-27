from datetime import date, timedelta, datetime
from django.conf import settings
from django.db.models import Manager, Q, Max, Case, When, DateTimeField


class CandidateContactManager(Manager):

    def available(self, target_date=None):
        if target_date is None:
            target_date = date.today()
        return self.get_queryset().filter(contact__is_available=True).exclude(
            contact__contact_unavailabilities__unavailable_from__lte=target_date,
            contact__contact_unavailabilities__unavailable_until__gte=target_date
        )

    def get_available_for_skill(self, skill, target_date_and_time=None):
        """
        Filters a list with available candidate contacts.
        Conditions:
            Candidate has required skill
            Candidate skill is active
            Has mobile phone number
            Lives in NSW
            His profile is active
            Recruitment status - Recruited Available for Hire
            has no timesheets with: tomorrow 7 AM - 16 hrs < shift_ended_at < tomorrow 7 AM + 16 hrs
            has no vacancy offers with: tomorrow 7 AM - 16 hrs < target_date_and_time < tomorrow 7 AM + 16 hrs
            has no carrier lists for tomorrow
            has no timesheets for today
            carrier list SMS not sent
        List gets sorted by Recent timesheet
        """
        if target_date_and_time is None:
            target_date_and_time = datetime.now()

        return self.available(target_date=target_date_and_time.date()).filter(
            candidate_skills__skill=skill,
            candidate_skills__skill__active=True,
            contact__phone_mobile__isnull=False,
            contact__contact_address__address__state__alternate_names__contains="NSW",
            contact__is_available=True,
        ).filter(
            ~Q(job_offers__shift__date__shift_date=target_date_and_time.date()) &
            ~Q(job_offers__time_sheets__shift_ended_at__range=(
                target_date_and_time - timedelta(hours=settings.CARRIER_LIST_FILLING_TIME_DELTA),
                target_date_and_time + timedelta(hours=settings.CARRIER_LIST_FILLING_TIME_DELTA)
            ))
        ).exclude(
            Q(contact__phone_mobile='') |
            Q(carrier_lists__target_date=target_date_and_time.date()) |
            Q(carrier_lists__sent_message__isnull=False) |
            Q(job_offers__time_sheets__shift_started_at__date=date.today())
        ).annotate(
            recent_timesheet=Max(
                Case(When(
                        job_offers__time_sheets__isnull=False,
                        then='job_offers__time_sheets__shift_started_at'
                    ),
                    output_field=DateTimeField(), default=datetime(target_date_and_time.year, 1, 1))
            ),
        ).select_related(
            'contact'
        ).order_by(
            '-recent_timesheet',
            '-candidate_scores__average_score',
        ).distinct()
