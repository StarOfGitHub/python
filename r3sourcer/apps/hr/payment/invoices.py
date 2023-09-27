import logging
import math
from copy import copy
from hashlib import md5

from django.core.files.base import ContentFile
from django.db.models import Count
from django.utils.formats import date_format
from filer.models import Folder, File

from r3sourcer.apps.core.models import Invoice, InvoiceLine, InvoiceRule
from r3sourcer.apps.core.utils.utils import get_thumbnail_picture
from r3sourcer.apps.hr.models import TimeSheet
from r3sourcer.apps.hr.payment.base import BasePaymentService
from r3sourcer.apps.pricing.models import PriceListRate
from r3sourcer.apps.pdf_templates.models import PDFTemplate
from r3sourcer.helpers.datetimes import utc_now

logger = logging.getLogger(__name__)


class InvoiceService(BasePaymentService):
    def _get_order_number(self, rule, date_from, date_to, timesheet):
        if rule.separation_rule == InvoiceRule.SEPARATION_CHOICES.one_invoice:
            order_number = '{} - {}'.format(date_from, date_to)
        elif rule.separation_rule == InvoiceRule.SEPARATION_CHOICES.per_jobsite:
            jobsite = timesheet.job_offer.shift.date.job.jobsite
            order_number = jobsite.address.city
        elif rule.separation_rule == InvoiceRule.SEPARATION_CHOICES.per_candidate:
            order_number = str(timesheet.job_offer.candidate_contact)
        else:
            raise Exception('Order number not filled')

        return order_number

    def _get_price_list_rate(self, worktype, customer_company):
        price_list_rate = PriceListRate.objects.filter(
            worktype=worktype,
            price_list__company=customer_company,
        ).last()

        if price_list_rate:
            return price_list_rate
        else:
            raise Exception('Pricelist rate for company not found')

    def calculate(self, timesheets):
        # coefficient_service = CoefficientService()
        lines = []

        for timesheet in timesheets:
            # industry = timesheet.job_offer.job.jobsite.industry
            customer_company = timesheet.job_offer.shift.date.job.customer_company
            vat = customer_company.get_vat()
            
            master_company = customer_company.get_master_company()
            provider_company = master_company[0] if master_company else customer_company
            company_language = provider_company.get_default_language()

            for ts_rate in timesheet.timesheet_rates.all():
                # price_list_rate = self._get_price_list_rate(ts_rate.worktype, customer_company)

                # Decided not to use the below code snippet because RateCoEfficient is used in
                # Australia only, outside Europe like Estonia.
                # if ts_rate.worktype.name == WorkType.DEFAULT:
                #     coeffs_hours = coefficient_service.calc(timesheet.master_company,
                #                                             industry,
                #                                             RateCoefficientModifier.TYPE_CHOICES.company,
                #                                             timesheet.shift_started_at_tz,
                #                                             timesheet.shift_duration,
                #                                             break_started=timesheet.break_started_at_tz,
                #                                             break_ended=timesheet.break_ended_at_tz)
                #
                #     lines_iter = self.lines_iter(coeffs_hours,
                #                                  ts_rate.worktype,
                #                                  ts_rate.rate,
                #                                  timesheet)
                #     for raw_line in lines_iter:
                #         rate = raw_line['rate']
                #         units = Decimal(raw_line['hours'].total_seconds() / 3600)
                #
                #         if not units:
                #             continue
                #
                #         lines.append({
                #             'date': timesheet.shift_started_at_tz.date(),
                #             'units': units,
                #             'notes': ts_rate.worktype.skill_translation(company_language),
                #             'skill_activity': ts_rate.worktype.translation(company_language),
                #             'unit_price': rate,
                #             'amount': math.ceil(rate * units * 100) / 100,
                #             'vat': vat,
                #             'unit_name': ts_rate.worktype.uom.translation(company_language),
                #             'timesheet': timesheet,
                #         })
                # else:

                lines.append({
                    'date': timesheet.shift_started_at_tz.date(),
                    'units': ts_rate.value,
                    'notes': ts_rate.worktype.skill_translation(company_language),
                    'skill_activity': ts_rate.worktype.translation(company_language),
                    'unit_price': ts_rate.rate,
                    'amount': math.ceil(ts_rate.rate * ts_rate.value * 100) / 100,
                    'vat': vat,
                    'unit_name': ts_rate.worktype.uom.translation(company_language),
                    'timesheet': timesheet,
                })

        return lines, timesheets

    @classmethod
    def generate_pdf(cls, invoice, show_candidate=False):
        template_slug = 'company-invoice'
        master_company = invoice.provider_company
        company_language = master_company.get_default_language()

        # get template
        try:
            template = PDFTemplate.objects.get(slug=template_slug,
                                               company=master_company,
                                               language=company_language)
        except PDFTemplate.DoesNotExist:
            logger.exception('Cannot find pdf template with slug %s for language %s', template_slug, company_language)
            raise Exception('Cannot find pdf template with slug %s for language %s', template_slug, company_language)

        if master_company.logo:
            master_logo = get_thumbnail_picture(master_company.logo, 'large')
        else:
            master_logo = get_thumbnail_picture(invoice.provider_company.logo, 'large')

        context = {
            'lines': invoice.invoice_lines.order_by('date').all(),
            'invoice': invoice,
            'company': invoice.customer_company,
            'master_company': invoice.provider_company,
            'master_company_logo': master_logo,
            'show_candidate': show_candidate,
        }

        pdf_file = cls._get_file_from_str(str(template.render(context)))

        folder, created = Folder.objects.get_or_create(
            parent=invoice.customer_company.files,
            name='invoices',
        )

        file_name = 'invoice_{}_{}.pdf'.format(
            invoice.number,
            date_format(invoice.date, 'Y_m_d')
        )

        file_obj, _ = File.objects.get_or_create(
            folder=folder,
            name='invoice_{}_{}.pdf'.format(
                invoice.number,
                date_format(invoice.date, 'Y_m_d')
            ),
            file=ContentFile(pdf_file.read(), name=file_name)
        )

        return file_obj

    @property
    def invoice_line_keys(se1f):
        return (
            'timesheet',
            'date',
            'units',
            'notes',
            'unit_price',
            'amount',
            'unit_name'
        )

    def get_line_unique_id(self, get_fn, line):
        parts = []
        for key in self.invoice_line_keys:
            parts.append(str(get_fn(line, key)))

        return md5(''.join(parts).encode()).hexdigest()

    def _prepare_invoice(self, date_from, date_to, timesheets, invoice=None, company=None,
                         show_candidate=False, recreate=False):
        if hasattr(company, 'subcontractor'):
            candidate = company.subcontractor.primary_contact
            timesheets = timesheets.filter(
                job_offer__candidate_contact=candidate
            )

        lines, timesheets = self.calculate(timesheets)

        if not lines:
            return

        if not invoice:
            master_company = company.get_master_company()
            provider_company = master_company[0] if master_company else company
            invoice_rule = company.invoice_rules.first()
            invoice = Invoice.objects.create(
                provider_company=provider_company,
                customer_company=company,
                order_number=self._get_order_number(invoice_rule, date_from, date_to, timesheets[0]),
                period=invoice_rule.period,
                separation_rule=invoice_rule.separation_rule
            )

        invoice_lines = {}
        for line in invoice.invoice_lines.all():
            invoice_lines[self.get_line_unique_id(getattr, line)] = line

        calculated_lines = {}
        for line in lines:
            calculated_lines[self.get_line_unique_id(dict.get, line)] = line

        to_insert = []

        for key in copy(calculated_lines).keys():
            item = calculated_lines.pop(key)
            if invoice_lines.get(key) is None:
                to_insert.append(item)
            else:
                invoice_lines.pop(key)

        # delete outdated lines
        for item in invoice_lines.values():
            item.delete()

        invoice_lines = []

        for line in to_insert:
            invoice_lines.append(InvoiceLine(
                invoice=invoice,
                created_at=utc_now(),
                updated_at=utc_now(),
                **line))

        InvoiceLine.objects.bulk_create(invoice_lines)

        invoice.save(update_fields=['total', 'tax', 'total_with_tax', 'updated_at'])

        # TODO: decide when to trigger pdf generation
        # self.generate_pdf(invoice, show_candidate)

        return invoice

    def generate_invoice(self, date_from, date_to, company, invoice_rule, invoice=None, recreate=False):
        separation_rule = invoice_rule.separation_rule
        show_candidate = invoice_rule.show_candidate_name
        time_sheets_qs = TimeSheet.objects.filter(
            invoice_lines__isnull=True,
            candidate_submitted_at__isnull=False,
            supervisor_approved_at__isnull=False,
            job_offer__shift__date__shift_date__lt=date_to,
            job_offer__shift__date__job__jobsite__regular_company=company,
        ).annotate(Count('id'))
        if separation_rule == InvoiceRule.SEPARATION_CHOICES.one_invoice:
            self._prepare_invoice(
                date_from=date_from,
                date_to=date_to,
                invoice=invoice,
                company=company,
                show_candidate=show_candidate,
                timesheets=time_sheets_qs,
                recreate=recreate
            )

        elif separation_rule == InvoiceRule.SEPARATION_CHOICES.per_jobsite:
            jobsites = company.jobsites_regular.all()

            for jobsite in set(jobsites):
                time_sheets = time_sheets_qs.filter(
                    job_offer__shift__date__job__jobsite=jobsite,
                ).order_by('shift_started_at')

                self._prepare_invoice(
                    date_from=date_from,
                    date_to=date_to,
                    invoice=invoice,
                    company=company,
                    timesheets=time_sheets,
                    show_candidate=show_candidate,
                    recreate=recreate
                )

        elif separation_rule == InvoiceRule.SEPARATION_CHOICES.per_candidate:
            candidates = set(time_sheets_qs.values_list('job_offer__candidate_contact', flat=True))

            for candidate in candidates:
                time_sheets = time_sheets_qs.filter(
                    job_offer__candidate_contact_id=candidate,
                )
                self._prepare_invoice(
                    date_from=date_from,
                    date_to=date_to,
                    invoice=invoice,
                    company=company,
                    timesheets=time_sheets,
                    show_candidate=show_candidate,
                    recreate=recreate
                )
