from celery import shared_task
from celery.utils.log import get_task_logger

from .exceptions import SMSServiceError
from .utils import get_sms_service
from ..candidate.models import CandidateRel
from ..candidate.tasks import buy_candidate
from ..core.models import User

logger = get_task_logger(__name__)


@shared_task(bind=True)
def fetch_remote_sms(self):
    try:
        sms_service = get_sms_service()
        sms_service.fetch()
    except SMSServiceError as e:
        logger.exception('Cannot fetch SMS messages. Error: %s', e)


@shared_task(bind=True)
def parse_sms_response(self, phone_number=None):
    if phone_number:
        try:
            user = User.objects.get(contact__phone_mobile=phone_number)
            if user.contact.candidate_contacts:
                rel = CandidateRel.objects.filter(
                    candidate_contact=user.contact.candidate_contacts,
                    sharing_data_consent=False
                ).first()
                rel.sharing_data_consent=True
                rel.save()
                buy_candidate.apply_async([rel.pk, str(user.id)])
                logger.info('User shared consent to CandidateRel: %s', rel.pk)

        except User.DoesNotExist as e:
            logger.exception('Cannot find the User during parse SMS response. Error: %s', e)
        except Exception as e:
            logger.exception('An error raises during parse sms response. Error: %s', e)
