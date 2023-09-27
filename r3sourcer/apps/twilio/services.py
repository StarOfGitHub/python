import logging

from r3sourcer.apps.core.utils.companies import get_master_companies_by_contact
from r3sourcer.apps.sms_interface.exceptions import AccountHasNotPhoneNumbers
from r3sourcer.apps.sms_interface.services import BaseSMSService
from r3sourcer.apps.twilio import models
from r3sourcer.helpers.datetimes import utc_now

logger = logging.getLogger(__name__)


class TwilioSMSService(BaseSMSService):
    def process_sms_send(self, sms_message):
        recipient = self._get_recipient(sms_message.to_number)
        from_number = self.get_from_number(sms_message.from_number, recipient.get_closest_company())

        if from_number:
            sms_message.from_number = from_number
            twilio_account = models.TwilioAccount.objects.get(phone_numbers__phone_number=from_number)
        else:
            logger.warning('Cannot find Twilio number')
            raise AccountHasNotPhoneNumbers
        response_ = twilio_account.client.api.account.messages.create(
            body=sms_message.text, from_=from_number, to=sms_message.to_number
        )
        sms_message.sid = response_.sid
        sms_message.save(update_fields=['sid', 'from_number'])

    def process_sms_fetch(self):
        sms_list = []

        """ Fetch all credentials from db """
        c_items = models.TwilioCredential.objects.all()

        for c in c_items.iterator():
            """ Update current credential (numbers, accounts, messages) """
            phone_numbers = []
            last_sync = utc_now()
            for n in c.client.api.incoming_phone_numbers.stream():
                phone_numbers.append(models.TwilioPhoneNumber.fetch_remote(n, c.company))

            for remote_account in c.client.api.accounts.stream():
                account = models.TwilioAccount.fetch_remote(c, remote_account)

                """ Update current account (messages) """
                params = {
                    'date_sent_after': account.get_last_sync()
                }  # get all messages sent_at after `self.get_last_sync()`

                acc_last_sync = utc_now().date()
                logger.info("Sync params: {}".format(params))

                for sms_message in remote_account.messages.stream(**params):
                    sms_list.append(models.TwilioSMSMessage.fetch_remote(account, sms_message))

                account.last_sync = acc_last_sync
                account.save(update_fields=['last_sync'])

            acc_sid_list = models.TwilioPhoneNumber.objects.filter(twilio_accounts=None).values_list(
                'account_sid', flat=True
            )

            for sid in acc_sid_list:
                if models.TwilioAccount.objects.filter(sid=sid).exists():
                    models.TwilioAccount.objects.get(sid=sid).phone_numbers.add(
                        *models.TwilioPhoneNumber.objects.filter(account_sid=sid)
                    )

            c.last_sync = last_sync
            c.save(update_fields=['last_sync'])

        return sms_list

    @classmethod
    def get_sender_phones(cls, contact):
        companies = get_master_companies_by_contact(contact)
        return models.TwilioPhoneNumber.objects.filter(company__in=companies)

    def get_from_number(self, from_number, master_company):
        try:
            twilio_account = models.TwilioAccount.objects.get(phone_numbers__phone_number=from_number)
        except models.TwilioAccount.DoesNotExist:
            twilio_account = models.TwilioAccount.objects.filter(credential__company=master_company).last()

        if not twilio_account:
            logger.warning('Cannot find Twilio number')
            return

        from_number = twilio_account.phone_numbers.filter(is_default=True, sms_enabled=True).first()
        if from_number:
            from_number = from_number.phone_number

        return from_number
