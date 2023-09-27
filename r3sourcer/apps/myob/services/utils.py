from r3sourcer.apps.candidate.models import CandidateContact
from r3sourcer.apps.core.models import Company
from r3sourcer.apps.hr.models import TimeSheet
from r3sourcer.apps.myob.services.candidate import CandidateSync
from r3sourcer.apps.myob.services.company import CompanySync


def sync_candidate_contacts_to_myob(myob_client=None, account=None):
    """
    Sync candidate contacts to myob service.
    Sync would be used for only candidate contacts on active state and with signed time sheets.

    :param myob_client: object api.client
    :param account: object Account
    :return:
    """

    sync = CandidateSync(myob_client)

    # get ids only signed time sheets
    candidates_with_signed_timesheets = TimeSheet.objects.filter(
        candidate_submitted_at__isnull=False,
        supervisor_approved_at__isnull=False,
    ).values_list('job_offer__candidate_contact__id', flat=True)

    # get only active candidate contacts
    candidate_contacts = CandidateContact.objects.filter(id__in=candidates_with_signed_timesheets).distinct()

    for candidate_contact in candidate_contacts:
        sync.sync_to_myob(candidate_contact, partial=True)


def get_latest_state(obj):
    if not obj:
        return None

    state = obj.get_active_states().first()
    return state.state.name_after_activation or state.state.name_before_activation if state else None


def get_company_rel(company):
    return company.regular_companies.last()


def get_latest_state_new(obj):
    if obj and obj.type == Company.COMPANY_TYPES.regular:
        obj = get_company_rel(obj)

    return get_latest_state(obj)


def sync_companies_to_myob(api_client, company_id):
    comp = Company.objects.get(pk=company_id)

    sync = CompanySync(api_client)
    # TODO: refactor this, bcs state 'Active' is hardcoded
    # TODO: Find more elegant solution, bcs <get_latest_state_new(x)> fired queries for each company,
    #       it is potential bottleneck
    for company in [x for x in Company.objects.owned_by(comp) if get_latest_state_new(x) == 'Active']:
        sync.sync_to_myob(company, partial=True)
