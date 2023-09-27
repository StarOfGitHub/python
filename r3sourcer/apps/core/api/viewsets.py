from cities_light.loading import get_model
import uuid
from django.apps import apps
from django.conf import settings
from django.contrib.auth import logout
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q, ForeignKey, FileField
from django.db.models.deletion import ProtectedError
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.utils.translation import ugettext_lazy as _

from rest_framework import viewsets, exceptions, status, fields
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from django_filters.rest_framework import DjangoFilterBackend

from r3sourcer.apps.acceptance_tests.models import AcceptanceTestAnswer, AcceptanceTestQuestion
from r3sourcer.apps.candidate.models import CandidateContact, CandidateRel
from r3sourcer.apps.core import tasks
from r3sourcer.apps.core.api.contact_bank_accounts.serializers import ContactBankAccountFieldSerializer
from r3sourcer.apps.core.api.fields import ApiBase64FileField
from r3sourcer.apps.core.api.mixins import GoogleAddressMixin
from r3sourcer.apps.core.models import BankAccountLayout, ContactBankAccount, BankAccountField, Contact
from r3sourcer.apps.core.models.dashboard import DashboardModule
from r3sourcer.apps.core.utils.address import parse_google_address
from r3sourcer.apps.core.utils.form_builder import StorageHelper
from r3sourcer.apps.core.utils.utils import normalize_phone_number, validate_phone_number
from r3sourcer.apps.myob.models import MYOBSyncObject
from r3sourcer.apps.pricing.models import Industry
from . import permissions, serializers
from .. import models, mixins
from ..decorators import get_model_workflow_functions
from ..service import factory
from ..utils.companies import get_master_companies_by_contact, get_site_master_company
from ..utils.user import get_default_company
from ..workflow import WorkflowProcess


class BaseViewsetMixin():
    related_setting = None

    list_fields = None

    def __init__(self, *args, **kwargs):
        if 'options' not in self.http_method_names:
            self.http_method_names = list(self.http_method_names) + ['options']

        super(BaseViewsetMixin, self).__init__(*args, **kwargs)

    def get_list_fields(self, request):
        return self.list_fields or []

    def dispatch(self, request, *args, **kwargs):
        self.list_fields = request.GET.getlist('fields', []) or request.GET.getlist('fields[]', [])
        self.related_setting = request.GET.get('related')

        return super(BaseViewsetMixin, self).dispatch(request, *args, **kwargs)

    def get_serializer_context(self):
        context = super(BaseViewsetMixin, self).get_serializer_context()
        if self.related_setting is not None:
            context['related_setting'] = self.related_setting

        return context


class BaseApiViewset(BaseViewsetMixin, viewsets.ModelViewSet):

    _exclude_data = {'__str__'}
    exclude_empty = False

    picture_fields = {'picture', 'logo'}
    phone_fields = []

    def _paginate(self, request, serializer_class, queryset=None, context=None):
        queryset = self.filter_queryset(self.get_queryset()) if queryset is None else queryset
        fields = self.get_list_fields(request)

        serializer_context = self.get_serializer_context()
        if context is not None:
            serializer_context.update(context)

        page = self.paginate_queryset(queryset)
        if page is not None:

            serializer = serializer_class(page, many=True, fields=fields, context=serializer_context)
            data = self.process_response_data(serializer.data, page)
            return self.get_paginated_response(data)

        serializer = serializer_class(queryset, many=True, fields=fields, context=serializer_context)
        data = self.process_response_data(serializer.data, queryset)
        return Response(data)

    def list(self, request, *args, **kwargs):
        return self._paginate(request, self.get_serializer_class())

    def retrieve(self, request, *args, **kwargs):
        fields = self.get_list_fields(request)

        instance = self.get_object()
        serializer = self.get_serializer(instance, fields=fields)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        data = self.prepare_related_data(request.data, is_create=True)
        data = self.clean_request_data(data)

        return self.create_from_data(data, *args, **kwargs)

    def create_from_data(self, data, *args, **kwargs):
        is_response = kwargs.pop('is_response', True)

        many = isinstance(data, list)

        serializer = self.get_serializer(data=data, many=many)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        if is_response:
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        else:
            return serializer

    def update(self, request, *args, **kwargs):
        data = self.prepare_related_data(request.data)
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}

        return Response(self.get_serializer(self.get_object()).data)

    def process_response_data(self, data, queryset=None):
        return data

    def prepare_related_data(self, data, is_create=False):
        return self._prepare_internal_data(data, is_create=is_create)

    def _prepare_internal_data(self, data, is_create=False):
        res = {}

        if isinstance(data, list):
            return [self._prepare_internal_data(item) if isinstance(item, dict) else item for item in data]

        for key, val in data.items():
            is_empty = val == '' or val is fields.empty
            if key in self._exclude_data or (self.exclude_empty and is_empty and (key != 'id' or len(data) > 1)):
                continue

            if isinstance(val, (dict, list)):
                res[key] = self._prepare_internal_data(val)
            else:
                res[key] = val

        return res['id'] if len(res) == 1 and 'id' in res else res

    def clean_request_data(self, data):
        if isinstance(data, list):
            return [self.clean_request_data(item) for item in data]

        return {
            k: v for k, v in data.items() if v is not None
        }

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
        except ProtectedError:
            raise exceptions.ValidationError({
                'message': 'Data you are trying to delete has relationships to other parts of '
                           'database so this cannot be deleted! '
            })
        return Response(status=status.HTTP_204_NO_CONTENT)


class ContactViewset(GoogleAddressMixin, BaseApiViewset):

    phone_fields = ['phone_mobile']
    raise_invalid_address = False


    def create(self, request, *args, **kwargs):

        master_company = get_site_master_company(request=self.request)
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid(raise_exception=False):
            contact = serializer.save()
            http_status = status.HTTP_201_CREATED
        else:
            contact = serializer.get_or_update()
            if contact:
                serializer = serializers.ContactSerializer(contact, many=False)
                http_status = status.HTTP_200_OK
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        models.ContactRelationship.objects.get_or_create(
            contact=contact,
            company=master_company
        )

        return Response(serializer.data, http_status)


    @action(methods=['get'], detail=False, permission_classes=[AllowAny])
    def validate(self, request, *args, **kwargs):
        email = request.GET.get('email')
        phone = request.GET.get('phone', '').strip()
        country_code = request.GET.get('country_code')

        if email is not None:
            try:
                validate_email(email)
                message = _('Email is valid')
            except ValidationError as e:
                raise exceptions.ValidationError({
                    'valid': False,
                    'message': e.message
                })
        elif phone is not None:
            phone = normalize_phone_number(phone, country_code)
            if not phone or validate_phone_number(phone, country_code) is False:
                raise exceptions.ValidationError({
                    'valid': False,
                    'message': _('Enter a valid Phone Number')
                })
            else:
                message = _('Phone Number is valid')
        else:
            raise exceptions.ValidationError({
                'valid': False,
                'message': _('Please specify Email or Phone Number')
            })

        return Response({
            'status': 'success',
            'data': {
                'valid': True,
                'message': message
            }
        })

    @action(methods=['get'], detail=False, permission_classes=[AllowAny])
    def exists(self, request, *args, **kwargs):
        email = request.GET.get('email')
        phone = request.GET.get('phone', '').strip()
        country_code = request.GET.get('country_code')
        message = ''

        if email and models.Contact.objects.filter(email=email).exists():
            message = _('User with this email already registered')
        elif phone:
            _phone = normalize_phone_number(phone, country_code)
            if validate_phone_number(_phone, country_code) is False:
                message = _('Invalid phone number %s' % phone)
            if validate_phone_number(_phone, country_code) is True \
                    and models.Contact.objects.filter(phone_mobile=_phone).exists():
                message = _('User with this phone number already registered')

        if message:
            return Response({
                'errors': {
                    'valid': False,
                    'message': message
                },
                'status': 'error'
            })

        return Response({
            'status': 'success'
        })

    @action(methods=['put'], detail=True)
    def password(self, request, *args, **kwargs):
        return self._update_password(serializers.ContactPasswordSerializer)

    @action(methods=['get'], detail=False, permission_classes=[AllowAny])
    def verify_email(self, request, *args, **kwargs):
        contact = get_object_or_404(models.Contact, verification_token=request.query_params.get('token'))
        contact.email_verified = True
        if contact.new_email:
            contact.email = contact.new_email
            contact.new_email = None
        contact.save(update_fields=['email_verified', 'new_email', 'email'])

        master_company = get_site_master_company(request=self.request)

        trial_role = contact.user.role.filter(name=models.Role.ROLE_NAMES.trial).first()
        if trial_role:
            email_tamplate = 'trial-e-mail-verification-success'
            contact.user.role.remove(trial_role)
        else:
            email_tamplate = 'e-mail-verification-success'

        tasks.send_verification_success_email.apply_async(
            args=(contact.id, master_company.id, email_tamplate), countdown=10
        )

        return Response({
            'status': 'success',
            'message': _('Thank you! Your email has been verified!'),
        })

    @action(methods=['post'], detail=False, permission_classes=[AllowAny])
    def forgot_password(self, request, *args, **kwargs):
        serializer = serializers.ContactForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.data['email']

        # Should pass master_company since request object is None in celery tasks.
        # If no master_company is passed, incorrect master company domain is extracted.
        try:
            contact = models.Contact.objects.get(email=email)
        except models.Contact.DoesNotExist as e:
            raise ValidationError('Contact with email = {} does not exist'.format(email))

        master_company = contact.get_closest_company()
        tasks.send_generated_password_email.delay(email, None, master_company.id)

        return Response({
            'status': 'success',
            'message': _('Password reset instructions were sent to this email address'),
        })

    @action(methods=['put'], detail=True)
    def change_password(self, request, *args, **kwargs):
        return self._update_password(serializers.ContactChangePasswordSerializer)

    @action(methods=['post'], detail=True)
    def send_password(self, request, *args, **kwargs):
        instance = self.get_object()
        is_sms = request.data.get('sms', False)
        is_email = request.data.get('email', False)
        new_password = models.User.objects.make_random_password(20)
        message = ''

        if is_email:
            tasks.send_generated_password_email.delay(instance.email, new_password)
            message = 'email'

        if is_sms:
            tasks.send_generated_password_sms.delay(instance.id, new_password)
            message = '{} and sms'.format(message) if is_email else 'sms'

        data = {
            'status': 'success',
            'message': _('New password was sent by {type}').format(type=message),
        }

        if (is_email or is_sms) and request.user.id == instance.user.id:
            logout(request)
            data['logout'] = True

        return Response(data)

    @action(methods=['post'], detail=True)
    def emails(self, request, *args, **kwargs):
        instance = self.get_object()
        manager = self.request.user.contact
        master_company = get_site_master_company(request=self.request)
        data = {
            'status': 'error',
            'message': 'Email already verified',
        }
        if not instance.email_verified:
            tasks.send_contact_verify_email.apply_async(
                args=(instance.id, manager.id, master_company.id))
            data = {'status': 'success'}

        return Response(data)

    @action(methods=['post'], detail=True)
    def smses(self, request, *args, **kwargs):
        instance = self.get_object()
        manager = self.request.user.contact
        data = {
            'status': 'error',
            'message': 'Mobile phone already verified',
        }
        if not instance.phone_mobile_verified:
            tasks.send_contact_verify_sms.apply_async(args=(instance.id, manager.id))
            data = {'status': 'success'}

        return Response(data)

    def _update_password(self, serializer_class):
        instance = self.get_object()
        serializer = serializer_class(instance.user, data=self.request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        data = {
            'status': 'success',
            'message': _('Password changed successfully')
        }

        if self.request.user.id == instance.user.id:
            logout(self.request)
            data['logout'] = True

        return Response(data)

    def prepare_related_data(self, data, is_create=False):
        data = super().prepare_related_data(data, is_create)

        if self.request.query_params.get('candidate') and not data.get('birthday'):
            raise exceptions.ValidationError({'birthday': _('Birthday is required')})

        return data

    @action(methods=['put'], detail=True)
    def change_email(self, request, *args, **kwargs):
        instance = self.get_object()
        new_email = request.data.get('new_email')
        password = request.data.get('password')

        if not new_email:
            raise exceptions.ValidationError({
                'new_email': _('Please specify a new_email field')
            })
        if not password:
            raise exceptions.ValidationError({
                'password': _('Please specify a password field')
            })
        if not instance.user.check_password(password):
            raise exceptions.ValidationError({
                'password': _('Password invalid')
            })
        if models.Contact.objects.filter(email=new_email).exists():
            raise exceptions.ValidationError({
                'new_email': _('User with this email address already registered')
            })

        instance.email_verified = False
        instance.new_email = new_email
        instance.save(update_fields=['email_verified', 'new_email'])

        # send verification email
        master_company = get_site_master_company()
        manager = master_company.primary_contact
        tasks.send_contact_verify_email.apply_async(
                args=(instance.id, manager.id, master_company.id), kwargs=dict(new_email=True))

        data = {
            'status': 'success',
            'message': _('An activation link has been sent to your new email address. Please confirm it. You must use the old email until the new email address is confirmed')
        }

        return Response(data)

    @action(methods=['put'], detail=True)
    def change_phone_mobile(self, request, *args, **kwargs):
        instance = self.get_object()
        new_phone_mobile = request.data.get('new_phone_mobile')
        password = request.data.get('password')

        if not new_phone_mobile:
            raise exceptions.ValidationError({
                'new_phone_mobile': _('Please specify a new_phone_mobile field')
            })
        if not password:
            raise exceptions.ValidationError({
                'password': _('Please specify a password field')
            })
        if not instance.user.check_password(password):
            raise exceptions.ValidationError({
                'password': _('Password invalid')
            })
        if models.Contact.objects.filter(phone_mobile=new_phone_mobile).exists():
            raise exceptions.ValidationError({
                'phone_mobile': _('User with this phone number already registered')
            })

        instance.phone_mobile_verified = False
        instance.new_phone_mobile = new_phone_mobile
        instance.save(update_fields=['phone_mobile_verified', 'new_phone_mobile'])

        # send verification email
        master_company = get_site_master_company()
        manager = master_company.primary_contact
        tasks.send_contact_verify_sms.apply_async(
                args=(instance.id, manager.id), kwargs=dict(new_phone_mobile=True))

        data = {
            'status': 'success',
            'message': _('An sms has been sent to your new mobile number. Please reply to it with "yes". You will receive notification to ols phone number until the new phone number is confirmed')
        }

        return Response(data)

    # @action(methods=['post'], detail=False, permission_classes=[AllowAny])
    # def register(self, request, *args, **kwargs):

    #     master_company = get_site_master_company(request=self.request)
    #     serializer = self.get_serializer(data=request.data)

    #     if serializer.is_valid(raise_exception=False):
    #         contact = serializer.save()
    #         http_status = status.HTTP_201_CREATED
    #     else:
    #         email = serializer.data.get('email')
    #         phone_mobile = serializer.data.get('phone_mobile')
    #         if email and phone_mobile and models.Contact.objects.filter(email=email,
    #                                                                     phone_mobile=phone_mobile,
    #                                                                     registration_completed=False) \
    #                                                             .exists():
    #                 contact = serializer.get_or_update()
    #                 if contact:
    #                     serializer = serializers.ContactSerializer(contact, many=False)
    #                     http_status = status.HTTP_200_OK
    #         else:
    #             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    #     models.ContactRelationship.objects.get_or_create(
    #         contact=contact,
    #         company=master_company
    #     )

    #     return Response(serializer.data, http_status)


class ContactAddressViewset(GoogleAddressMixin, BaseApiViewset):

    def prepare_related_data(self, data, is_create=False):
        data = super().prepare_related_data(data, is_create)

        if is_create and not data.get('is_active'):
            data['is_active'] = True
        return data

    def clear_active_contactaddresses(self, instance):
        """ if new address is active make all old adresses not active """
        if instance.is_active:
            for address in models.ContactAddress.objects.filter(contact=instance.contact) \
                                                        .exclude(pk=instance.pk):
                address.is_active=False
                address.save()

    def perform_create(self, serializer):
        instance = serializer.save()
        self.clear_active_contactaddresses(instance)

    def perform_update(self, serializer):
        instance = self.get_object()
        instance = serializer.save()
        self.clear_active_contactaddresses(instance)

    def perform_destroy(self, instance):
        instance = self.get_object()
        # prevent deleting the only address
        if models.ContactAddress.objects.filter(contact=instance.contact).count() == 1:
            raise exceptions.ValidationError({'non_field_errors': _("You cannot delete the only address")})
        # set another active address
        super().perform_destroy(instance)
        if instance.is_active:
            last_address = models.ContactAddress.objects.filter(contact=instance.contact).last()
            if last_address:
                last_address.is_active = True
                last_address.save()


class CompanyViewset(BaseApiViewset):

    http_method_names = ['post', 'put', 'get', 'delete', 'options']
    action_map = {
        'put': 'partial_update'
    }

    def process_response_data(self, data, queryset=None):
        if 'country' in self.request.GET or \
                'business_id' in self.request.GET:
            if isinstance(data, dict) and data.get('count') > 0:
                data.update({
                    'message': _('Company already exists')
                })
            elif isinstance(data, list) and len(data) > 0:
                data = {
                    'message': _('Company already exists'),
                    'results': data
                }
        return data

    def update(self, request, *args, **kwargs):
        data = self.prepare_related_data(request.data)
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        myob_name = data.pop('myob_name', None)
        if myob_name:
            master_company = get_site_master_company(request=self.request)
            MYOBSyncObject.objects.update_or_create(
                record=instance.pk, app='core', model='Company',
                company=master_company, defaults={
                    'legacy_confirmed': True,
                    'legacy_myob_card_number': myob_name
                }
            )
        # update industry relations
        industries_objects = data.pop('industries_objects', None)
        company = models.Company.objects.get(pk=kwargs['pk'])
        with transaction.atomic():
            models.CompanyIndustryRel.objects.filter(company=company).delete()
            if industries_objects:
                if len(industries_objects) < 2:
                    industries_objects[0]['default'] = True
                for industry in industries_objects:
                    industry_instance = Industry.objects.get(pk=industry['id'])
                    company_industry, _ = models.CompanyIndustryRel.objects.get_or_create(company=company,
                                                                                          industry=industry_instance)
                    company_industry.default = industry['default']
                    company_industry.save()
        # end update industry
        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}

        return Response(self.get_serializer(self.get_object()).data)

    def perform_update(self, serializer):
        instance = self.get_object()

        errors = []

        if instance.company_addresses.filter(active=True, primary_contact__isnull=True).exists():
            errors.append(_('All active addresses must have primary contact'))

        if errors:
            raise exceptions.ValidationError({'non_field_errors': errors})

        instance = serializer.save()

        if instance.type == models.Company.COMPANY_TYPES.master:
            return

        master_company = self.request.data.get('master_company')
        master_company = master_company.get('id') if isinstance(master_company, dict) else master_company
        manager_obj = self.request.data.get('manager')
        manager_id = manager_obj.get('id') if isinstance(manager_obj, dict) else manager_obj
        company_rel = instance.regular_companies.first()

        if master_company:
            master_company_obj = models.Company.objects.get(id=master_company)
            if manager_id:
                manager = models.CompanyContact.objects.get(id=manager_id)
            else:
                manager = None

            if not company_rel and instance.type != models.Company.COMPANY_TYPES.master:
                models.CompanyRel.objects.create(
                    master_company=master_company_obj,
                    regular_company=instance,
                    manager=manager
                )
            else:
                company_rel.master_company = master_company_obj
                company_rel.manager = manager
                company_rel.save()

    def create(self, request, *args, **kwargs):
        data = self.prepare_related_data(request.data)
        data = self.clean_request_data(data)

        invoice_rule_data = data.pop('invoice_rule', None)
        if invoice_rule_data:
            invoice_rule_data.pop('id')

            # check Invoice Rule fields for new Company
            invoice_rule_serializer = serializers.InvoiceRuleSerializer(data=invoice_rule_data)
            if not invoice_rule_serializer.is_valid():
                errors = invoice_rule_serializer.errors
                errors.pop('company', None)
                if errors:
                    raise exceptions.ValidationError(errors)

        # create Company
        kwargs['is_response'] = False
        instance_serializer = self.create_from_data(data, *args, **kwargs)

        if invoice_rule_data:
            # update Invoice Rule object
            invoice_rule_data['company'] = instance_serializer.instance.id
            invoice_rule_instance = instance_serializer.instance.invoice_rules.first()
            invoice_rule_serializer = serializers.InvoiceRuleSerializer(
                instance=invoice_rule_instance, data=invoice_rule_data, partial=True
            )
            invoice_rule_serializer.is_valid(raise_exception=True)
            invoice_rule_serializer.save()

        master_company = get_site_master_company(request=request, user=request.user).id
        manager = request.user.contact.company_contact.first()
        models.CompanyRel.objects.create(
            master_company_id=master_company,
            regular_company=instance_serializer.instance,
            manager=manager
        )

        headers = self.get_success_headers(instance_serializer.data)
        return Response(instance_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_destroy(self, instance):
        # TODO: The condition (or not relations_in_state) is temporarily eliminated
        #       because it doesn't make sense to me or Taavi
        #       why it tries to check the state's number values.
        # company_rels = instance.regular_companies.values_list('id', flat=True)
        # content_type = ContentType.objects.get_for_model(models.CompanyRel)
        # exclude_states = models.WorkflowObject.objects.filter(
        #     state__number__gt=10, state__workflow__model=content_type, active=True, object_id__in=company_rels
        # ).values_list('object_id', flat=True)
        # states = models.WorkflowObject.objects.filter(
        #     state__number__in=[10, 0], state__workflow__model=content_type, active=True, object_id__in=company_rels
        # ).exclude(
        #     object_id__in=set(exclude_states)
        # ).distinct('object_id').values_list('object_id', flat=True)

        # relations_in_state = states.count() == instance.regular_companies.count()

        # if instance.relationships.exists() or instance.jobsites_regular.exists() or not relations_in_state:

        if instance.relationships.filter(company_contact__contact__user__is_active=True).exists() \
                or instance.jobsites_regular.exists():
            raise ValidationError(_('Please delete the related company contacts and job sites first.'))

        instance.candidate_rels.delete()

        super().perform_destroy(instance)

    @action(methods=['get'], detail=False, permission_classes=[AllowAny])
    def exists(self, request, *args, **kwargs):
        company_name = request.GET.get('name')

        try:
            models.Company.objects.get(name__iexact=company_name)
            message = _('Company with this name alredy exists')
        except models.Company.DoesNotExist:
            message = ''

        if message:
            raise exceptions.ValidationError({
                'valid': False,
                'message': message
            })

        return Response({
            'status': 'success'
        })

    @action(methods=['get'], detail=False,)
    def guide(self, request, *args, **kwargs):
        company = self.request.user.company
        clients = company.__class__.objects.owned_by(company.get_master_company()[0]).exclude(id=company.id)

        return Response({
            'purpose': company.purpose,
            'has_industry': bool(company.industries.all()),
            'has_company_address': company.company_addresses.filter(active=True).exists(),
            'has_jobsite': bool(company.jobsites.all()),
            'has_company_contact': bool(models.CompanyContact.objects.owned_by(company.get_master_company()[0])),
            'has_client': bool(clients),
            'has_candidate': bool(company.candidate_rels.all()),
            'myob_connected': bool(company.myob_settings.timesheet_company_file),
            'has_skills': bool(company.skills.all())
        })

    @action(methods=['put'], detail=True)
    def change_purpose(self, request, pk, *args, **kwargs):

        company = get_object_or_404(models.Company, pk=pk)

        serializer = serializers.CompanyPurposeSerializer(instance=company, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            'status': 'success',
            'message': _('Company purpose changed')
        }, status=status.HTTP_200_OK)


    @action(methods=['post'], detail=True)
    def transfer_to_master_company(self, request, pk, *args, **kwargs):

        company = get_object_or_404(models.Company, pk=pk)

        # check if company_contact is primary contact
        if self.request.user != company.primary_contact.contact.user:
            raise exceptions.PermissionDenied

        # create domain if serializer valid
        serializer = serializers.CompanyDomainSerializer(instance=company, data=request.data)
        serializer.is_valid(raise_exception=True)
        website = serializer.validated_data['website']
        domain = '{}.{}'.format(website.lower(), settings.REDIRECT_DOMAIN)
        site, __ = Site.objects.get_or_create(domain=domain, defaults={'name': domain})
        models.SiteCompany.objects.get_or_create(company=company, site=site)

        # change company properties
        company.type = models.Company.COMPANY_TYPES.master
        company.save()

        # change user role
        user_role = self.request.user.role.filter(company_contact_rel__company=company).last()
        user_role.name = models.Role.ROLE_NAMES.manager
        user_role.save()

        # create CompanyWorkflowNodes
        bulk_objects = [
            models.CompanyWorkflowNode(company=company, workflow_node=wf_node)
            for wf_node in models.WorkflowNode.objects.filter(hardlock=True)
        ]
        models.CompanyWorkflowNode.objects.bulk_create(bulk_objects)
        company.create_state(10)
        models.CompanyRel.objects.get_or_create(master_company=company, regular_company=company)

        # add default company language
        models.CompanyLanguage.objects.get_or_create(
            company_id=company.id,
            language_id=settings.DEFAULT_LANGUAGE,
            default=True
            )

        # create registration form
        form, __ = models.Form.objects.get_or_create(
            company=company,
            builder=models.FormBuilder.objects.get(
                content_type=ContentType.objects.get_by_natural_key('candidate', 'candidatecontact')
            ),
            defaults=dict(is_active=True)
        )

        # create form languages
        models.FormLanguage.objects.get_or_create(
            form=form,
            title='Application Form',
            short_description='New application form',
            result_messages="You've been registered!"
        )
        return Response({
            'status': 'success',
            'message': _('Company transferred to master company')
            }, status=status.HTTP_200_OK)


class CompanyContactViewset(BaseApiViewset):

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(contact__user__is_active=True)

    def get_serializer_context(self):
        context = super(CompanyContactViewset, self).get_serializer_context()
        user = context['request'].user
        if user and user.is_authenticated:
            context['approved_by_staff'] = self.is_approved_by_staff(user)
            context['approved_by_primary_contact'] = self.is_approved_by_manager(user)
        return context

    def is_approved_by_staff(self, user):
        return models.CompanyContactRelationship.objects.filter(
            company__type=models.Company.COMPANY_TYPES.master,
            company_contact__contact__user=user
        ).exists()

    def is_approved_by_manager(self, user):
        return models.CompanyRel.objects.filter(manager__contact__user=user).exists()

    def get_object(self):
        obj = super().get_object()

        rel = obj.relationships.first()

        if rel:
            obj.active = rel.active
            obj.termination_date = rel.termination_date

        return obj

    def perform_destroy(self, instance):
        with transaction.atomic():
            has_jobsites = instance.managed_jobsites.exists() or instance.jobsites.exists()
            has_jobs = (
                instance.provider_representative_jobs.exists() or instance.customer_representative_jobs.exists()
            )

            if has_jobs:
                raise ValidationError({
                    'non_field_errors': _('There are jobs related to this client contact.')
                })
            elif has_jobsites:
                raise ValidationError({
                    'non_field_errors': _('There are jobsites related to this client contact.')
                })
            elif instance.supervised_time_sheets.exists():
                raise ValidationError({
                    'non_field_errors': _('There are timesheets related to this client contact.')
                })

            relationships = instance.relationships.all()
            for relationship in relationships:
                roles = relationship.user_roles.all()
                for role in roles:
                    instance.contact.user.role.remove(role)

                    # Delete Role object related to CompanyContactRelationship model
                    # once it's detached from user_role table
                    role.delete()

                # CompanyContactRelationship record should be deleted manually
                # because it's related to CompanyContact model by on_delete=SET_NULL
                # Not necessarily required actually :)
                relationship.delete()

            # Delete the instance finally which deletes UserDashboardModule objects
            instance.delete()

            # mark user as inactive
            # instance.contact.user.is_active = False
            # instance.contact.user.save()

    def prepare_related_data(self, data, is_create=False):
        if is_create and not data.get('contact'):
            data['contact'] = fields.empty

        return self._prepare_internal_data(data, is_create=is_create)

    def perform_create(self, serializer):
        instance = serializer.save()

        manager = self.request.user.contact
        master_company = get_site_master_company(request=self.request)

        if not instance.contact.phone_mobile_verified:
            tasks.send_contact_verify_sms.apply_async(args=(instance.contact.id, manager.id))

        if not instance.contact.email_verified:
            tasks.send_contact_verify_email.apply_async(
                args=(instance.contact.id, manager.id, master_company.id))

    @action(methods=['post'], detail=False)
    def register(self, request, *args, **kwargs):
        serializer = serializers.CompanyContactRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()

        phone_number = instance.contact.phone_mobile
        if phone_number:
            login_service = factory.get_instance('login')
            login_service.send_login_sms(instance.contact,
                                         '/#/registration/password')

        serializer = serializers.CompanyContactSerializer(instance)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data,
                        status=status.HTTP_201_CREATED,
                        headers=headers)

    @action(methods=['post'], detail=False)
    def sendsms(self, request, *args, **kwargs):
        id_list = request.data

        if not id_list or not isinstance(id_list, list):
            raise exceptions.ParseError(_('You should select Company addresses'))

        phone_numbers = models.CompanyContact.objects.filter(
            id__in=id_list, contact__phone_mobile__isnull=False
        ).values_list(
            'contact__phone_mobile', flat=True
        ).distinct()

        return Response({
            'status': 'success',
            'phone_number': phone_numbers,
            'message': _('Phones numbers was selected'),
        })

    @action(methods=['put'], detail=True)
    def change_username(self, request, *args, **kwargs):
        data = self.prepare_related_data(request.data)
        contact = data.get('contact', {})
        instance = self.get_object()
        new_email = contact.get('email', None)
        new_phone_mobile = contact.get('phone_mobile', None)

        if new_email is None or new_phone_mobile is None:
            raise exceptions.ValidationError({'email': _('Email must be given.')})

        if new_email != instance.contact.email:
            if Contact.objects.filter(email=new_email).exists():
                raise exceptions.ValidationError({
                    'email': _('User with this email address already registered')
                })

            instance.contact.email = new_email
            instance.contact.save(update_fields=['email'])

        if new_phone_mobile != instance.contact.phone_mobile:
            if Contact.objects.filter(phone_mobile=new_phone_mobile).exists():
                raise exceptions.ValidationError({
                    'phone_mobile': _('User with this phone number already registered')
                })

            instance.contact.phone_mobile = new_phone_mobile
            instance.contact.save(update_fields=['phone_mobile'])

        data = {
            'status': 'status',
            'message': _('Email and/or mobile phone has successfully been updated.')
        }

        return Response(data)


class SiteViewset(BaseApiViewset):

    permission_classes = (permissions.SitePermissions,)
    filter_backends = (permissions.SiteClosestCompanyFilterBackend,)

    @action(methods=['get'], detail=False, permission_classes=[AllowAny])
    def exists(self, request, *args, **kwargs):
        website = request.GET.get('website', '').lower()

        try:
            Site.objects.get(domain__iexact='{}.{}'.format(website, settings.REDIRECT_DOMAIN))
            message = _('Website with this domain alredy exists')
        except Site.DoesNotExist:
            message = _('Website with this domain is not available') if website == 'api' else ''

        if message:
            raise exceptions.ValidationError({
                'valid': False,
                'message': message
            })

        return Response({
            'status': 'success'
        })


class NavigationViewset(BaseApiViewset):

    def get_queryset(self):
        role_id = self.request.query_params.get('role', None)

        try:
            role = models.Role.objects.get(id=role_id)
            access_level = role.name
        except Exception:
            access_level = self.request.user.access_level

        access_qry = Q(access_level=access_level)

        if self.request.user.is_superuser:
            access_qry |= Q(access_level=models.ExtranetNavigation.ADMIN)

        return models.ExtranetNavigation.objects.filter(access_qry, parent=None)


class CompanyAddressViewset(GoogleAddressMixin, BaseApiViewset):

    phone_fields = ['phone_landline', 'phone_fax']

    def prepare_related_data(self, data, is_create=False):
        data = super().prepare_related_data(data, is_create)

        if is_create and not data.get('active'):
            data['active'] = True

        if not data.get('primary_contact'):
            raise exceptions.ValidationError({'primary_contact': _('Primary contact must be set')})

        return data

    def perform_destroy(self, instance):
        if models.CompanyAddress.objects.filter(company=instance.company).count() == 1:
            company_rel = instance.company.regular_companies.last()
            is_active_state = company_rel.get_active_states().filter(state__number=70).exists()
            if company_rel and company_rel.is_allowed(80) and is_active_state:
                company_rel.create_state(80, _('Company has no active address!'))

        super().perform_destroy(instance)

    @action(methods=['post'], detail=False)
    def delete(self, request, *args, **kwargs):
        ids = request.data

        if not ids:
            raise exceptions.ParseError(_('Objects not selected'))

        return Response({
            'status': 'success',
            'message': _('Deleted successfully'),
        })

    @action(methods=['post'], detail=False)
    def sendsms(self, request, *args, **kwargs):
        id_list = request.data

        if not id_list or not isinstance(id_list, list):
            raise exceptions.ParseError(_('You should select Company addresses'))

        phone_numbers = set(models.CompanyAddress.objects.filter(
            id__in=id_list, primary_contact__contact__phone_mobile__isnull=False).values_list(
            'primary_contact__contact__phone_mobile', flat=True))

        return Response({
            'status': 'success',
            'phone_number': phone_numbers,
            'message': _('Phones numbers was selected'),
        })


class AppsList(ViewSet):

    def list(self, request, format=None, **kwargs):
        """
        Return a list of applications
        """
        return Response([app.replace('r3sourcer.apps.', '') for app in settings.INSTALLED_APPS])


class ModelsList(ViewSet):

    def list(self, request, format=None, *args, **kwargs):
        """
        Return a list of all models by application name.
        """
        app_name = request.query_params.get("app_name", None)
        if app_name:
            models = [model._meta.model_name
                      for model in apps.get_app_config(app_name).get_models()]
            return Response(models)
        return Response(status=status.HTTP_400_BAD_REQUEST)


class FunctionsList(ViewSet):

    def list(self, request, format=None, *args, **kwargs):
        """
        Return a list of functions available for workflow by app_name
        and model_name
        """
        app_name = request.query_params.get("app_name", None)
        model_name = request.query_params.get("model_name", None)

        if app_name and model_name:
            try:
                model = get_model(app_name, model_name)
            except LookupError:
                return Response(status=status.HTTP_400_BAD_REQUEST)
            else:
                functions = get_model_workflow_functions(model)
                return Response(functions)
        return Response(status=status.HTTP_400_BAD_REQUEST)


class WorkflowNodeViewset(BaseApiViewset):

    def _get_target(self, model_name, object_id):
        try:
            model_class = apps.get_model(model_name)
            target_object = model_class.objects.get(id=object_id)
        except ObjectDoesNotExist:
            raise exceptions.NotFound(_('Object does not exists'))

        required_mixins = (WorkflowProcess, mixins.CompanyLookupMixin)
        if not isinstance(target_object, required_mixins):
            raise exceptions.NotFound(_('Object does not have workflow'))

        return target_object

    @action(methods=['get'], detail=False)
    def timeline(self, request, *args, **kwargs):
        model = request.query_params.get('model')
        object_id = request.query_params.get('object_id')
        company = request.query_params.get('company')

        if not model or not object_id:
            raise exceptions.NotFound(_('Workflow Nodes not found'))

        target_object = self._get_target(model, object_id)

        try:
            company = models.Company.objects.get(id=company)
        except models.Company.DoesNotExist:
            company = target_object.get_closest_company()

        try:
            model_ct = ContentType.objects.get_by_natural_key(
                *model.split('.')
            )
            workflow = models.Workflow.objects.get(model=model_ct)
        except (IndexError, models.Workflow.DoesNotExist):
            workflow = None

        if workflow is None:
            raise exceptions.NotFound(_('Workflow not found for model'))

        nodes = models.WorkflowNode.get_company_nodes(company, workflow).filter(parent__isnull=True)

        serializer = serializers.WorkflowTimelineSerializer(
            nodes, target=target_object, many=True
        )

        return Response(serializer.data, status=status.HTTP_200_OK)


class CompanyWorkflowNodeViewset(BaseApiViewset):

    def perform_create(self, serializer):
        company_node = models.CompanyWorkflowNode.objects.filter(
            company=serializer.validated_data['company'],
            workflow_node=serializer.validated_data['workflow_node']
        ).first()

        if company_node is not None:
            company_node.active = True
            company_node.order = serializer.data.get('order')
            company_node.save()
        else:
            serializer.save()

    def perform_destroy(self, instance):
        instance.active = False
        instance.save()


class UserDashboardModuleViewSet(BaseApiViewset):

    CAN_NOT_CREATE_MODULE_ERROR = _("You should be CompanyContact to creating module")
    MODULE_ALREADY_EXISTS = _("Module already exists")
    filter_backends = [DjangoFilterBackend]

    def get_queryset(self):
        if self.request.user.is_authenticated:
            site_master_company = get_site_master_company(request=self.request)
            dm = models.UserDashboardModule.objects.filter(
                company_contact__contact__user_id=self.request.user.id
            )
            if self.request.user.is_superuser:
                return dm
            else:
                return dm.owned_by(site_master_company)

        return models.DashboardModule.objects.none()

    def perform_create(self, serializer):
        qs = models.UserDashboardModule.objects.filter(
                company_contact__contact__user=self.request.user.id,
                dashboard_module=serializer.validated_data['dashboard_module'])
        if qs.exists():
            raise exceptions.ValidationError(self.MODULE_ALREADY_EXISTS)

        user = self.request.user
        company_contact = user.contact.company_contact.last()
        if company_contact is None:
            raise exceptions.APIException(self.CAN_NOT_CREATE_MODULE_ERROR)

        if user.is_manager() is False:
            raise exceptions.PermissionDenied
        serializer.save(company_contact=company_contact)


class DashboardModuleViewSet(BaseApiViewset):

    def create(self, request, *args, **kwargs):
        if not request.user.has_perm('core.add_dashboardmodule'):
            raise exceptions.PermissionDenied
        return super(DashboardModuleViewSet, self).create(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not request.user.has_perm('core.delete_dashboardmodule'):
            raise exceptions.PermissionDenied
        return super(DashboardModuleViewSet, self).destroy(request, *args, **kwargs)

    def get_queryset(self):
        if self.request.user.is_manager():
            queryset = super(DashboardModuleViewSet, self).get_queryset().prefetch_related('content_type')
        else:
            queryset = DashboardModule.objects.none()

        return queryset


class FormBuilderViewSet(BaseApiViewset):

    permission_classes = (permissions.ReadonlyOrIsSuperUser,)
    serializer_class = serializers.FormBuilderSerializer


class ContentTypeViewSet(BaseApiViewset):

    permission_classes = (permissions.ReadOnly,)


class FormViewSet(BaseApiViewset):

    serializer_class = serializers.FormSerializer
    permission_classes = (IsAuthenticated,)

    def update(self, request, *args, **kwargs):
        data = self.prepare_related_data(request.data)
        partial = kwargs.pop('partial', False)
        form_obj = self.get_object()
        # update translations
        translation_objects = data.pop('translations', None)
        form = models.Form.objects.get(pk=kwargs['pk'])
        with transaction.atomic():
            models.FormLanguage.objects.filter(form=form).delete()
            for translation in translation_objects:
                language_id = translation['language'] if isinstance(translation['language'], str) else translation['language']['id']
                language = models.Language.objects.get(alpha_2=language_id)
                models.FormLanguage.objects.create(form=form,
                                                   language=language,
                                                   title=translation['title'],
                                                   short_description=translation['short_description'],
                                                   button_text=translation['button_text'],
                                                   result_messages=translation['result_messages']
                                                   )
        # end update translations
        serializer = self.get_serializer(form_obj, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(form_obj, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        data = self.prepare_related_data(request.data)

        companies = get_master_companies_by_contact(self.request.user.contact)
        if len(companies) > 0:
            data['company'] = companies[0].id
        else:
            data['company'] = get_default_company().id

        data = self.clean_request_data(data)

        return self.create_from_data(data, *args, **kwargs)

    @action(methods=['get'], detail=True, permission_classes=(AllowAny,))
    def render(self, request, pk, *args, **kwargs):
        fields = self.get_list_fields(request)
        instance = self.get_object()
        serializer = serializers.FormRenderSerializer(instance, fields=fields)

        return Response(serializer.data)

    @action(methods=['post'], detail=True, permission_classes=(AllowAny,))
    def submit(self, request, pk, *args, **kwargs):
        from r3sourcer.apps.acceptance_tests.models import WorkflowObjectAnswer, WorkflowObject
        from r3sourcer.apps.candidate.models import CandidateContact, Formality
        form_obj = self.get_object()
        extra_data = {}
        data = {}

        for key, val in request.data.items():
            if form_obj.builder.extra_fields.filter(name=key).exists():
                extra_data[key] = val
            else:
                data[key] = val

        try:
            data = models.Form.parse_api_data(data, form=form_obj)
            files = models.Form.parse_api_files(data)
        except ValidationError as e:
            raise exceptions.ValidationError({k.replace('__', '.'): v for k, v in e.message_dict.items()})

        form = form_obj.get_form_class()(data=data, files=files)

        if not form.is_valid():
            raise exceptions.ValidationError({k.replace('__', '.'): v for k, v in form.errors.items()})

        form_storage_data = models.Form.parse_data_to_storage(form.cleaned_data)
        form_storage_data, errors = form_obj.get_data(form_storage_data)
        if errors:
            raise exceptions.ValidationError(errors)

        form_storage_data = {k: v for k, v in form_storage_data.items() if v}

        storage_helper = StorageHelper(form_obj.content_type.model_class(), form_storage_data)
        storage_helper.process_fields()

        if not storage_helper.validate():
            raise exceptions.ValidationError(storage_helper.errors)

        instance = storage_helper.create_instance()
        candidate = CandidateContact.objects.get(id=instance.id)
        if candidate and data.get('tests'):
            for item in data.get('tests'):
                # TODO: The block below must be verified later. Only first three general questions, one tool question
                #       and two carpenter questions are only passed, while the other questions are ignored.
                if 'answer' in item:
                    # If the answer is either an empty string or an empty list, skip!
                    if not item['answer']:
                        continue

                    if isinstance(item['answer'], list):
                        answers = item['answer']
                    else:
                        answers = [item['answer']]

                elif 'answer_text' in item:
                    # If the answer_text is an emtpy string, skip.
                    if not item['answer_text'].strip():
                        continue

                question = AcceptanceTestQuestion.objects.get(id=item['acceptance_test_question'])
                workflow_object = WorkflowObject.objects.get(object_id=str(instance.id))
                if 'answer_text' in item:
                    WorkflowObjectAnswer.objects.create(workflow_object=workflow_object,
                                                        acceptance_test_question=question,
                                                        answer_text=item['answer_text'])
                else:
                    for ans_id in answers:
                        try:
                            uuid.UUID(ans_id)
                            answer = AcceptanceTestAnswer.objects.get(id=ans_id)
                            WorkflowObjectAnswer.objects.create(workflow_object=workflow_object,
                                                                acceptance_test_question=question,
                                                                answer=answer)
                        except ValueError:
                            raise exceptions.ValidationError({"Answer": _("Answer id is not an UUID value")})

        # create formality object
        personal_id = data.get('formalities__personal_id', None)
        tax_number = data.get('formalities__tax_number', None)
        if candidate and (personal_id or tax_number):
            Formality.objects.create(candidate_contact=candidate,
                                     country=candidate.contact.active_address.country,
                                     personal_id=personal_id,
                                     tax_number=tax_number)

        # create bank account
        if candidate:
            master_company = get_site_master_company()
            bank_account_layout = BankAccountLayout.objects.filter(
                countries__country=master_company.country
            ).order_by('-countries__default').first()

            if not bank_account_layout:
                raise exceptions.ValidationError({"country": _("Bank account layout doesn't exist for country {}".format(master_company.country))})

            with transaction.atomic():
                bank_account = ContactBankAccount(
                    contact=candidate.contact,
                    layout=bank_account_layout,
                )
                bank_account.save()
                for (key, value) in data.items():
                    if key.startswith("contact__bank_accounts"):
                        try:
                            field = BankAccountField.objects.get(name=key[key.rfind('__')+2:])
                        except BankAccountField.DoesNotExist:
                            raise exceptions.ValidationError({"{}".format(key): _("Field doesn't exist ")})
                        field_serializer = ContactBankAccountFieldSerializer(data={'field_id': field.id, 'value': value})
                        if field_serializer.is_valid(raise_exception=True):
                            field_serializer.create(dict(bank_account_id=str(bank_account.pk), **field_serializer.data))

        for extra_field in form_obj.builder.extra_fields.all():
            # check if field exists in extra_data
            if extra_field.name not in extra_data:
                continue

            target_model = extra_field.content_type.model_class()
            related_model = extra_field.related_through_content_type.model_class()
            values = extra_data[extra_field.name]

            # if value is single make list with one value
            if not isinstance(values, list):
                values = [values]

            for val in values:
                # TODO: remove next 2 lines after https://taavisaavo.atlassian.net/browse/RV-1237 will be fixed on FE
                if isinstance(val, str):
                    val = {"id": val}
                # prepare data
                for field in related_model._meta.get_fields():
                    if isinstance(field, FileField):
                        if field.name in val:
                           val[field.name] = ApiBase64FileField().to_internal_value(val[field.name])
                        continue
                    if not isinstance(field, ForeignKey):
                        continue
                    rel_model = field.rel.model if hasattr(field, 'rel') else field.remote_field.model
                    if isinstance(instance, rel_model):
                        val[field.name] = instance
                        continue
                    if isinstance(instance.recruitment_agent, rel_model):
                        val[field.name] = instance.recruitment_agent
                        continue

                # check if id field exists in dictionary
                if 'id' in val:
                    val_id = val.pop('id', None)

                    try:
                        val_obj = target_model.objects.get(id=val_id)
                        obj_values = {
                            extra_field.name: val_obj,
                            **val,
                        }
                        related_model.objects.create(**obj_values)

                    except ObjectDoesNotExist:
                        continue

        # TODO: form instance might not have any translations, which would lead to results_messages error
        return Response({'message': form_obj.submit_message,
                         'candidate_contact': instance.id},
                        status=status.HTTP_201_CREATED)


class CitiesLightViewSet(BaseApiViewset):

    permission_classes = (AllowAny,)

    def get_queryset(self):
        qs = super().get_queryset()

        return qs.order_by('name')


class AddressViewset(GoogleAddressMixin, BaseApiViewset):
    root_address = True

    @action(methods=['post'], detail=False, permission_classes=(AllowAny,))
    def parse(self, request, *args, **kwargs):
        address_data = request.data
        data = parse_google_address(address_data)
        return Response(data)


class CompanyContactRelationshipViewset(BaseApiViewset):

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(company_contact__contact__user__is_active=True)

    def perform_destroy(self, instance):
        with transaction.atomic():
            company_contact = instance.company_contact
            has_jobsites = company_contact.managed_jobsites.exists() or company_contact.jobsites.exists()
            has_jobs = (
                company_contact.provider_representative_jobs.exists() or
                company_contact.customer_representative_jobs.exists()
            )

            if has_jobs or has_jobsites or company_contact.supervised_time_sheets.exists():
                raise ValidationError({
                    'non_field_errors': _('This contact has some related jobs, jobsites or timesheets.')
                })
            # Roles will be deleted according to on_delete=CASCADE
            # models.Role.objects.filter(company_contact_rel=instance).delete()

            # mark user as inactive
            # instance.company_contact.contact.user.is_active = False
            # instance.company_contact.contact.user.save()

            super().perform_destroy(instance)


class TagViewSet(BaseApiViewset):

    permission_classes_by_action = {'create': [AllowAny],
                                    'all': [AllowAny],
                                    'update': [IsAuthenticated]}

    def get_permissions(self):
        try:
            # return permission_classes depending on `action`
            return [permission() for permission in self.permission_classes_by_action[self.action]]
        except KeyError:
            # action is not set return default permission_classes
            return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.kwargs.get('pk'):
            master_company = self.request.user.contact.get_closest_company().get_closest_master_company()
            qs = qs.filter(Q(company_tags__company_id=master_company.pk) | Q(owner=models.Tag.TAG_OWNER.system))
        return qs

    @action(methods=['get'], detail=False)
    def all(self, request, *args, **kwargs):
        """
        Public view that get company from subdomain and return company and system tags
        """
        master_company = get_site_master_company(request=self.request)
        queryset = models.Tag.objects.filter(Q(company_tags__company_id=master_company.pk) |
                                                Q(owner=models.Tag.TAG_OWNER.system))
        return self._paginate(request, self.get_serializer_class(), queryset=queryset)

    def update(self, request, *args, **kwargs):
        data = self.prepare_related_data(request.data)
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        if instance.owner == models.Tag.TAG_OWNER.system \
                or not instance.company_tags.all():
            return HttpResponseBadRequest('Forbidden action - edit')
        if data.get('owner') and data['owner'] == models.Tag.TAG_OWNER.system:
            return HttpResponseBadRequest('Field <owner> cannot be {0}'.format(data['owner']))

        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        master_company = get_site_master_company(request=self.request)
        with transaction.atomic():
            data = self.prepare_related_data(request.data)
            serializer = self.get_serializer(data=data)
            serializer.initial_data['owner'] = models.Tag.TAG_OWNER.company
            serializer.is_valid(raise_exception=True)
            if self.queryset.filter(owner=models.Tag.TAG_OWNER.system,
                                    name__iexact=serializer.validated_data['name']).all():
                return HttpResponseBadRequest('Tag already exists {0}'.format(serializer.validated_data["name"]))

            if self.queryset.filter(owner=models.Tag.TAG_OWNER.company,
                                    name__iexact=serializer.validated_data['name'],
                                    company_tags__company_id=master_company.pk,
                                    ).all():
                return HttpResponseBadRequest('Tag already exists {0}'.format(serializer.validated_data["name"]))

            self.perform_create(serializer)
            company_tag = models.CompanyTag(
                tag_id=serializer.data['id'],
                company_id=master_company.pk,
            )
            company_tag.save()
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class PublicHolidayViewset(BaseApiViewset):

    def get_queryset(self):
        qs = super().get_queryset()
        master_company = get_site_master_company(request=self.request)
        return qs.filter(country=master_company.country)
