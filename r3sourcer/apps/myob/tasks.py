import datetime

from celery import shared_task
from celery.utils.log import get_task_logger

from django.db.models import Q, F

from r3sourcer.apps.candidate.models import CandidateContact
from r3sourcer.apps.core.models import Company, Invoice
from r3sourcer.apps.core.tasks import one_task_at_the_same_time
from r3sourcer.apps.hr.models import TimeSheet
from r3sourcer.apps.myob.services.exceptions import MYOBServerException
from r3sourcer.apps.myob.helpers import get_myob_client, get_myob_settings
from r3sourcer.apps.myob.models import MYOBRequestLog
from r3sourcer.apps.myob.services.invoice import InvoiceSync
from r3sourcer.apps.myob.services.timesheet import TimeSheetSync
from r3sourcer.apps.myob.services.utils import sync_candidate_contacts_to_myob, sync_companies_to_myob
from r3sourcer.celeryapp import app
from r3sourcer.helpers.datetimes import utc_now

logger = get_task_logger(__name__)


def retry_on_myob_error(origin_task):
    def wrap(self, *args, **kwargs):
        try:
            origin_task(self, *args, **kwargs)
        except MYOBServerException:
            self.retry(args=args, kwargs=kwargs, countdown=60)
    wrap.__name__ = origin_task.__name__
    wrap.__module__ = origin_task.__module__
    return wrap


@app.task(bind=True)
def sync_company_to_myob(self, settings, regular_company_id, master_company_id):
    if settings.get('time_sheet_company_file_id'):
        sync_candidate_contacts_myob.apply_async(args=[settings['time_sheet_company_file_id'],
                                                       regular_company_id,
                                                       master_company_id])

    if settings.get('invoice_company_file_id'):
        sync_active_companies_to_myob(settings['invoice_company_file_id'],
                                      master_company_id)


@app.task(bind=True)
def sync_active_companies_to_myob(self, company_file_id, master_company_id):
    """Pay attention company file id should have been associated
       with time invoice company file id
    """
    myob_client = get_myob_client(company_id=master_company_id,
                                  myob_company_file_id=company_file_id)
    sync_companies_to_myob(myob_client, master_company_id)


@app.task(bind=True)
def sync_candidate_contacts_myob(self, company_file_id, regular_company_id, master_company_id):
    """Pay attention company file id should have been associated
       with time sheet company file id
    """
    myob_client = get_myob_client(company_id=master_company_id,
                                  myob_company_file_id=company_file_id)
    sync_candidate_contacts_to_myob(myob_client, regular_company_id)


@app.task(bind=True)
@one_task_at_the_same_time()
@retry_on_myob_error
def sync_to_myob(self):
    """
    Sync candidate contacts, clients, jobsites to myob.
    """

    companies = Company.objects.filter(
        Q(myob_settings__invoice_company_file__isnull=False) |
        Q(myob_settings__timesheet_company_file__isnull=False)
    ).values_list('id', flat=True)
    for company_id in companies:
        settings = get_myob_settings(company_id)
        sync_company_to_myob(settings, company_id, company_id)


@app.task(bind=True)
@retry_on_myob_error
def sync_timesheets(self):
    companies = Company.objects.filter(type=Company.COMPANY_TYPES.master)

    for company in companies:
        settings = get_myob_settings(company.id)

        if not settings.get('time_sheet_company_file_id'):
            logger.warn('Company %s has no TimeSheet Company Files configured', str(company))
            continue

        myob_client = get_myob_client(company_id=company.id,
                                      myob_company_file_id=settings['time_sheet_company_file_id'])

        sync_service = TimeSheetSync(myob_client)

        candidates = CandidateContact.objects.owned_by(company)
        for candidate in candidates:
            sync_service.sync_to_myob(candidate)

        logger.warn('Sync Timesheets for company %s finished', str(company))


@app.task(bind=True)
@one_task_at_the_same_time
def clean_myob_request_log(self):
    """
    Clean myob request logs from db.
    """

    today = utc_now().date()
    MYOBRequestLog.objects.filter(created__date__lt=today).delete()


@shared_task
def sync_invoice(invoice_id):
    invoice = Invoice.objects.get(id=invoice_id)
    if invoice.sync_status in (Invoice.SYNC_STATUS_CHOICES.sync_scheduled,
                               Invoice.SYNC_STATUS_CHOICES.syncing):
        logger.warn('Sync process already running for invoice %s' % invoice_id)
        return

    if invoice.sync_status in (Invoice.SYNC_STATUS_CHOICES.not_synced,
                               Invoice.SYNC_STATUS_CHOICES.synced,
                               Invoice.SYNC_STATUS_CHOICES.sync_failed):
        invoice.set_sync_status(Invoice.SYNC_STATUS_CHOICES.sync_scheduled)

    company = invoice.provider_company

    cf_id = None
    if company.myob_settings.invoice_company_file:
        company_file = company.myob_settings.invoice_company_file
        cf_id = company_file.id

    client = get_myob_client(company_id=company.id, myob_company_file_id=cf_id)
    service = InvoiceSync(client)

    params = {"$filter": "Number eq '%s'" % invoice.number}
    synced_invoice = client.api.Sale.Invoice.TimeBilling.get(params=params)

    synced = False
    try:
        invoice.set_sync_status(Invoice.SYNC_STATUS_CHOICES.syncing)
        if synced_invoice['Count']:
            if synced_invoice['Count'] > 1:
                invoice.set_sync_status(Invoice.SYNC_STATUS_CHOICES.sync_failed)
                raise Exception("Got 2 or more invoices with id %s from MYOB." % invoice.id)

            synced_invoice_lines = synced_invoice['Items'][0]['Lines']

            if len(synced_invoice_lines) < invoice.invoice_lines.count():
                service.sync_to_myob(invoice, partial=True)
                synced = True
            if len(synced_invoice_lines) == invoice.invoice_lines.count():
                # update old invoices with sync field
                synced = True
        else:
            service.sync_to_myob(invoice)
            synced = True
    except ValueError:
        logger.warn('Sync to MYOB failed')
        invoice.set_sync_status(Invoice.SYNC_STATUS_CHOICES.sync_failed)
    else:
        if synced:
            invoice.synced_at = invoice.now_utc
            invoice.sync_status = Invoice.SYNC_STATUS_CHOICES.synced
            invoice.save(update_fields=['synced_at', 'sync_status'])


@app.task(bind=True)
@retry_on_myob_error
def sync_time_sheet(self, time_sheet_id, resync=False):
    qs = TimeSheet.objects.filter(
        pk=time_sheet_id
    ).annotate(
        regular_company_id=F('job_offer__shift__date__job__jobsite__regular_company_id'),
        master_company_id=F('job_offer__shift__date__job__jobsite__master_company_id'),
        candidate_contact_id=F('job_offer__candidate_contact_id'),
    ).values_list(
        'regular_company_id',
        'master_company_id',
        'candidate_contact_id',
    )
    try:
        regular_company_id, master_company_id, candidate_contact_id = qs.get()
    except TimeSheet.DoesNotExist:
        logger.warn('TimeSheet with id=%s does not exist')
        return

    settings = get_myob_settings(master_company_id)
    sync_candidate_contacts_myob.apply_async(args=[settings['time_sheet_company_file_id'],
                                                   regular_company_id,
                                                   master_company_id])

    candidate_contact = CandidateContact.objects.get(pk=candidate_contact_id)
    service = TimeSheetSync.from_candidate(settings, master_company_id)
    service.sync_single_to_myob(time_sheet_id, candidate_contact, resync)
