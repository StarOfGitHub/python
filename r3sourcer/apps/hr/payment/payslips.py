from decimal import Decimal

from django.core.files.base import ContentFile
from django.template.loader import get_template
from django.utils.formats import date_format
from filer.models import Folder, File

from r3sourcer.apps.candidate.models import CandidateContact, SkillRel
from r3sourcer.apps.core.utils.companies import get_site_url
from r3sourcer.apps.hr.payment.base import BasePaymentService
from r3sourcer.apps.pricing.models import RateCoefficientModifier
from r3sourcer.apps.pricing.services import CoefficientService
from ..models import PayslipLine, Payslip, JobOffer, TimeSheet


class PayslipService(BasePaymentService):

    def _get_skill_rate(self, candidate, skill):
        skill_rel = candidate.candidate_skills.filter(
            skill=skill
        ).first()

        if skill_rel is None:
            return 0

        skill_rate = skill_rel.hourly_rate if skill_rel.hourly_rate else skill.default_rate

        return skill_rate

    def calculate(self, candidate, from_date=None, timesheets=None):

        timesheets = self._get_timesheets(timesheets, from_date, candidate)
        coefficient_service = CoefficientService()
        prices = {}

        for timesheet in timesheets:
            jobsite = timesheet.job_offer.job.jobsite
            industry = jobsite.industry
            skill = timesheet.job_offer.job.position
            skill_rate = self._get_skill_rate(candidate, skill)

            coeffs_hours = coefficient_service.calc(
                timesheet.master_company, industry,
                RateCoefficientModifier.TYPE_CHOICES.company,
                timesheet.shift_started_at_tz,
                timesheet.shift_duration,
                break_started=timesheet.break_started_at,
                break_ended=timesheet.break_ended_at,
            )

            lines_iter = self.lines_iter(coeffs_hours, skill, skill_rate)

            for raw_line in lines_iter:
                units = Decimal(raw_line['hours'].total_seconds() / 3600)
                rate = raw_line['rate']
                notes = raw_line['notes']

                line = prices.get(notes, {})
                if not line:
                    line = {
                        'hours': units,
                        'description': notes,
                        'calc_rate': rate,
                        'amount': rate * units,
                        'type': PayslipLine.TYPE_CHOICES.wages
                    }
                    prices[notes] = line
                else:
                    line.update({
                        'hours': line['hours'] + units,
                        'amount': line['amount'] + rate * units
                    })

        return list(prices.values())

    @classmethod
    def generate_pdf(cls, payslip):
        template = get_template('payment/payslips.html')

        domain = get_site_url(master_company=payslip.company)

        context = {
            'lines': payslip.payslip_lines.all(),
            'payslip': payslip,
            'company': payslip.company,
            'candidate': payslip.candidate,
            'STATIC_URL': '%s/static' % domain,
            'DOMAIN': domain
        }

        pdf_file = cls._get_file_from_str(str(template.render(context)))

        folder, created = Folder.objects.get_or_create(
            parent=payslip.company.files,
            name='invoices',
        )
        file_name = 'invoice_{}_{}_{}.pdf'.format(
            payslip.cheque_number,
            date_format(payslip.from_date, 'Y_m_d'),
            date_format(payslip.to_date, 'Y_m_d')
        )
        file_obj, created = File.objects.get_or_create(
            folder=folder,
            name=file_name,
            file=ContentFile(pdf_file.read(), name=file_name)
        )

    def prepare_candidate(self, candidate, company, from_date, to_date):
        try:
            return Payslip.objects.filter(
                company=company,
                candidate=candidate,
                to_date=to_date,
                from_date=from_date,
            ).latest('from_date')
        except Payslip.DoesNotExist:
            pass

        lines = self.calculate(candidate, from_date)

        if lines:
            min_rate = SkillRel.objects.filter(candidate_contact=candidate).order_by('hourly_rate').first()

            payslip = Payslip.objects.create(
                candidate=candidate,
                hourly_rate=min_rate.hourly_rate,
                from_date=from_date,
                to_date=to_date,
                company=company,
            )

            payslip_lines = []

            for line in lines:
                payslip_lines.append(PayslipLine(payslip=payslip, **line))

            PayslipLine.objects.bulk_create(payslip_lines)

            gross_pay = payslip.get_gross_pay()
            if candidate.superannuation_fund and gross_pay > 450:
                PayslipLine.objects.create(
                    payslip=payslip,
                    description='Superannuation - %s' % candidate.superannuation_fund.name,
                    amount=gross_pay * Decimal('0.095'),
                    type=PayslipLine.TYPE_CHOICES.superannuation
                )

            self.generate_pdf(payslip)

    def prepare(self, company, to_date, from_date):
        to_date = to_date or company.today_tz

        candidate_ids = JobOffer.objects.filter(
            shift__date__job__provider_company=company
        ).values_list('candidate_contact', flat=True).distinct()

        for candidate_id in candidate_ids:
            unsigned = TimeSheet.objects.filter(
                job_offer__candidate_contact_id=candidate_id
            ).exclude(
                candidate_submitted_at__isnull=False,
                supervisor_approved_at__isnull=False,
            )

            if not unsigned.exists():
                candidate = CandidateContact.objects.get(id=candidate_id)
                self.prepare_candidate(candidate, company, from_date, to_date)
