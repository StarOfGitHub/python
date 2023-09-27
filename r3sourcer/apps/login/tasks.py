from celery import shared_task
from celery.utils.log import get_task_logger
from django.conf import settings
from django.db import transaction

from r3sourcer.apps.core.models import Contact, Company
from r3sourcer.apps.core.service import factory
from r3sourcer.apps.core.utils.utils import is_valid_email, is_valid_phone_number
from .models import TokenLogin
from ..core.utils.companies import get_site_master_company, get_site_url

logger = get_task_logger(__name__)


def get_contact(contact_id):
    try:
        contact = Contact.objects.get(id=contact_id)
    except Contact.DoesNotExist as e:
        logger.exception(e)
    else:
        return contact


DEFAULT_LOGIN_REDIRECT = '/'


def send_login_token(contact, send_func, tpl_name, redirect_url=None,
                     type_=TokenLogin.TYPES.sms, master_company_id=None):
    if not redirect_url:
        redirect_url = DEFAULT_LOGIN_REDIRECT
    with transaction.atomic():
        if not master_company_id:
            master_company = contact.get_closest_company()
        else:
            try:
                master_company = Company.objects.get(pk=master_company_id)
            except Company.DoesNotExist as e:
                raise Exception(e)

        token_login = TokenLogin.objects.create(contact=contact,
                                                type=type_,
                                                redirect_to=redirect_url)

        site_url = get_site_url(master_company=master_company)
        data_dict = dict(
            contact=contact,
            auth_url="%s%s" % (site_url, token_login.auth_url),
            project_url=site_url,
            related_obj=contact,
        )

        logger.info('Prepared Login token for contact %s. URL: %s',
                    contact,
                    data_dict['auth_url'])
        if type_ in (TokenLogin.TYPES.sms,):
            send_func(contact, master_company, tpl_name, **data_dict)
        elif type_ in (TokenLogin.TYPES.email,):
            send_func(contact, master_company, tpl_name, **data_dict)
        else:
            raise Exception('Unknown login  token type')


@shared_task(bind=True)
def send_login_sms(self, contact_id, redirect_url=None):
    sms_interface = factory.get_instance(
        getattr(settings, 'SMS_INTERFACE_CLASS', 'sms_interface')
    )

    sms_tpl = 'login-token'

    contact = get_contact(contact_id)

    if contact is not None:
        send_login_token(contact, sms_interface.send_tpl, sms_tpl, redirect_url)


@shared_task(bind=True)
def send_login_email(self, contact_id, master_company_id=None):
    email_interface = factory.get_instance(
        getattr(settings, 'EMAIL_INTERFACE_CLASS', 'email_interface')
    )

    email_tpl = 'login-token'

    contact = get_contact(contact_id)
    if contact is not None:
        send_login_token(contact, email_interface.send_tpl, email_tpl, type_=TokenLogin.TYPES.email,
                         master_company_id=master_company_id)


def send_login_message(username, contact):
    email_username = is_valid_email(username)
    mobile_phone_username = is_valid_phone_number(username, country_code=None)
    master_company = contact.get_closest_company()
    if email_username is False and mobile_phone_username is False:
        raise Exception('Invalid email or phone number')
    elif mobile_phone_username is False:
        send_login_email.delay(contact.id, master_company.id)
    elif email_username is False:
        send_login_sms.delay(contact.id)
