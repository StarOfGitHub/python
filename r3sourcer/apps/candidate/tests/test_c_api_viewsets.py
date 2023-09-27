import datetime
import json

import mock
import pytest
from unittest.mock import patch

from django.urls import reverse
from django.contrib.sites.models import Site
from django.utils import timezone

from rest_framework.test import force_authenticate

from r3sourcer.apps.candidate.endpoints import (
    CandidateContactEndpoint, SubcontractorEndpoint
)
from r3sourcer.apps.candidate.models import CandidateContact, Subcontractor, CandidateRel
from r3sourcer.apps.candidate.tests.utils import BaseTestCase, AnonymousUser
from r3sourcer.apps.core import models as core_models
from r3sourcer.apps.hr import models as hr_models
from r3sourcer.apps.pricing.models import Industry
from r3sourcer.apps.skills.models import Skill, SkillName


def load_data():
    # Load fixtures
    from django.core.management import call_command
    call_command("loaddata", "test_data")


class CandidateContactEndpointTest(CandidateContactEndpoint):

    permission_classes = []


class ResourceMixin:
    endpoint_class = None
    actions = {
        'get': 'retrieve',
        'put': 'update',
        'post': 'create',
        'delete': 'destroy',
    }

    def get_response_as_view(self, request, endpoint=None, actions=None):
        kwargs = {
            'request': request,
            'partial': request.method.lower() == 'put'
        }
        endpoint = endpoint or self.endpoint_class
        viewset = endpoint().get_viewset()
        view = viewset.as_view(actions or self.actions)
        response = view(**kwargs)
        response.render()
        return response


@pytest.mark.django_db
class TestCompanyContactResource(ResourceMixin):
    endpoint_class = CandidateContactEndpointTest
    actions = {
        'post': 'create',
    }

    @mock.patch('r3sourcer.apps.core.models.core.fetch_geo_coord_by_address', return_value=(42, 42))
    def test_can_register_candidate_contact(
        self, mock_geo, rf, user, staff_relationship, candidate_contact_data, site_company
    ):
        req = rf.post(
            '/candidate_contacts/register/', data=json.dumps(candidate_contact_data),
            content_type='application/json'
        )
        force_authenticate(req, user=user)

        response = self.get_response_as_view(req, actions={'post': 'register'})

        assert 201 == response.status_code
        assert 'id' in response.data
        assert CandidateContact.objects.filter(id=response.data['id']).exists()

    @mock.patch('r3sourcer.apps.core.models.core.fetch_geo_coord_by_address',
                return_value=(42, 42))
    def test_can_register_candidate_contact_do_not_agree(
            self, mock_geo, rf, user, candidate_contact_data):
        candidate_contact_data['agree'] = False
        req = rf.post('/candidate_contacts/register/',
                      data=json.dumps(candidate_contact_data),
                      content_type='application/json')
        force_authenticate(req, user=user)

        response = self.get_response_as_view(req, actions={'post': 'register'})

        assert response.data['status'] == 'error'


@pytest.mark.django_db
class TestSubcontractorResource(ResourceMixin):
    endpoint_class = SubcontractorEndpoint
    actions = {
        'post': 'create',
    }

    @mock.patch('r3sourcer.apps.core.models.core.fetch_geo_coord_by_address',
                return_value=(42, 42))
    def test_can_register_subcontractor(self, mock_geo, rf, user, candidate_contact_data):
        req = rf.post('/candidate_contacts/register/',
                      data=json.dumps(candidate_contact_data),
                      content_type='application/json')
        force_authenticate(req, user=user)

        response = self.get_response_as_view(req, actions={'post': 'register'})

        assert 'id' in response.data
        assert 201 == response.status_code
        assert Subcontractor.objects.filter(id=response.data['id']).exists()

    @mock.patch('r3sourcer.apps.core.models.core.fetch_geo_coord_by_address',
                return_value=(42, 42))
    def test_can_register_subcontractor_do_not_agree(self, mock_geo, rf, user, candidate_contact_data):
        candidate_contact_data['agree'] = False
        req = rf.post('/candidate_contacts/register/',
                      data=json.dumps(candidate_contact_data),
                      content_type='application/json')
        force_authenticate(req, user=user)

        response = self.get_response_as_view(req, actions={'post': 'register'})

        assert response.data['status'] == 'error'

from django.contrib.contenttypes.models import ContentType

def workflow_state(candidate_id, company):
    content_type = ContentType.objects.get_for_model(CandidateContact)
    workflow, created = core_models.Workflow.objects.get_or_create(name="test_workflow", model=content_type)
    wf_node = core_models.WorkflowNode.objects.create(
        number=11, name_before_activation="State 11", workflow=workflow, rules={}, name_after_activation='Recruited - Available for Hire',
    )
    core_models.CompanyWorkflowNode.objects.get_or_create(company=company, workflow_node=wf_node)
    wf_obj = core_models.WorkflowObject.objects.create(
        object_id=candidate_id, state=wf_node)

    return wf_obj


class TestPoolAPITestCase(BaseTestCase):
    def get_url(self, view_name=None, args=None, kwargs=None):
        return '/candidate/candidatecontacts/pool/'

    def get_allowed_users(self):
        if self.request_user is not None:
            return [self.request_user]
        return [core_models.User.objects.create_superuser(
            email='test@test.tt', phone_mobile='+32345678901',
            password='test1234',
            )]

    def get_data(self):
        user = core_models.User.objects.create_user(
            email='test@test.vt', phone_mobile='+12345678801',
            password='test1234'
            )
        company = core_models.Company.objects.create(
            name='Company',
            business_id='123',
            type=core_models.Company.COMPANY_TYPES.master,
            )
        test_candidate = CandidateContact.objects.create(
            contact=user.contact, profile_price=13.0
            )
        company_contact = core_models.CompanyContact.objects.create(
            contact=user.contact
            )
        candidate_rel = CandidateRel.objects.create(
            candidate_contact=test_candidate,
            master_company=company,
            company_contact=company_contact,
            owner=True,
            active=True
            )
        workflow_state(candidate_id=str(test_candidate.id), company=company)
        return {'user': user, 'company': company, 'test_candidate': test_candidate,
                'company_contact': company_contact, 'candidate_rel': candidate_rel}

    def setUp(self):
        super().setUp()
        self.request_user = None

    def test_pool(self):
        data = self.get_data()
        resp = self.make_request()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], 1)
        self.assertEqual(resp.data['results'][0]['id'], str(data['test_candidate'].id))

    def test_pool_anonym(self):
        self.request_user = AnonymousUser()
        data = self.get_data()
        resp = self.make_request()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], 0)
        self.assertEqual(resp.data['results'], [])


class TestBuyAPITestCase(BaseTestCase):
    view_name = 'api:candidate/candidatecontacts-buy'

    def get_url(self, view_name=None, args=None, kwargs=None):
        return reverse(view_name or self.view_name,
                       kwargs=kwargs or self.get_view_kwargs())

    def get_allowed_users(self):
        if self.request_user is not None:
            return [self.request_user]
        return [core_models.User.objects.create_superuser(
            email='test@test.mm', phone_mobile='+79275678901',
            password='test1234'
            )]

    def setUp(self):
        super().setUp()
        load_data()
        self.request_user = None

    def test_buy_success(self):
        resp = self.make_request(
            method='POST',
            view_kwargs={"pk": "63382061-88a8-4449-a84e-40c6f238ccd6"},
            data={"company": "d882fc63-8198-4193-b5f1-935b1f6f8f8e"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'success')
        self.assertEqual(resp.data['message'], 'Please wait for candidate to agree sharing their '
                                                           'information')

    def test_buy_cannot_sell_candidate(self):
        candidate_rel = CandidateRel.objects.get(pk="d4536e9c-0d7c-4178-9943-94aafe000952")
        candidate_rel.owner = False
        candidate_rel.save()
        resp = self.make_request(
            method='POST',
            view_kwargs={"pk": "63382061-88a8-4449-a84e-40c6f238ccd6"},
            data={"company": "d882fc63-8198-4193-b5f1-935b1f6f8f8e"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['status'], 'error')
        self.assertIn('cannot sell this candidate.', resp.data['errors']['company'])

    def test_buy_cannot_find_company(self):
        resp = self.make_request(
            method='POST',
            view_kwargs={"pk": "63382061-88a8-4449-a84e-40c6f238ccd6"},
            data={"company": "d882fc63-8198-4193-b5f1-935b1f6f8f8d"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['status'], 'error')
        self.assertIn('Cannot find company',
                      resp.data['errors']['company'])

    def test_buy_regular_company(self):
        company = core_models.Company.objects.get(pk="d882fc63-8198-4193-b5f1-935b1f6f8f8e")
        company.type = core_models.Company.COMPANY_TYPES.regular
        company.save()
        resp = self.make_request(
            method='POST',
            view_kwargs={"pk": "63382061-88a8-4449-a84e-40c6f238ccd6"},
            data={"company": "d882fc63-8198-4193-b5f1-935b1f6f8f8e"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['status'], 'error')
        self.assertIn("Only Master company can buy candidate's profile",
                      resp.data['errors']['company'])

    def test_buy_existing_rel(self):
        resp = self.make_request(
            method='POST',
            view_kwargs={"pk": "63382061-88a8-4449-a84e-40c6f238ccd6"},
            data={"company": "02d5b262-e53a-4fc0-92d6-500335910851"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['status'], 'error')
        self.assertIn("Company already has this Candidate Contact",
                      resp.data['errors']['company'])

    def test_buy_stripe_customer_not_exist(self):
        company = core_models.Company.objects.get(pk="d882fc63-8198-4193-b5f1-935b1f6f8f8e")
        company.stripe_customer = None
        company.save()
        resp = self.make_request(
            method='POST',
            view_kwargs={"pk": "63382061-88a8-4449-a84e-40c6f238ccd6"},
            data={"company": "d882fc63-8198-4193-b5f1-935b1f6f8f8e"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['status'], 'error')
        self.assertIn("Company has no billing information",
                      resp.data['errors']['company'])

@patch('r3sourcer.apps.core.models.core.fetch_geo_coord_by_address',
       return_value=(42, 42))
def address(db):
    country, _ = core_models.Country.objects.get_or_create(name='Australia', code2='AU')
    state = core_models.Region.objects.create(name='test', country=country)
    city = core_models.City.objects.create(name='city', country=country)
    return core_models.Address.objects.create(
        street_address="test street",
        postal_code="123456",
        city=city,
        state=state
    )

@pytest.fixture
@patch.object(hr_models.JobOffer, 'check_job_quota', return_value=True)
def job_offer(mock_check, db, shift, candidate_contact):
    job_offer = hr_models.JobOffer.objects.create(
        shift=shift,
        candidate_contact=candidate_contact,
        status=hr_models.JobOffer.STATUS_CHOICES.accepted,
    )

    hr_models.JobOfferSMS.objects.create(job_offer=job_offer, offer_sent_by_sms=None)

    return job_offer


class TestCandidatesLocationAPITestCase(BaseTestCase):
    view_name = 'api:candidate/location-candidates-location'

    def get_url(self, view_name=None, args=None, kwargs=None):
        return reverse(view_name or self.view_name,
                       kwargs=kwargs or self.get_view_kwargs())

    def get_allowed_users(self):
        if self.request_user is not None:
            return [self.request_user]
        return [core_models.User.objects.create_superuser(
            email='test@test.mm', phone_mobile='+32345678901',
            password='test1234'
            )]

    def get_data(self):
        user = core_models.User.objects.create_user(
            email='test@test.vt', phone_mobile='+12345678801',
            password='test1234'
            )
        industry = Industry.objects.create(type='test')
        skill_name = SkillName.objects.create(name="Driver", industry=industry)
        candidate_contact = CandidateContact.objects.create(
            contact=user.contact
            )
        company_contact = core_models.CompanyContact.objects.create(
            contact=user.contact
            )
        master_company = core_models.Company.objects.create(
            name='Master',
            business_id='123',
            registered_for_gst=True,
            type=core_models.Company.COMPANY_TYPES.master,
            timesheet_approval_scheme=core_models.Company.TIMESHEET_APPROVAL_SCHEME.PIN
        )
        skill = Skill.objects.create(
            name=skill_name,
            carrier_list_reserve=2,
            short_name="Drv",
            active=False,
            company=master_company
            )
        regular_company = core_models.Company.objects.create(
            name='Regular',
            business_id='321',
            registered_for_gst=True,
            type=core_models.Company.COMPANY_TYPES.regular
            )
        jobsite = hr_models.Jobsite.objects.create(
            industry=industry,
            master_company=master_company,
            start_date=datetime.date.today(),
            end_date=datetime.date.today() + datetime.timedelta(days=7),
            address=address(),
            regular_company=regular_company,
            )
        candidate_rel = CandidateRel.objects.create(
            candidate_contact=candidate_contact,
            master_company=master_company,
            company_contact=company_contact,
            owner=True,
            active=True
            )
        job = hr_models.Job.objects.create(
            provider_company=master_company,
            customer_company=regular_company,
            jobsite=jobsite,
            position=skill,
            published=True
            )
        shift_date = hr_models.ShiftDate.objects.create(
            job=job,
            shift_date=timezone.now() - timezone.timedelta(hours=10)
            )

        shift = hr_models.Shift.objects.create(
                date=shift_date,
                time=datetime.time(hour=7, minute=00)
            )
        job_offer_obj = job_offer(shift=shift, candidate_contact=candidate_contact, db=None)
        timesheet = hr_models.TimeSheet.objects.create(
                going_to_work_confirmation=True,
                job_offer=job_offer_obj,
                supervisor=company_contact,
                shift_started_at=timezone.now().replace(hour=8, minute=0),
                shift_ended_at=timezone.now().replace(hour=8, minute=0) + timezone.timedelta(hours=8),
                supervisor_approved_at=timezone.now(),
                candidate_submitted_at=timezone.now(),
            )
        return {'job': job,  'job_offer': job_offer_obj,
                'shift_date': shift_date, "timesheet": timesheet}

    def setUp(self):
        super().setUp()
        self.request_user = None

    def test_success(self):
        with mock.patch(
                'r3sourcer.apps.logger.services.LocationLogger.fetch_location_candidates',
                return_value={"results": [{"test": "test-something"}]}) as location_mock:
            data = self.get_data()
            resp = self.make_request(data={"job_id": data['job'].id})
            location_mock.assert_called_with([data['timesheet'].id])
            self.assertEqual(resp.status_code, 200)


class TestConsentAPITestCase(BaseTestCase):
    view_name = 'api:candidate/candidatecontacts-consent'

    def get_url(self, view_name=None, args=None, kwargs=None):
        return reverse(view_name or self.view_name,
                       kwargs=kwargs or self.get_view_kwargs())

    def get_allowed_users(self):
        if self.request_user is not None:
            return [self.request_user]
        return [core_models.User.objects.create_superuser(
            email='test@test.mm',
            phone_mobile='+79274567890',
            password='test1234'
            )]

    def setUp(self):
        super().setUp()
        self.request_user = None
        load_data()

    def test_give_consent(self):
        candidate_rel = CandidateRel.objects.get(pk="d4536e9c-0d7c-4178-9943-94aafe000952")
        resp = self.make_request(method='POST', view_kwargs={"pk": "d4536e9c-0d7c-4178-9943-94aafe000952"}, data={"agree": True})

        self.assertEqual(resp.status_code, 200)

        candidate_rel.refresh_from_db()
        self.assertEqual(candidate_rel.sharing_data_consent, True)

    def test_doesnt_give_consent(self):
        candidate_rel = CandidateRel.objects.get(pk="d4536e9c-0d7c-4178-9943-94aafe000952")
        resp = self.make_request(method='POST', view_kwargs={"pk": candidate_rel.pk}, data={"agree": False})

        self.assertEqual(resp.status_code, 200)

        candidate_rel.refresh_from_db()
        self.assertEqual(candidate_rel.sharing_data_consent, False)

    def test_not_existing_candidaterel(self):
        resp = self.make_request(method='POST',
                                 view_kwargs={"pk": "d4536e9c-0d7c-4178-9943-94aafe000951"},
                                 data={"agree": False})

        self.assertEqual(resp.status_code, 404)
