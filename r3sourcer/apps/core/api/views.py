import copy
import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.utils.decorators import method_decorator
from django.utils.translation import ugettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status, permissions, viewsets
from rest_framework.response import Response
from rest_framework.views import exception_handler

from r3sourcer.apps.company_settings.models import GlobalPermission
from r3sourcer.apps.core import models
from r3sourcer.apps.core.api import serializers
from r3sourcer.apps.core.tasks import send_trial_email, cancel_trial, send_contact_verify_sms, send_verification_success_email
from r3sourcer.apps.core.utils.companies import get_site_master_company
from r3sourcer.helpers.datetimes import utc_now, tz2utc

User = get_user_model()


def core_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        new_response = {
            'status': 'error',
            'errors': response.data
        }
        response.data = new_response
    elif exc and hasattr(exc, 'messages'):
        data = {
            'status': 'error',
            'errors': {"non_field_errors": exc.messages if hasattr(exc, 'messages') else str(exc)}
        }
        response = Response(data, status=status.HTTP_400_BAD_REQUEST)

    return response


class TrialUserView(viewsets.GenericViewSet):

    permission_classes = [permissions.AllowAny]
    serializer_class = serializers.TrialSerializer

    @method_decorator(csrf_exempt)
    def create(self, request, *args, **kwargs):
        email = request.data['email']
        phone_mobile = request.data['phone_mobile']

        serializer = self.get_serializer(data=request.data)
        new_user = True
        if serializer.is_valid(raise_exception=False):

            user = User.objects.create_user(email=email, phone_mobile=phone_mobile)
            contact = user.contact
            contact.first_name = serializer.validated_data['first_name']
            contact.last_name = serializer.validated_data['last_name']
            contact.save(update_fields=['first_name', 'last_name'])

            # add permissions
            permission_list = GlobalPermission.objects.all()
            user.user_permissions.add(*permission_list)
            user.trial_period_start = utc_now()
            user.save()

            company_name = serializer.validated_data['company_name']
            website = serializer.validated_data['website']

        else:
            try:
                contact = models.Contact.objects.get(email=email,
                                                     phone_mobile=phone_mobile
                                                     )
                user = contact.user
                company_name = request.data['company_name']
                website = request.data['website']
                new_user = False

                if models.Company.objects.filter(name=company_name).exists():
                    return Response({'company_name': _('Company with this name already registered')},
                                    status=status.HTTP_400_BAD_REQUEST)
                if Site.objects.filter(domain=website).exists():
                    return Response({'website': _('Website address already registered')},
                                    status=status.HTTP_400_BAD_REQUEST)
            except:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # create new company contact
        company_contact = models.CompanyContact.objects.create(contact=contact)

        # add trial role
        trial_role = models.Role.objects.create(name=models.Role.ROLE_NAMES.trial)
        user.role.add(trial_role)

        company = models.Company.objects.create(
            name=company_name,
            type=models.Company.COMPANY_TYPES.master,
            primary_contact=company_contact,
        )

        models.CompanyRel.objects.create(master_company=company, regular_company=company)

        models.CompanyContactRelationship.objects.create(company=company, company_contact=company_contact)

        domain = '{}.{}'.format(website.lower(), settings.REDIRECT_DOMAIN)
        site, created = Site.objects.get_or_create(domain=domain, defaults={'name': domain})
        models.SiteCompany.objects.get_or_create(company=company, site=site)

        form, form_created = models.Form.objects.get_or_create(
            company=company,
            builder=models.FormBuilder.objects.get(
                content_type=ContentType.objects.get_by_natural_key('candidate', 'candidatecontact')
            ),
            defaults=dict(
                is_active=True
            )
        )

        models.FormLanguage.objects.get_or_create(
            form=form,
            title='Application Form',
            short_description='New application form',
            result_messages="You've been registered!"
        )

        if new_user:
            end_of_trial = utc_now() + datetime.timedelta(days=30)
            send_trial_email.apply_async([contact.id, company.id], countdown=10)
            utc_end_of_trial = tz2utc(end_of_trial)
            cancel_trial.apply_async([user.id], eta=utc_end_of_trial)

            send_contact_verify_sms.apply_async(args=(contact.id, contact.id))
        else:
            master_company = get_site_master_company(request=self.request)

            trial_role = contact.user.role.filter(name=models.Role.ROLE_NAMES.trial).first()
            if trial_role:
                email_tamplate = 'trial-e-mail-verification-success'
                contact.user.role.remove(trial_role)
            else:
                email_tamplate = 'e-mail-verification-success'

            send_verification_success_email.apply_async(
                args=(
                    contact.id, master_company.id, email_tamplate, request.data['website'] if trial_role else None
                ),
                countdown=10
            )

        return Response({
            'status': 'success',
            'message': _('Trial User registered successfully')
        })
