from datetime import timedelta, date, datetime
from decimal import Decimal

import mock
import pytest
import pytz

from django.conf import settings
from django_mock_queries.query import MockSet
from freezegun import freeze_time

from r3sourcer.apps.core.models import InvoiceRule, Invoice, InvoiceLine
from r3sourcer.apps.hr.payment.invoices import InvoiceService
from r3sourcer.apps.hr.models import TimeSheet
from r3sourcer.apps.hr.utils import utils
from r3sourcer.apps.pricing.services import CoefficientService


tz = pytz.timezone(settings.TIME_ZONE)
today = date(2017, 1, 2)


@pytest.mark.django_db
class TestInvoiceService:

    @pytest.fixture
    def service(self):
        return InvoiceService()

    def test_get_price_list_rate(self, price_list_rate, service, skill, master_company, industry):
        res = service._get_price_list_rate(skill, master_company)

        assert res == price_list_rate

    @mock.patch.object(InvoiceService, 'calculate')
    def test_prepare_invoice_no_lines(self, mock_calc, service, regular_company):
        mock_calc.return_value = [], []
        date_from, date_to = utils.get_invoice_dates(regular_company.invoice_rules.first())

        res = service.generate_invoice(date_from, date_to, company=regular_company)

        assert res is None

    @mock.patch.object(CoefficientService, 'calc')
    @mock.patch('r3sourcer.apps.hr.payment.invoices.calc_worked_delta')
    @mock.patch.object(InvoiceService, '_get_price_list_rate')
    @mock.patch.object(InvoiceService, '_get_timesheets')
    def test_calculate(
            self, mock_timesheets, mock_price_list_rate, mock_worked, mock_pl,
            service, regular_company, timesheet_approved, price_list_rate,
            rate_coefficient, vat):

        mock_timesheets.return_value = [timesheet_approved]
        mock_price_list_rate.return_value = price_list_rate
        mock_worked.return_value = timedelta(hours=8)
        mock_pl.return_value = [
            {'coefficient': rate_coefficient, 'hours': timedelta(hours=1)},
            {'coefficient': 'base', 'hours': timedelta(hours=7)},
        ]

        res, jobsites = service.calculate(regular_company)

        assert len(res) == 2
        assert res[0]['amount'] == Decimal(20)
        assert res[1]['amount'] == Decimal(70)
        assert len(jobsites) == 1

    @mock.patch.object(InvoiceService, '_get_timesheets')
    def test_calculate_no_timesheets(
            self, mock_timesheets, service, regular_company):

        mock_timesheets.return_value = []

        res, jobsites = service.calculate(regular_company)

        assert len(res) == 0

    @mock.patch.object(InvoiceService, '_prepare_invoice')
    @mock.patch('r3sourcer.apps.hr.payment.invoices.get_invoice_rule')
    @mock.patch.object(InvoiceService, 'calculate')
    def test_prepare(self, mock_calc, mock_invoice_rule, mock_prepare_invoice,
                     service, regular_company, invoice_rule_master_company):

        mock_calc.return_value = [], []
        mock_invoice_rule.return_value = invoice_rule_master_company
        date_from, date_to = utils.get_invoice_dates(regular_company.invoice_rules.first())

        service.generate_invoice(date_from, date_to, company=regular_company)

        mock_prepare_invoice.assert_called_with(
            company=regular_company,
            date_from=date_from,
            date_to=date_to,
            show_candidate=False,
            invoice=None
        )

    @mock.patch.object(InvoiceService, '_prepare_invoice')
    @mock.patch('r3sourcer.apps.hr.payment.invoices.get_invoice_rule')
    @mock.patch.object(InvoiceService, 'calculate')
    def test_prepare_invoice_exists(
            self, mock_calc, mock_invoice_rule, mock_prepare_invoice, service,
            regular_company, invoice_rule_master_company, invoice):

        mock_calc.return_value = [], []
        mock_invoice_rule.return_value = invoice_rule_master_company
        date_from, date_to = utils.get_invoice_dates(regular_company.invoice_rules.first())

        service.generate_invoice(date_from, date_to, company=regular_company)

        mock_prepare_invoice.assert_called_with(
            company=regular_company,
            date_from=date_from,
            date_to=date_to,
            show_candidate=False,
            invoice=None
        )

    @mock.patch.object(TimeSheet, 'objects', new_callable=mock.PropertyMock)
    @mock.patch.object(InvoiceService, '_prepare_invoice')
    @mock.patch('r3sourcer.apps.hr.payment.invoices.get_invoice_rule')
    @mock.patch.object(InvoiceService, 'calculate')
    def test_prepare_per_jobsite(
            self, mock_calc, mock_invoice_rule, mock_prepare_invoice,
            mock_timesheets, regular_company, invoice_rule_master_company,
            timesheet_approved, jobsite, service):

        invoice_rule_master_company.separation_rule = InvoiceRule.SEPARATION_CHOICES.per_jobsite
        mock_calc.return_value = [], []
        mock_invoice_rule.return_value = invoice_rule_master_company
        mock_timesheets.return_value.filter.return_value = [timesheet_approved]
        date_from, date_to = utils.get_invoice_dates(regular_company.invoice_rules.first())

        service.generate_invoice(date_from, date_to, company=regular_company)

        mock_prepare_invoice.assert_called_with(
            company=regular_company,
            date_from=date_from,
            date_to=date_to,
            timesheets=[timesheet_approved],
            show_candidate=False,
            invoice=None
        )

    @mock.patch.object(InvoiceService, '_prepare_invoice')
    @mock.patch('r3sourcer.apps.hr.payment.invoices.get_invoice_rule')
    @mock.patch.object(InvoiceService, 'calculate')
    def test_prepare_per_jobsite_no_jobsite(
            self, mock_calc, mock_invoice_rule, mock_prepare_invoice, service,
            regular_company, invoice_rule_master_company):

        invoice_rule_master_company.separation_rule = \
            InvoiceRule.SEPARATION_CHOICES.per_jobsite
        mock_calc.return_value = [], []
        mock_invoice_rule.return_value = invoice_rule_master_company
        date_from, date_to = utils.get_invoice_dates(regular_company.invoice_rules.first())

        service.generate_invoice(date_from, date_to, company=regular_company)

        assert not mock_prepare_invoice.called

    @mock.patch.object(TimeSheet, 'objects', new_callable=mock.PropertyMock)
    @mock.patch.object(InvoiceService, '_get_timesheets')
    @mock.patch.object(InvoiceService, '_prepare_invoice')
    @mock.patch('r3sourcer.apps.hr.payment.invoices.get_invoice_rule')
    @mock.patch.object(InvoiceService, 'calculate')
    def test_prepare_per_candidate(
            self, mock_calc, mock_invoice_rule, mock_prepare_invoice,
            mock_get_ts, mock_timesheets, regular_company, timesheet_approved,
            invoice_rule_master_company, candidate_contact, service):

        invoice_rule_master_company.separation_rule = \
            InvoiceRule.SEPARATION_CHOICES.per_candidate
        mock_calc.return_value = [], []
        mock_invoice_rule.return_value = invoice_rule_master_company
        mock_timesheets.return_value.filter.return_value = [timesheet_approved]
        mock_get_ts.return_value = MockSet(timesheet_approved)
        date_from, date_to = utils.get_invoice_dates(regular_company.invoice_rules.first())

        service.generate_invoice(date_from, date_to, company=regular_company)

        mock_prepare_invoice.assert_called_with(
            company=regular_company,
            date_from=date_from,
            date_to=date_to,
            timesheets=[timesheet_approved],
            show_candidate=False,
            invoice=None
        )

    @mock.patch.object(InvoiceService, '_prepare_invoice')
    @mock.patch('r3sourcer.apps.hr.payment.invoices.get_invoice_rule')
    @mock.patch.object(InvoiceService, 'calculate')
    def test_prepare_per_candidate_no_candidates(
            self, mock_calc, mock_invoice_rule, mock_prepare_invoice, service,
            regular_company, invoice_rule_master_company):

        invoice_rule_master_company.separation_rule = \
            InvoiceRule.SEPARATION_CHOICES.per_candidate
        mock_calc.return_value = [], []
        mock_invoice_rule.return_value = invoice_rule_master_company
        date_from, date_to = utils.get_invoice_dates(regular_company.invoice_rules.first())

        service.generate_invoice(date_from, date_to, company=regular_company)

        assert not mock_prepare_invoice.called

    @freeze_time(datetime(2017, 1, 1, 0, 0, 0))
    def test_generate_invoice(self, service, regular_company, job_offer, rate_coefficient, jobsite, price_list_rate):
        invoice_count = Invoice.objects.count()
        invoice_line_count = InvoiceLine.objects.count()
        shift_started_at = tz.localize(datetime.strptime('2017-01-01 07:00:00', '%Y-%m-%d %H:%M:%S'))
        shift_ended_at = tz.localize(datetime.strptime('2017-01-01 17:00:00', '%Y-%m-%d %H:%M:%S'))
        break_started_at = tz.localize(datetime.strptime('2017-01-01 12:00:00', '%Y-%m-%d %H:%M:%S'))
        break_ended_at = tz.localize(datetime.strptime('2017-01-01 12:30:00', '%Y-%m-%d %H:%M:%S'))
        candidate_submitted_at = tz.localize(datetime.strptime('2017-01-02 18:00:00', '%Y-%m-%d %H:%M:%S'))
        supervisor_approved_at = tz.localize(datetime.strptime('2017-01-02 19:00:00', '%Y-%m-%d %H:%M:%S'))
        date_from, date_to = utils.get_invoice_dates(regular_company.invoice_rules.first())
        price_list = price_list_rate.price_list
        price_list.company = regular_company
        price_list.save()

        TimeSheet.objects.create(
            job_offer=job_offer,
            shift_started_at=shift_started_at,
            break_started_at=break_started_at,
            break_ended_at=break_ended_at,
            shift_ended_at=shift_ended_at,
            candidate_submitted_at=candidate_submitted_at,
            supervisor_approved_at=supervisor_approved_at,
        )

        service.generate_invoice(date_from, date_to, company=regular_company)
        invoice = Invoice.objects.all().first()
        line = InvoiceLine.objects.all().first()

        assert Invoice.objects.count() == invoice_count + 1
        assert InvoiceLine.objects.count() == invoice_line_count + 1
        assert invoice.total_with_tax == Decimal('104.50')
        assert invoice.total == Decimal('95.00')
        assert invoice.tax == Decimal('9.50')
        assert line.units == Decimal('9.50')
        assert line.unit_price == Decimal('10.00')

    @freeze_time(datetime(2017, 1, 4, 0, 0, 0))
    def test_update_invoice(self, service, regular_company, job_offer, rate_coefficient, jobsite, price_list_rate):
        shift_started_at = tz.localize(datetime.strptime('2017-01-02 07:00:00', '%Y-%m-%d %H:%M:%S'))
        shift_ended_at = tz.localize(datetime.strptime('2017-01-02 17:00:00', '%Y-%m-%d %H:%M:%S'))
        break_started_at = tz.localize(datetime.strptime('2017-01-02 12:00:00', '%Y-%m-%d %H:%M:%S'))
        break_ended_at = tz.localize(datetime.strptime('2017-01-02 12:30:00', '%Y-%m-%d %H:%M:%S'))
        candidate_submitted_at = tz.localize(datetime.strptime('2017-01-03 18:00:00', '%Y-%m-%d %H:%M:%S'))
        supervisor_approved_at = tz.localize(datetime.strptime('2017-01-03 19:00:00', '%Y-%m-%d %H:%M:%S'))
        date_from, date_to = utils.get_invoice_dates(regular_company.invoice_rules.first())
        price_list = price_list_rate.price_list
        price_list.company = regular_company
        price_list.save()

        TimeSheet.objects.create(
            job_offer=job_offer,
            shift_started_at=shift_started_at,
            break_started_at=break_started_at,
            break_ended_at=break_ended_at,
            shift_ended_at=shift_ended_at,
            candidate_submitted_at=candidate_submitted_at,
            supervisor_approved_at=supervisor_approved_at,
        )

        service.generate_invoice(date_from, date_to, company=regular_company)

        invoice_count = Invoice.objects.count()
        invoice_line_count = InvoiceLine.objects.count()
        shift_started_at = tz.localize(datetime.strptime('2017-01-03 07:00:00', '%Y-%m-%d %H:%M:%S'))
        shift_ended_at = tz.localize(datetime.strptime('2017-01-03 17:00:00', '%Y-%m-%d %H:%M:%S'))
        break_started_at = tz.localize(datetime.strptime('2017-01-03 12:00:00', '%Y-%m-%d %H:%M:%S'))
        break_ended_at = tz.localize(datetime.strptime('2017-01-03 12:30:00', '%Y-%m-%d %H:%M:%S'))
        candidate_submitted_at = tz.localize(datetime.strptime('2017-01-04 18:00:00', '%Y-%m-%d %H:%M:%S'))
        supervisor_approved_at = tz.localize(datetime.strptime('2017-01-04 19:00:00', '%Y-%m-%d %H:%M:%S'))
        timesheet = TimeSheet.objects.create(
            job_offer=job_offer,
            shift_started_at=shift_started_at,
            break_started_at=break_started_at,
            break_ended_at=break_ended_at,
            shift_ended_at=shift_ended_at,
            candidate_submitted_at=candidate_submitted_at,
            supervisor_approved_at=supervisor_approved_at,
        )

        invoice = utils.get_invoice(regular_company, date_from, date_to, timesheet)
        service.generate_invoice(date_from, date_to, invoice=invoice)
        invoice = Invoice.objects.all().first()

        assert invoice_count == Invoice.objects.count()
        assert invoice_line_count + 1 == InvoiceLine.objects.count()
        assert invoice.total_with_tax == Decimal('209.00')
        assert invoice.total == Decimal('190.00')
        assert invoice.tax == Decimal('19.00')
