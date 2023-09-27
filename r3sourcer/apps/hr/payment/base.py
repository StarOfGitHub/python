import copy
from datetime import timedelta, datetime
from io import BytesIO

import weasyprint
from django.db.models import Q

from r3sourcer.apps.pricing.models import (
    RateCoefficientModifier,
    AllowanceMixin,
)
from r3sourcer.helpers.datetimes import tz2utc, date2utc_date

class BasePaymentService:

    modifier_type = RateCoefficientModifier.TYPE_CHOICES.company

    def _get_timesheets(self, timesheets, date_from=None, date_to=None, candidate=None, company=None):
        timesheets = timesheets.filter(
            candidate_submitted_at__isnull=False,
            supervisor_approved_at__isnull=False
        )

        if company:
            date_from = date2utc_date(date_from, company.tz)
            date_to = date2utc_date(date_to, company.tz)

            timesheets = timesheets.filter(
                job_offer__shift__date__job__jobsite__regular_company=company
            )

        if candidate:
            timesheets = timesheets.filter(
                job_offer__candidate_contact=candidate,
            )

        if date_from:
            timesheets.filter(Q(shift_started_at__date__gte=date_from))

        if date_to:
            timesheets.filter(Q(shift_started_at__date__lte=date_to))

        return timesheets.order_by('shift_started_at')

    @classmethod
    def _get_file_from_str(cls, str):
        pdf = weasyprint.HTML(string=str)
        pdf_file = BytesIO()
        pdf_file.write(pdf.write_pdf())
        pdf_file.seek(0)

        return pdf_file

    def lines_iter(self, coeffs_hours, skill, hourly_rate, timesheet):
        for coeff_hours in coeffs_hours:
            coefficient = coeff_hours['coefficient']
            notes = str(skill)
            if coefficient != 'base':
                if self.modifier_type == RateCoefficientModifier.TYPE_CHOICES.company:
                    modifier_rel = coefficient.price_list_rate_modifiers.filter(
                        price_list_rate__price_list__company=timesheet.regular_company,
                    ).first()
                elif self.modifier_type == RateCoefficientModifier.TYPE_CHOICES.candidate:
                    modifier_rel = coefficient.candidate_skill_coefficient_rels.filter(
                        skill_rel__candidate_contact=timesheet.candidate_contact,
                    ).first()

                modifier = modifier_rel and modifier_rel.rate_coefficient_modifier

                if not modifier:
                    modifier = coefficient.rate_coefficient_modifiers.filter(
                        type=self.modifier_type, default=True,
                    ).first()

                is_allowance = any([
                    isinstance(rule.rule, AllowanceMixin)
                    for rule in coefficient.rate_coefficient_rules.all()]
                )
                if is_allowance:
                    rate = modifier.fixed_override
                else:
                    rate = modifier.calc(hourly_rate)
                notes = '{} {}'.format(notes, str(coefficient))
            else:
                rate = hourly_rate

            line = copy.copy(coeff_hours)
            line['rate'] = rate
            line['notes'] = notes

            yield line
