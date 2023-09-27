from datetime import timedelta

from .models import RateCoefficient, WeekdayWorkRule
from .exceptions import RateNotApplicable
from django.db import models


class CoefficientService:

    def get_industry_rate_coefficient(self, company, industry, modifier_type, start_datetime, overlaps=False):
        query = models.Q(industry=industry,
                         rate_coefficient_modifiers__type=modifier_type,
                         active=True,
                         overlaps=overlaps)

        rate_coefficients = RateCoefficient.objects.owned_by(company).filter(query)

        return rate_coefficients.order_by(
            '-rate_coefficient_modifiers__multiplier',
            '-rate_coefficient_modifiers__fixed_addition',
            '-rate_coefficient_modifiers__fixed_override',
            '-priority',
        ).distinct()

    def process_rate_coefficients(self, rate_coefficients, start_datetime,
                                  origin_hours, break_started=None,
                                  break_ended=None, overlaps=False):
        res = []
        worked_hours = origin_hours
        for rate_coefficient in rate_coefficients:
            rules = rate_coefficient.rate_coefficient_rules.filter(used=True).order_by('-priority').distinct()
            try:
                used_hours = worked_hours
                is_allowance = False

                for rule in rules:
                    calc_hours = origin_hours if is_allowance else worked_hours
                    hours = rule.rule.calc_hours(start_datetime,
                                                 calc_hours,
                                                 break_started,
                                                 break_ended)

                    if hours == timedelta(hours=-1):
                        is_allowance = True
                        hours = timedelta(hours=1)
                        if used_hours < hours:
                            used_hours = hours
                    elif isinstance(rule.rule, WeekdayWorkRule):
                        break

                    used_hours = min(hours, used_hours)

                    if used_hours.total_seconds() <= 0:
                        break

                if used_hours.total_seconds() > 0:
                    # Dmitry F.
                    # it is not best solution! but it needed to prevent
                    # bad time calculation for allowance rules
                    if is_allowance is True and used_hours.total_seconds() < 60 * 60:
                        used_hours = timedelta(hours=1)

                    res.append({
                        'coefficient': rate_coefficient,
                        'hours': used_hours
                    })

                    if not is_allowance:
                        worked_hours -= used_hours
            except RateNotApplicable:
                # TODO: Add logger here with info level
                print('Rate not applicable')

        if worked_hours.total_seconds() > 0 and not overlaps:
            res.append({
                'coefficient': 'base',
                'hours': worked_hours
            })
        return res

    def calc(self, company, industry, modifier_type, start_datetime, worked_hours,
             break_started=None, break_ended=None, overlaps=False):
        if overlaps:
            rate_coefficients = self.get_industry_rate_coefficient(
                company, industry, modifier_type, start_datetime, overlaps=True
            )
            res = self.process_rate_coefficients(rate_coefficients,
                                                 start_datetime,
                                                 worked_hours,
                                                 break_started,
                                                 break_ended,
                                                 overlaps=True)
        else:
            res = []

        rate_coefficients = self.get_industry_rate_coefficient(company,
                                                               industry,
                                                               modifier_type,
                                                               start_datetime,
                                                               overlaps=False)
        res.extend(self.process_rate_coefficients(rate_coefficients,
                                                  start_datetime,
                                                  worked_hours,
                                                  break_started,
                                                  break_ended))
        return res
