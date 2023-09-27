from celery.utils.log import get_task_logger
from django.db.models import Q, F

from r3sourcer.apps.company_settings.models import MYOBSettings
from r3sourcer.apps.myob.api import MYOBClient
from r3sourcer.apps.myob.models import MYOBCompanyFileToken
from r3sourcer.apps.myob.services.exceptions import MYOBClientException


logger = get_task_logger(__name__)


def get_myob_settings(company_id) -> dict:
    qs = MYOBSettings.objects.filter(
        company_id=company_id
    ).annotate(
        time_sheet_company_file_id=F('timesheet_company_file_id'),
        invoice_company_file_id=F('invoice_company_file_id'),
    ).values(
        'time_sheet_company_file_id',
        'invoice_company_file_id',
        'company_id',
    )

    try:
        settings = qs.get()
    except MYOBSettings.DoesNotExist:
        logger.error('MYOBSettings for company with id=%s does not exist'
                     % company_id)
        return {}
    return settings


def get_myob_client(company_id, myob_company_file_id=None, date=None):
    """
    :param company_id:
    :param myob_company_file_id:
    :param date:
    :return:
    TODO: adapt date to company timezone
    TODO: Make filter logic more strict
    TODO: Make sort order more clearly,
          because only one myob file token obj should be correct
          and only one have to use for myob connection at same time
    """
    qs = MYOBCompanyFileToken.objects.filter(
        company_id=company_id,
    )
    if myob_company_file_id is not None:
        qs = qs.filter(
            company_file_id=myob_company_file_id,
        )
    if date is not None:
        qs = qs.filter(
            (Q(enable_from__isnull=True) | Q(enable_from__lte=date)) &
            (Q(enable_until__isnull=True) | Q(enable_until__gte=date))
        )

    cft = qs.first()

    if not cft:
        raise MYOBClientException('Company File Token could not been provided')

    return MYOBClient(cf_data=cft)
