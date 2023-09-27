import logging
import os
import smtplib
from abc import ABCMeta, abstractmethod
from email.message import EmailMessage

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Q

from r3sourcer.apps.core.models import Company, Contact, CompanyContact
from r3sourcer.apps.candidate.models import CandidateContact
from r3sourcer.apps.email_interface import models as email_models
from r3sourcer.apps.email_interface.exceptions import RecipientsInvalidInstance, EmailBaseServiceError
from r3sourcer.helpers.datetimes import utc_now

logger = logging.getLogger(__name__)

class BaseEmailService(metaclass=ABCMeta):

    def get_template(self, contact: Contact, master_company: Company, tpl_name: str) -> email_models.EmailTemplate:
        # notification language selection
        if contact.is_candidate_contact():
            languages = contact.languages.order_by('-default')

        elif contact.is_company_contact():
            languages = master_company.languages.order_by('-default')

        # template selection
        templates = email_models.EmailTemplate.objects.filter(slug=tpl_name, company=master_company)
        template = None

        for lang in languages:
            try:
                template = templates.get(language=lang.language)
                break
            except email_models.EmailTemplate.DoesNotExist:
                continue

        if template is None:
            template = templates.filter(language_id=settings.DEFAULT_LANGUAGE).first()

        if template is None:
            logger.exception('Cannot find email template with name %s', tpl_name)
            # raise Exception('Cannot find email template with name:', tpl_name)

        return template

    @transaction.atomic
    def send(self, recipients, subject, text_message, html_message=None, from_email=None, template=None, **kwargs):

        try:
            if not from_email:
                from_email = settings.NO_REPLY_EMAIL

            email_message = None
            if isinstance(recipients, str):
                to_addresses = recipients
            elif isinstance(recipients, (tuple, list)):
                to_addresses = ",".join(recipients)
            else:
                raise RecipientsInvalidInstance('Recipients should be either string or list')

            email_message = email_models.EmailMessage(
                state=email_models.EmailMessage.STATE_CHOICES.CREATED,
                sent_at=None,
                from_email=from_email,
                subject=subject,
                created_at=utc_now(),
                to_addresses=to_addresses,
                template=template
            )
            email_message.save()

            if text_message:
                email_models.EmailBody.objects.create(
                    content=text_message, type=email_models.TEXT_CONTENT_TYPE, message=email_message
                )

            if html_message:
                email_models.EmailBody.objects.create(
                    content=html_message, type=email_models.HTML_CONTENT_TYPE, message=email_message
                )

            files = kwargs.get('files', [])
            for f in files:
                root, ext = os.path.splitext(f.name)

                if ext in email_models.FILE_MIME_MAPPING:
                    email_models.EmailBody.objects.create(
                        file=f, type=email_models.FILE_MIME_MAPPING[ext], message=email_message
                    )

            self.process_email_send(email_message)

            logger.info("E-mail message sent: sid={}; recipients={}".format(
                email_message.message_id, email_message.to_addresses
            ))
        except EmailBaseServiceError as e:
            if email_message:
                email_message.error_message = str(e)
                email_message.save()

    @transaction.atomic
    def send_tpl(self, contact_obj, master_company_obj, tpl_name, from_email=None, **kwargs):

        template = self.get_template(contact_obj, master_company_obj, tpl_name)

        if kwargs.get('new_email') == True:
            email = contact_obj.new_email
        else:
            email = contact_obj.email

        if template:
            compiled = template.compile(**kwargs)
            subject = compiled['subject']
            self.send(email, subject, compiled['text'],
                    html_message=compiled['html'], from_email=from_email, template=template,
                    **kwargs
            )

    @abstractmethod
    def process_email_send(self, email_message):
        """
        Actually send e-mail message

        should throws EmailBaseServiceError or its subclasses if error occurred
        """
        pass  # pragma: no cover


class FakeEmailService(BaseEmailService):

    def process_email_send(self, email_message):
        email_message.message_id = 'FAKE_%s' % email_message.id
        email_message.save(update_fields=['message_id'])


class SMTPEmailService(BaseEmailService):

    def process_email_send(self, email_message):
        email_message.message_id = email_message.id
        email_message.state = email_models.EmailMessage.STATE_CHOICES.SENDING
        email_message.save(update_fields=['state', 'message_id'])

        is_no_reply_email = email_message.from_email == settings.DEFAULT_SMTP_EMAIL

        msg = EmailMessage()
        msg['From'] = email_message.from_email
        msg['To'] = email_message.to_addresses
        msg['Subject'] = str(email_message.subject)
        if not is_no_reply_email:
            msg.add_header('Reply-To', email_message.from_email)

        if email_message.has_text_message():
            msg.set_content(email_message.get_text_body())

        if email_message.has_html_message():
            msg.add_alternative(email_message.get_html_body(), subtype='html')

        body_files = email_message.bodies.filter(type__in=email_models.FILE_MIME_MAPPING.values())

        for body_file in body_files:
            maintype, subtype = body_file.type.split('/')
            msg._add_multipart(
                'mixed', body_file.file.file.read(),
                _disp='attachment; filename=' + body_file.file.name, maintype=maintype, subtype=subtype)

        smtp_server_args = {
            'host': settings.DEFAULT_SMTP_SERVER,
            'port': settings.DEFAULT_SMTP_PORT,
        }
        smpt_auth_args = {
            'user': settings.DEFAULT_SMTP_EMAIL,
            'password': settings.DEFAULT_SMTP_PASSWORD,
        }

        try:
            smtp_conn = smtplib.SMTP(**smtp_server_args)
            smtp_conn.ehlo()

            if settings.DEFAULT_SMTP_TLS:
                smtp_conn.starttls()
                smtp_conn.ehlo()

            smtp_conn.login(**smpt_auth_args)
            smtp_conn.send_message(msg, email_message.from_email, email_message.to_addresses.split(','))
            smtp_conn.close()

            email_message.state = email_models.EmailMessage.STATE_CHOICES.SENT
            email_message.save(update_fields=['state'])
        except Exception:
            logger.exception('Cannot send email using SMTP')

            email_message.state = email_models.EmailMessage.STATE_CHOICES.ERROR
            email_message.save(update_fields=['state'])
