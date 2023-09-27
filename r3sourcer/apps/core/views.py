import json

from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.module_loading import import_string
from django.utils.translation import ugettext_lazy as _
from django.views import generic
from oauth2_provider_jwt.utils import generate_payload, encode_jwt
from oauth2_provider_jwt.views import TokenView, MissingIdAttribute
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import APIView

from r3sourcer.apps.candidate.models import CandidateContact
from r3sourcer.apps.core.models import Form, Company, Invoice, Role, User, CompanyContact, Contact
from r3sourcer.apps.core.utils.companies import get_site_master_company, get_site_url
from r3sourcer.apps.core.utils.utils import is_valid_email, is_valid_phone_number
from r3sourcer.apps.myob.models import MYOBSyncObject
from r3sourcer.apps.myob.tasks import sync_invoice


class OAuth2JWTTokenMixin():
    def _get_access_token_jwt(self, request, content, domain=None, username=None):
        from r3sourcer.apps.login.api.serializers import TokenPayloadSerializer

        extra_data = {}
        issuer = settings.JWT_ISSUER
        payload_enricher = getattr(settings, 'JWT_PAYLOAD_ENRICHER', None)
        if payload_enricher:
            fn = import_string(payload_enricher)
            extra_data = fn(request)

        if 'scope' in content:
            extra_data['scope'] = content['scope']

        if not username:
            try:
                username = json.loads(request.body.decode('utf-8'))['username']
            except Exception:
                username = request.data.get('username') if hasattr(request, 'data') else request.POST.get('username')

        if username:
            if is_valid_email(username) is True:
                contact_qs = Contact.objects.filter(email=username)
            elif is_valid_phone_number(username, country_code=None) is True:
                if not username.startswith('+'):
                    username = '+{}'.format(username)
                contact_qs = Contact.objects.filter(phone_mobile=username)
            else:
                raise ValueError('Invalid username')
            try:
                contact = contact_qs.first()
                extra_data['user_id'] = str(contact.user.id)
            except Exception:
                raise MissingIdAttribute

            if not domain:
                master_company = contact.get_closest_company()
                domain = get_site_url(master_company=master_company)

            extra_data['origin'] = domain
            extra_data['contact'] = TokenPayloadSerializer(contact).data,

        payload = generate_payload(issuer, content['expires_in'], **extra_data)
        token = encode_jwt(payload)
        return token


class FormView(generic.TemplateView):

    template_name = 'form_builder.html'

    def get_context_data(self, **kwargs):
        context = super(FormView, self).get_context_data(**kwargs)
        context['company'] = get_object_or_404(Company, pk=self.kwargs['company'])
        context['company_id'] = str(context['company'].pk)
        if Form.objects.filter(pk=self.kwargs['pk'], company=context['company']).exists():
            company = context['company']
        elif Form.objects.filter(pk=self.kwargs['pk'], company=None).exists():
            company = None
        else:
            raise Http404
        context['form'] = get_object_or_404(Form, pk=self.kwargs['pk'], company=company)
        return context


class RegisterFormView(generic.TemplateView):

    template_name = 'form_builder.html'

    def get_context_data(self, **kwargs):
        context = super(RegisterFormView, self).get_context_data(**kwargs)
        context['company'] = get_site_master_company(request=self.request)
        context['company_id'] = str(context['company'].pk)

        form = Form.objects.filter(company=context['company'], is_active=True).first()
        if not form:
            form = Form.objects.filter(company=None, is_active=True).first()
            if not form:
                raise Http404

        context['form'] = form
        return context


class ApproveInvoiceView(APIView):
    def post(self, request, *args, **kwargs):
        from r3sourcer.apps.hr.tasks import send_invoice_email
        invoice = get_object_or_404(Invoice, id=self.kwargs['id'])

        if not invoice.customer_company.billing_email:
            raise exceptions.ValidationError(_('Please set billing email address for company'))

        invoice.approved = True
        invoice.provider_representative = request.user.contact.get_company_contact_by_company(
            invoice.provider_company)
        invoice.save()
        sync_invoice.delay(invoice.id)
        send_invoice_email.delay(invoice.id)
        return Response()


class SyncInvoiceView(APIView):
    def post(self, request, *args, **kwargs):
        invoice = get_object_or_404(Invoice, id=self.kwargs['id'])
        if invoice.approved is False:
            return Response({"error": "Invoice is not approved"})

        sync_invoice.delay(invoice.id)
        return Response({"status": "success"})


class SyncInvoicesView(APIView):
    """
    Fetches unsynced invoices and triggers delayed task to sync them to MYOB
    """
    def get(self, *args, **kwargs):
        synced_objects = MYOBSyncObject.objects.filter(app='core',
                                                       model='Invoice',
                                                       direction='myob') \
                                               .values_list('record', flat=True)
        invoice_list = Invoice.objects.exclude(id__in=synced_objects)

        for invoice in invoice_list:
            sync_invoice.delay(invoice.id)


class UserRolesView(APIView):
    """
    Returns list of user's roles
    """
    def get(self, *args, **kwargs):
        if self.request.user.is_anonymous:
            data = {}
        else:
            roles = []
            for role in self.request.user.role.all().order_by('name'):
                site_company = None
                if role.company_contact_rel:
                    site_company = role.company_contact_rel.company.get_closest_master_company().site_companies.last()

                roles.append(
                    {
                        'id': role.id,
                        'job_title': role.company_contact_rel.company_contact.job_title if role.company_contact_rel else role.name,
                        'domain': site_company.site.domain if site_company else '',
                        '__str__': '{} - {}'.format(
                            role.name, role.company_contact_rel.company.name
                        ) if role.company_contact_rel else '{} - '.format(role.name)
                    }
                )

            data = {
                'roles': roles
            }
        return Response(data)


class SetRolesView(APIView):
    """
    Sets roles to users
    """
    def post(self, *args, **kwargs):
        roles = list()
        user = get_object_or_404(User, id=kwargs['id'])

        if 'manager' in self.request.POST['roles']:
            roles.append(Role.objects.get(name='manager'))

            if not hasattr(user.contact, 'company_contact'):
                CompanyContact.objects.create(contact=user.contact)

        if 'client' in self.request.POST['roles']:
            roles.append(Role.objects.get(name='client'))

            if not hasattr(user.contact, 'company_contact'):
                CompanyContact.objects.create(contact=user.contact)

        if 'candidate' in self.request.POST['roles']:
            roles.append(Role.objects.get(name='candidate'))

            if not hasattr(user.contact, 'candidate_contacts'):
                CandidateContact.objects.create(contact=user.contact)

        user.role.add(*roles)
        return Response()


class RevokeRolesView(APIView):
    """
    Revokes user roles
    """
    def post(self, *args, **kwargs):
        roles = list()
        user = get_object_or_404(User, id=kwargs['id'])

        if 'manager' in self.request.POST['roles']:
            roles.append(Role.objects.get(name='manager'))

        if 'client' in self.request.POST['roles']:
            roles.append(Role.objects.get(name='client'))

        if 'candidate' in self.request.POST['roles']:
            roles.append(Role.objects.get(name='candidate'))

        user.role.remove(*roles)
        return Response()


class OAuthJWTToken(OAuth2JWTTokenMixin, TokenView):
    pass


class UserTimezone(APIView):
    """
    Get user timezone
    """
    def post(self, *args, **kwargs):
        self.request.session['user_timezone'] = self.request.data.get('user_timezone')
        company = self.request.user.company
        if company:
            company.company_timezone = self.request.data.get('user_timezone')
            company.save()
        return Response()
