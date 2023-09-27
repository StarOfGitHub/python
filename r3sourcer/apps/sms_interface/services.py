import logging
from abc import ABCMeta, abstractmethod

from django.conf import settings
from django.db import transaction
from phonenumber_field.phonenumber import PhoneNumber

from r3sourcer.apps.core.models import Contact, Company
from r3sourcer.apps.core.service import factory
from r3sourcer.apps.core.utils.companies import get_site_master_company
from .exceptions import SMSServiceError, AccountHasNotPhoneNumbers, SMSBalanceError, SMSDisableError
from .helpers import get_sms
from .models import SMSMessage, SMSTemplate

logger = logging.getLogger(__name__)


class BaseSMSService(metaclass=ABCMeta):

    def get_template(self, contact: Contact, master_company: Company, tpl_name: str) -> SMSTemplate:
        # notification language selection
        if contact.is_candidate_contact():
            languages = contact.languages.order_by('-default')

        elif contact.is_company_contact():
            languages = master_company.languages.order_by('-default')

        # template selection
        templates = SMSTemplate.objects.filter(slug=tpl_name, company=master_company)
        template = None

        for lang in languages:
            try:
                template = templates.get(language=lang.language)
                break
            except SMSTemplate.DoesNotExist:
                continue

        if template is None:
            template = templates.filter(language_id=settings.DEFAULT_LANGUAGE).first()

        if template is None:
            logger.exception('Cannot find sms template with name %s', tpl_name)
            # raise Exception('Cannot find sms template with name:', tpl_name)

        return template

    @transaction.atomic
    def send(self, to_number, text, from_number, related_obj=[], **kwargs):
        if isinstance(to_number, PhoneNumber):
            to_number = to_number.as_e164

        if isinstance(from_number, PhoneNumber):
            from_number = from_number.as_e164

        recipient = self._get_recipient(to_number)
        recipient_company = recipient.get_closest_company()
        from_number = self.get_from_number(from_number, recipient_company)
        company = self.can_send_sms(to_number, recipient_company)

        if not company:
            return

        sms_message = get_sms(from_number=from_number, to_number=to_number, text=text, company=company, **kwargs)

        try:
            self.sms_disable(company)
            self.substract_sms_cost(company, sms_message)

            sms_message.save()
            related_objs = kwargs.pop('related_objs', [])
            objs = [related_obj, *related_objs]
            sms_message.add_related_objects(*objs)

            self.process_sms_send(sms_message)

            logger.info("Message sent: sid={}; to_number={}".format(
                sms_message.sid, sms_message.to_number)
            )
        except SMSServiceError as e:
            sms_message.error_message = str(e)
        except SMSBalanceError:
            sms_message.error_code = "No Funds"
            sms_message.error_message = "SMS balance should be positive, your is: {}".format(company.sms_balance.balance)
            # raise SMSBalanceError(sms_message.error_message)
        except SMSDisableError:
            sms_message.error_code = "SMS disabled"
            sms_message.error_message = "SMS sending is disabled for company {}, your SMS balance is: {}".format(company, company.sms_balance.balance)
            # raise SMSDisableError(sms_message.error_message)
        except AccountHasNotPhoneNumbers:
            if sms_message and sms_message.pk:
                sms_message.delete()
        finally:
            sms_message.save()

        return sms_message

    @transaction.atomic
    def send_tpl(self, contact_obj, master_company_obj, tpl_name, related_obj=[], from_number=None, **kwargs):

        template = self.get_template(contact_obj, master_company_obj, tpl_name)

        if kwargs.get('new_phone_mobile') == True:
            phone_mobile = contact_obj.new_phone_mobile
        else:
            phone_mobile = contact_obj.phone_mobile

        if template:
            message = template.compile(**kwargs)['text']
            sms_message = self.send(phone_mobile, message, from_number, related_obj, **kwargs)
            if sms_message is not None:
                sms_message.template = template
                sms_message.save()

            return sms_message

    @abstractmethod
    def process_sms_send(self, sms_message):
        """
        Actually send SMS message

        should throws SMSServiceError if error occurred
        """
        pass  # pragma: no cover

    def fetch(self):
        try:
            sms_messages = self.process_sms_fetch()
        except SMSServiceError:
            logger.exception("Error occurred on SMS messages fetch")
        else:
            for sms_message in sms_messages:
                self._process_sms(sms_message)

    @transaction.atomic
    def _process_sms(self, sms_message):
        db_sms = SMSMessage.objects.filter(
            sid=sms_message.sid,
        ).all()
        for sms in db_sms:
            sms.is_fetched = True
            sms.save()

        logger.info(
            'Receive new message: type: %s; %s(%s)',
            sms_message.type, sms_message.id, sms_message
        )

        if sms_message.status == SMSMessage.STATUS_CHOICES.RECEIVED:
            sent_message = sms_message.get_sent_by_reply()
        else:
            sent_message = None

        if sms_message.type == SMSMessage.TYPE_CHOICES.SENT:
            # if it is new message, sent by another system (message not in local database),
            # then check delivered status after timeout by cron
            sms_message.check_delivered = True
            sms_message.save(update_fields=['check_delivered'])
            return

        if sms_message.is_answer():
            self.process_sms_answer(sms_message, sent_message)
            return

        if sms_message.is_stop_message():
            Contact.objects.filter(phone_mobile=sms_message.from_number).update(is_available=False)
            logger.info('Process stop message: {}'.format(sms_message.from_number))
            return

        if sms_message.is_start_message():
            Contact.objects.filter(phone_mobile=sms_message.from_number).update(is_available=True)
            logger.info('Process start message: {}'.format(sms_message.from_number))
            return

        # WARNING: Cycle sms sending
        # if sms_message.is_login():
        #     contact = Contact.objects.filter(phone_mobile=sms_message.from_number).last()
        #     if contact:
        #         login_service = factory.get_instance('login')
        #         login_service.send_login_sms(contact)
        #         logger.info('Process login message: {}'.format(sms_message.from_number))
        #     return

        if not sms_message.is_answer():
            self.process_ambiguous_answer(sms_message, sent_message)
            return

    def process_sms_answer(self, sms_message, sent_message):
        logger.info("Sent reply message: {}. id: {}".format(
            sent_message, getattr(sent_message, 'id', '-'))
        )

        positive = self._is_positive(sms_message)

        new_phone_mobile_contact = sms_message.new_phone_mobile_contact()
        if new_phone_mobile_contact:

            logger.info('Confirm new phone mobile number. Related object: {}; Answer: {}'.format(
                new_phone_mobile_contact, positive
            ))
            new_phone_mobile_contact.process_new_phone_mobile_reply(positive=positive)
            return

        if not sms_message.has_contact_relation():
            logger.error("Can't find Contact with numbers: {}, {}".format(
                sms_message.from_number, sms_message.to_number)
            )
            return

        if sent_message:
            sms_message.add_related_objects(*sent_message.get_related_objects())
            sent_message.no_check_reply()

        elif sms_message.is_late_reply():
            sent_message = sms_message.get_sent_by_reply(check_reply=False)
            # add related object to late reply
            sms_message.add_related_objects(*sent_message.get_related_objects())
            sent_message.late_reply = sms_message
            sent_message.save(update_fields=['late_reply_id'])
            logger.info('Received late reply for message {}: sent: {}; reply: {};'.format(
                sent_message, sent_message.id, sms_message.id
            ))

        if sent_message is not None:
            related_objects = sent_message.get_related_objects()
        else:
            related_objects = []

        for related_object in [x for x in related_objects if hasattr(x, 'process_sms_reply')]:
            logger.info('Run process_sms_reply. Related object: {}; Answer: {}'.format(
                related_object, positive
            ))
            related_object.process_sms_reply(sent_sms=sent_message,
                                             reply_sms=sms_message,
                                             positive=positive)

    @classmethod
    def _is_positive(cls, sms_message):
        positive = None
        if sms_message.is_positive_answer():
            positive = True
        elif sms_message.is_negative_answer():
            positive = False
        return positive

    @classmethod
    def process_ambiguous_answer(cls, sms_message, sent_message):
        if sent_message:
            sms_message.add_related_objects(*sent_message.get_related_objects())

    @abstractmethod
    def process_sms_fetch(self):
        """
        Actually fetch SMS messages

        should throws SMSServiceError if error occurred
        """
        pass  # pragma: no cover

    @classmethod
    def get_sender_phones(self, contact):
        """
        Get sender phones
        """
        return []

    def _get_recipient(self, to_number):
        contact = Contact.objects.filter(phone_mobile=to_number).first()

        if contact and not contact.sms_enabled:
            return

        return contact

    def can_send_sms(self, to_number, company=None):
        if not company:
            return

        if self._get_recipient(to_number) is None:
            return

        master_company = company.get_closest_master_company()

        if not master_company.company_settings.sms_enabled:
            logger.info('SMS sending is disabled for company {}'.format(master_company))
            return None

        return company

    def get_from_number(self, from_number, master_company):
        return from_number

    def substract_sms_cost(self, company, sms_message):
        if company.sms_balance:
            if company.sms_balance.balance > 0:
                company.sms_balance.substract_sms_cost(sms_message.segments)
            else:
                raise SMSBalanceError()
        else:
            SMSServiceError('There is no SMSBalance for that company')

    def sms_disable(self, company):
        if not company.sms_enabled:
            raise SMSDisableError()


class FakeSMSService(BaseSMSService):

    def process_sms_send(self, sms_message):
        company = get_site_master_company()
        from_number = company.phone_numbers.first()

        if from_number:
            from_number = from_number.phone_number
            sms_message.from_number = from_number

        sms_message.sid = 'FAKE_%s' % sms_message.id
        sms_message.save(update_fields=['sid', 'from_number'])

    def process_sms_fetch(self):
        res = []
        for sms in SMSMessage.objects.filter(is_fake=True):
            if not sms.sid.startswith('FAKE'):
                sms.sid = 'FAKE_%s' % sms.id
            sms.is_fake = False
            sms.save(update_fields=['sid', 'is_fake'])
            res.append(sms)
        return res

    def substract_sms_cost(self, company, sms_message):
        pass

    def can_send_sms(self, to_number, company=None):
        company = get_site_master_company()
        if self._get_recipient(to_number) is None:
            return

        return company if company.company_settings.sms_enabled else None
