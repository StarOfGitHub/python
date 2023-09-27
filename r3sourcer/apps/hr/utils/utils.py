import logging
from collections import defaultdict
from datetime import timedelta
from functools import reduce
from itertools import chain
from urllib.parse import urlparse

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.template.defaulttags import register
from django.templatetags.static import static
from django.utils import formats

from r3sourcer.apps.candidate.models import CandidateContact
from r3sourcer.apps.core.models import InvoiceRule, Invoice, CompanyContact
from r3sourcer.apps.core.utils.geo import calc_distance, MODE_TRANSIT, MAX_DIMENSIONS
from r3sourcer.celeryapp import app
from r3sourcer.helpers.datetimes import utc_now, date2utc_date
from r3sourcer.apps.core.utils.companies import get_site_master_company

log = logging.getLogger(__name__)

WEEKDAY_MAP = {
    0: 'monday',
    1: 'tuesday',
    2: 'wednesday',
    3: 'thursday',
    4: 'friday',
    5: 'saturday',
    6: 'sunday',
}


def _time_diff(start, end):
    return timedelta(
        hours=end.hour - start.hour,
        minutes=end.minute - start.minute,
        seconds=end.second - start.second
    )


def get_invoice_rule(company):
    if company.invoice_rules.exists():
        return company.invoice_rules.first()
    else:
        master_company = company.get_master_company()[0]
        return master_company.invoice_rules.first()


def get_payslip_rule(company):
    if company.payslip_rules.exists():
        return company.payslip_rules.first()
    else:
        master_company = company.get_master_company()[0]
        return master_company.payslip_rules.first()


def create_or_update_distance_cache(contact, jobsite, distance):
    from ..models import ContactJobsiteDistanceCache
    if distance != -1 and distance["distance"]:
        updated_values = {
            "jobsite": jobsite,
            "contact": contact,
            "distance": distance["distance"],
            "time": distance["duration"]
        }

        obj, created = ContactJobsiteDistanceCache.objects.update_or_create(
            jobsite=jobsite, contact=contact, defaults=updated_values
        )


def calculate_distances_for_jobsite(contacts, jobsite):
    """
    Calculates and save distances between jobsite and contacts
    :param contacts: contacts list
    :param jobsite: jobsite object
    :return: limit of queries is not reached
    """
    contacts_dict = defaultdict(list)
    for contact in contacts:
        candidate = contact.candidate_contacts.filter(candidate_rels__master_company=get_site_master_company()).first()
        is_public = candidate.transportation_to_work == CandidateContact.TRANSPORTATION_CHOICES.public
        if hasattr(contact, 'candidate_contacts') and is_public:
            contacts_dict[MODE_TRANSIT].append(contact)
        else:
            contacts_dict[None].append(contact)

    for mode, contact_list in contacts_dict.items():
        addresses = []
        for contact in contact_list:
            active_address = contact.active_address
            if active_address:
                addresses.append(active_address.get_full_address())

        jobsite_address = jobsite.get_address()
        if jobsite_address is None:
            continue

        s = 0
        while s < len(addresses):
            segments = addresses[s:s + MAX_DIMENSIONS]
            s = s + MAX_DIMENSIONS

            result = calc_distance(jobsite_address.get_full_address(), segments, mode=mode)
            if not result:
                return bool(result)

            if len(contact_list) == 1:
                result = [result]

            for distance, contact in zip(result[0], contact_list):
                create_or_update_distance_cache(contact, jobsite, distance)

    return True


def send_jo_rejection(job_offer):  # pragme: no cover
    from r3sourcer.apps.hr.tasks import send_placement_rejection
    send_placement_rejection.delay(job_offer.pk)


def meters_to_km(meters):
    """
    Converts meters to kilometers
    """
    if meters:
        return round(int(meters) / 1000, 1)
    else:
        return 0


def seconds_to_hrs(seconds):
    """
    Converts seconds to hours
    """
    minutes = int(seconds) // 60
    hours = minutes // 60
    return "%02d:%02d" % (hours, minutes % 60)


def get_invoice_dates(invoice_rule, time_sheet):
    """
    Accepts invoice rule and returns date_from and date_to needed for invoice generation based on period setting.
    """

    date_from = None
    date_to = None
    today = time_sheet.shift_started_at_tz.date()
    weekday = time_sheet.shift_started_at_tz.date().weekday()

    if invoice_rule.period == InvoiceRule.PERIOD_CHOICES.daily:
        date_from = today
        date_to = date_from + timedelta(days=1)
    elif invoice_rule.period == InvoiceRule.PERIOD_CHOICES.weekly:
        date_from = today - timedelta(weekday)
        date_to = date_from + timedelta(days=7)
    elif invoice_rule.period == InvoiceRule.PERIOD_CHOICES.fortnightly:
        if invoice_rule.last_invoice_created:
            last_invoice_date = invoice_rule.last_invoice_created
            first_invoice_day = last_invoice_date - timedelta(days=last_invoice_date.weekday())

            date_from = first_invoice_day
            while True:
                days_spent = (today - date_from).days

                if days_spent > 14:
                    date_from += timedelta(days=14)
                else:
                    break

            date_to = date_from + timedelta(days=14)
        else:
            date_from = today - timedelta(today.weekday())
            date_to = date_from + timedelta(days=14)

    elif invoice_rule.period == InvoiceRule.PERIOD_CHOICES.monthly:
        date_from = today.replace(day=1)
        next_month = date_from.replace(day=28) + timedelta(days=4)
        date_to = next_month - timedelta(days=next_month.day)

    if not date_from:
        raise Exception("Wrong invoice rule period.")

    return date_from, date_to


def get_invoice(company, date_from, date_to, timesheet, invoice_rule):
    """
    Checks if needed invoice already exists and returns it to update with new timesheets.
    """
    qs = Invoice.objects
    qry = Q(
        invoice_lines__date__gte=date_from,
        invoice_lines__date__lt=date_to,
    )

    if invoice_rule.separation_rule == InvoiceRule.SEPARATION_CHOICES.one_invoice:
        qs = qs.filter(
            qry,
            customer_company=company
        )
    elif invoice_rule.separation_rule == InvoiceRule.SEPARATION_CHOICES.per_jobsite:
        jobsite = timesheet.job_offer.shift.date.job.jobsite
        qs = qs.filter(
            qry,
            invoice_lines__timesheet__job_offer__shift__date__job__jobsite=jobsite
        )
    elif invoice_rule.separation_rule == InvoiceRule.SEPARATION_CHOICES.per_candidate:
        candidate = timesheet.job_offer.candidate_contact
        qs = qs.filter(
            qry,
            customer_company=company,
            invoice_lines__timesheet__job_offer__candidate_contact=candidate
        )
    try:
        invoice = qs.latest('date')
    except ObjectDoesNotExist:
        invoice = None

    return invoice


def send_supervisor_timesheet_approve(timesheet, force=False, not_agree=False):
    from r3sourcer.apps.hr.tasks import send_supervisor_timesheet_sign

    contact = timesheet.supervisor.contact
    master_company = contact.get_closest_company()

    if not_agree:
        date_time = utc_now() + timedelta(hours=4)
        send_supervisor_timesheet_sign.apply_async(
            args=[timesheet.supervisor.id, timesheet.id, force, master_company.id], eta=date_time)
    else:
        send_supervisor_timesheet_sign.apply_async(
            args=[timesheet.supervisor.id, timesheet.id, force, master_company.id], countdown=30*60)


def send_job_confirmation_sms(job):
    from r3sourcer.apps.hr.tasks import send_job_confirmation_message
    send_job_confirmation_message.apply_async(args=[job.id], countdown=10)


def schedule_auto_approve_timesheet(timesheet):
    from r3sourcer.apps.hr.tasks import auto_approve_timesheet
    from uuid import UUID  # not remove
    for task in chain.from_iterable(app.control.inspect().scheduled().values()):
        if str(eval(task['request']['args'])[0]) == str(timesheet.id) and task['request']['name'] == \
                'r3sourcer.apps.hr.tasks.auto_approve_timesheet':
            app.control.revoke(task['request']['id'], terminate=True, signal='SIGKILL')
    date_time = utc_now() + timedelta(hours=4)
    auto_approve_timesheet.apply_async(args=[timesheet.id], eta=date_time)


def format_dates_range(dates_list):
    def _cmp_dates(value, element):
        if not value:
            return [[element]]
        current_group = value[-1]
        if element - current_group[-1] == timedelta(days=1):
            current_group.append(element)
        else:
            value.append([element])
        return value
    res_dates = reduce(_cmp_dates, dates_list, [])

    results = []
    for dates in res_dates:
        if len(dates) > 2:
            results.append('{}-{}'.format(
                formats.date_format(dates[0], 'd/m'),
                formats.date_format(dates[-1], 'd/m')
            ))
        else:
            results.extend([formats.date_format(fulldate, 'd/m') for fulldate in dates])

    return results


@register.simple_tag(takes_context=True)
def absstatic(context, path):
    static_url = static(path)
    parsed_url = urlparse(static_url)
    if not parsed_url.netloc:
        request = context['request']
        return request.build_absolute_uri(static_url)
    return static_url


@register.filter
def get_hours(time_delta):
    if not time_delta:
        return '0'
    hours = time_delta.total_seconds() / 3600
    return '{0:.2f}'.format(hours)
