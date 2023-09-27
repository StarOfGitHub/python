import time

import pytest
import freezegun
from datetime import datetime, date, timedelta, time
from django.utils import timezone

from r3sourcer.apps.candidate.models import CandidateContact
from r3sourcer.apps.core.models import InvoiceRule, Invoice, InvoiceLine
from r3sourcer.apps.hr.models import PayslipRule
from r3sourcer.apps.hr.utils.utils import (
        _time_diff,
        get_invoice_rule,
        get_payslip_rule,
        get_invoice,
        get_invoice_dates,
    )
from r3sourcer.apps.hr.utils.job import (
    get_partially_available_candidate_ids_for_vs,
    get_partially_available_candidate_ids, get_partially_available_candidates,
)
from r3sourcer.apps.hr.models import TimeSheet

fun_test_data = [
    (TimeSheet.today_5_am, timezone.make_aware(datetime(2017, 1, 1, 5, 0))),
    (TimeSheet.today_7_am, timezone.make_aware(datetime(2017, 1, 1, 7, 0))),
    (TimeSheet.today_12_pm, timezone.make_aware(datetime(2017, 1, 1, 12, 0))),
    (TimeSheet.today_12_30_pm, timezone.make_aware(datetime(2017, 1, 1, 12, 30))),
    (TimeSheet.today_3_30_pm, timezone.make_aware(datetime(2017, 1, 1, 15, 30))),
    (TimeSheet.tomorrow, date(2017, 1, 2)),
    # (TimeSheet.tomorrow_5_am, timezone.make_aware(datetime(2017, 1, 2, 5, 0))),
    # (TimeSheet.tomorrow_7_am, timezone.make_aware(datetime(2017, 1, 2, 7, 0))),
    # (TimeSheet.tomorrow_end_5_am, timezone.make_aware(datetime(2017, 1, 3, 5, 0))),
]


class TestUtils:

    @pytest.mark.parametrize(['fun', 'res'], fun_test_data)
    def test_date_and_time_functions(self, fun, res):
        with freezegun.freeze_time(datetime(2017, 1, 1, 0, 0, 0)):
            assert fun == res

    @freezegun.freeze_time(datetime(2017, 1, 1, 0, 0, 0))
    def test_time_diff(self):
        now = datetime.now()
        assert _time_diff(now, now + timedelta(hours=8)) == timedelta(hours=8)

    def test_get_invoice_rule(self, regular_company):

        res = get_invoice_rule(regular_company)

        assert res == regular_company.invoice_rules.first()

    def test_get_invoice_rule_master(
            self, master_company, regular_company, company_rel):

        regular_company.invoice_rules.all().delete()
        res = get_invoice_rule(regular_company)

        assert res == master_company.invoice_rules.first()

    def test_get_invoice_rule_master_do_not_have_rule(
            self, master_company, regular_company, company_rel):

        InvoiceRule.objects.all().delete()
        res = get_invoice_rule(regular_company)

        assert res is None

    def test_get_invoice_rule_do_not_have_rule(self, regular_company,
                                               company_rel):

        InvoiceRule.objects.all().delete()
        res = get_invoice_rule(regular_company)

        assert res is None

    def test_get_payslip_rule(self, regular_company):

        res = get_payslip_rule(regular_company)

        assert res == regular_company.payslip_rules.first()

    def test_get_payslip_rule_master(
            self, master_company, regular_company, company_rel):

        regular_company.payslip_rules.all().delete()
        res = get_payslip_rule(regular_company)

        assert res == master_company.payslip_rules.first()

    def test_get_payslip_rule_master_do_not_have_rule(
            self, master_company, regular_company, company_rel):

        PayslipRule.objects.all().delete()
        res = get_payslip_rule(regular_company)

        assert res is None

    def test_get_payslip_rule_do_not_have_rule(self, regular_company,
                                               company_rel):

        PayslipRule.objects.all().delete()
        res = get_payslip_rule(regular_company)

        assert res is None


class TestGetInvoice:
    def test_get_invoice_one_invoice(self, master_company, regular_company, timesheet, vat):
        invoice_rule = regular_company.invoice_rules.first()
        invoice = Invoice.objects.create(
            provider_company=master_company,
            customer_company=regular_company,
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            units=1,
            unit_price=1,
            date=date.today(),
            timesheet=timesheet,
            vat=vat,
            amount=1,
            notes=''
        )
        date_from, date_to = get_invoice_dates(invoice_rule)
        result_invoice = get_invoice(regular_company, date_from, date_to, timesheet)

        assert invoice == result_invoice

    def test_get_invoice_per_candidate(self, master_company, regular_company, timesheet, vat, candidate_contact):
        invoice_rule = regular_company.invoice_rules.first()
        invoice_rule.separation_rule = 'per_candidate'
        invoice_rule.save()
        job_offer = timesheet.job_offer
        job_offer.candidate_contact = candidate_contact
        job_offer.save()
        invoice = Invoice.objects.create(
            provider_company=master_company,
            customer_company=regular_company,
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            units=1,
            unit_price=1,
            date=date.today(),
            timesheet=timesheet,
            vat=vat,
            amount=1,
            notes=''
        )
        date_from, date_to = get_invoice_dates(invoice_rule)
        result_invoice = get_invoice(regular_company, date_from, date_to, timesheet)

        assert invoice == result_invoice

    def test_get_invoice_per_jobsite(self, master_company, regular_company, timesheet, vat, jobsite):
        invoice_rule = regular_company.invoice_rules.first()
        invoice_rule.separation_rule = 'per_jobsite'
        invoice_rule.save()
        job = timesheet.job_offer.shift.date.job
        job.jobsite = jobsite
        job.save()
        invoice = Invoice.objects.create(
            provider_company=master_company,
            customer_company=regular_company,
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            units=1,
            unit_price=1,
            date=date.today(),
            timesheet=timesheet,
            vat=vat,
            amount=1,
            notes=''
        )
        date_from, date_to = get_invoice_dates(invoice_rule)
        result_invoice = get_invoice(regular_company, date_from, date_to, timesheet)

        assert invoice == result_invoice


class TestGetInvoiceDates:
    @freezegun.freeze_time(datetime(2017, 1, 1, 0, 0, 0))
    def test_get_invoice_dates_daily(self, regular_company):
        invoice_rule = regular_company.invoice_rules.first()
        invoice_rule.period = 'daily'
        invoice_rule.save()
        date_from, date_to = get_invoice_dates(invoice_rule)

        assert date_from == date(2017, 1, 1)
        assert date_to == date(2017, 1, 2)

    @freezegun.freeze_time(datetime(2017, 1, 1, 0, 0, 0))
    def test_get_invoice_dates_weekly(self, regular_company):
        invoice_rule = regular_company.invoice_rules.first()
        invoice_rule.period = 'weekly'
        invoice_rule.save()
        date_from, date_to = get_invoice_dates(invoice_rule)

        assert date_from == date(2016, 12, 26)
        assert date_to == date(2017, 1, 2)

    @freezegun.freeze_time(datetime(2017, 1, 1, 0, 0, 0))
    def test_get_invoice_dates_fortnightly_first_invoice(self, regular_company):
        invoice_rule = regular_company.invoice_rules.first()
        invoice_rule.period = 'fortnightly'
        invoice_rule.save()
        date_from, date_to = get_invoice_dates(invoice_rule)

        assert date_from == date(2016, 12, 26)
        assert date_to == date(2017, 1, 9)

    @freezegun.freeze_time(datetime(2017, 1, 1, 0, 0, 0))
    def test_get_invoice_dates_fortnightly(self, regular_company, master_company):
        freezer = freezegun.freeze_time("2016-01-26 12:00:00")
        freezer.start()
        Invoice.objects.create(
            provider_company=master_company,
            customer_company=regular_company,
        )
        freezer.stop()
        invoice_rule = regular_company.invoice_rules.first()
        invoice_rule.period = 'fortnightly'
        invoice_rule.save()

        date_from, date_to = get_invoice_dates(invoice_rule)

        assert date_from == date(2016, 12, 26)
        assert date_to == date(2017, 1, 9)

    @freezegun.freeze_time(datetime(2017, 1, 16, 0, 0, 0))
    def test_get_invoice_dates_fortnightly_new_invoice(self, regular_company, master_company):
        freezer = freezegun.freeze_time("2016-12-26 12:00:00")
        freezer.start()
        Invoice.objects.create(
            provider_company=master_company,
            customer_company=regular_company,
        )
        freezer.stop()
        invoice_rule = regular_company.invoice_rules.first()
        invoice_rule.period = 'fortnightly'
        invoice_rule.save()

        date_from, date_to = get_invoice_dates(invoice_rule)

        assert date_from == date(2017, 1, 9)
        assert date_to == date(2017, 1, 23)

    @freezegun.freeze_time(datetime(2017, 1, 18, 0, 0, 0))
    def test_get_invoice_dates_fortnightly_new_invoice_2(self, regular_company, master_company):
        freezer = freezegun.freeze_time("2017-01-04 12:00:00")
        freezer.start()
        Invoice.objects.create(
            provider_company=master_company,
            customer_company=regular_company,
        )
        freezer.stop()
        invoice_rule = regular_company.invoice_rules.first()
        invoice_rule.period = 'fortnightly'
        invoice_rule.save()

        date_from, date_to = get_invoice_dates(invoice_rule)

        assert date_from == date(2017, 1, 16)
        assert date_to == date(2017, 1, 30)

    @freezegun.freeze_time(datetime(2017, 2, 22, 0, 0, 0))
    def test_get_invoice_dates_fortnightly_new_invoice_empty_weeks(self, regular_company, master_company):
        freezer = freezegun.freeze_time("2017-01-02 12:00:00")
        freezer.start()
        Invoice.objects.create(
            provider_company=master_company,
            customer_company=regular_company,
        )
        freezer.stop()
        invoice_rule = regular_company.invoice_rules.first()
        invoice_rule.period = 'fortnightly'
        invoice_rule.save()

        date_from, date_to = get_invoice_dates(invoice_rule)

        assert date_from == date(2017, 2, 13)
        assert date_to == date(2017, 2, 27)

    @freezegun.freeze_time(datetime(2018, 1, 1, 0, 0, 0))
    def test_get_invoice_dates_monthly(self, regular_company):
        invoice_rule = regular_company.invoice_rules.first()
        invoice_rule.period = 'monthly'
        invoice_rule.save()
        date_from, date_to = get_invoice_dates(invoice_rule)

        assert date_from == date(2018, 1, 1)
        assert date_to == date(2018, 1, 29)

    @freezegun.freeze_time(datetime(2017, 1, 1, 0, 0, 0))
    def test_get_invoice_dates_monthly_overlapped_end(self, regular_company):
        invoice_rule = regular_company.invoice_rules.first()
        invoice_rule.period = 'monthly'
        invoice_rule.save()
        date_from, date_to = get_invoice_dates(invoice_rule)

        assert date_from == date(2016, 12, 26)
        assert date_to == date(2017, 1, 30)

    @freezegun.freeze_time(datetime(2017, 2, 2, 0, 0, 0))
    def test_get_invoice_dates_monthly_overlapped_start_end(self, regular_company):
        invoice_rule = regular_company.invoice_rules.first()
        invoice_rule.period = 'monthly'
        invoice_rule.save()
        date_from, date_to = get_invoice_dates(invoice_rule)

        assert date_from == date(2017, 1, 30)
        assert date_to == date(2017, 2, 27)

    @freezegun.freeze_time(datetime(2017, 4, 5, 0, 0, 0))
    def test_get_invoice_dates_monthly_overlapped_start(self, regular_company):
        invoice_rule = regular_company.invoice_rules.first()
        invoice_rule.period = 'monthly'
        invoice_rule.save()
        date_from, date_to = get_invoice_dates(invoice_rule)

        assert date_from == date(2017, 3, 27)
        assert date_to == date(2017, 5, 1)


class TestJobUtils():

    @freezegun.freeze_time(datetime(2017,2,1,0,0,0))
    def test_get_partially_available_candidate_ids_for_vs(self, client, user, job_with_four_shifts, shift_first,
                                                          shift_second, shift_third, shift_fourth,
                                                          skill_rel, skill_rel_second, candidate_rel,
                                                          candidate_rel_second):
        candidates = CandidateContact.objects.all()
        candidate_ids = get_partially_available_candidate_ids_for_vs(candidates, date(2017, 2, 1), time(0, 0, 0))

        assert len(candidates) > 0
        assert len(candidate_ids) == 0

    @freezegun.freeze_time(datetime(2017,1,1,0,0,0))
    def test_get_partially_available_candidate_ids_for_vs_with_unavailable(self, client, user, job_with_four_shifts,
                                                                           shift_first, shift_second, shift_third,
                                                                           shift_fourth, skill_rel, skill_rel_second,
                                                                           candidate_rel, candidate_rel_second,
                                                                           job_offer_for_candidate):
        candidates = CandidateContact.objects.all()
        candidate_ids = get_partially_available_candidate_ids_for_vs(candidates, date(2017, 1, 1), time(0, 0, 0))

        assert len(candidates) > 0
        assert len(candidate_ids) == 1

    @freezegun.freeze_time(datetime(2017,2,1,0,0,0))
    def test_get_partially_available_candidate_ids(self, client, user, job_with_four_shifts, shift_first,
                                                          shift_second, shift_third, shift_fourth,
                                                          skill_rel, skill_rel_second, candidate_rel,
                                                          candidate_rel_second):
        candidates = CandidateContact.objects.all()
        shifts = [shift_first, shift_second, shift_third, shift_fourth]
        partial = get_partially_available_candidate_ids(candidates, shifts)

        assert len(candidates) > 0
        assert len(partial) == 0

    @freezegun.freeze_time(datetime(2017,1,1,0,0,0))
    def test_get_partially_available_candidate_ids_with_unavailable(self, client, user, job_with_four_shifts,
                                                                   shift_first,
                                                               shift_second, shift_third, shift_fourth, skill_rel,
                                                               skill_rel_second, candidate_rel, candidate_rel_second,
                                                               job_offer_for_candidate):
        candidates = CandidateContact.objects.all()
        shifts = [shift_first, shift_second, shift_third, shift_fourth]
        partial = get_partially_available_candidate_ids(candidates, shifts)

        assert len(candidates) > 0
        assert len(partial) == 1

    @freezegun.freeze_time(datetime(2017,2,1,0,0,0))
    def test_get_partially_available_candidates(self, client, user, job_with_four_shifts, shift_first,
                                                          shift_second, shift_third, shift_fourth,
                                                          skill_rel, skill_rel_second, candidate_rel,
                                                          candidate_rel_second):
        candidates = CandidateContact.objects.all()
        shifts = [shift_first, shift_second, shift_third, shift_fourth]
        partial = get_partially_available_candidates(candidates, shifts)

        assert len(candidates) > 0
        assert len(partial) == 0

    @freezegun.freeze_time(datetime(2017,1,1,0,0,0))
    def test_get_partially_available_candidates_with_unavailable(self, client, user, job_with_four_shifts,
                                                                   shift_first,
                                                               shift_second, shift_third, shift_fourth, skill_rel,
                                                               skill_rel_second, candidate_rel, candidate_rel_second,
                                                               job_offer_for_candidate):
        candidates = CandidateContact.objects.all()
        shifts = [shift_first, shift_second, shift_third, shift_fourth]
        partial = get_partially_available_candidates(candidates, shifts)

        assert len(candidates) > 0
        assert len(partial) == 1
