import copy
import json
from datetime import datetime

import mock
import pytest
from django.test.client import MULTIPART_CONTENT
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.test import force_authenticate
from freezegun import freeze_time

from r3sourcer.apps.candidate.models import CandidateContact
from r3sourcer.apps.core.models import CompanyContact
from r3sourcer.apps.hr.api.viewsets import TimeSheetViewset
from r3sourcer.apps.hr.endpoints import TimeSheetEndpoint
from r3sourcer.apps.hr.models import TimeSheet


class TimeSheetEndpointTest(TimeSheetEndpoint):
    model = TimeSheet


TimeSheetViewsets = TimeSheetEndpointTest().get_viewset()


@pytest.mark.django_db
class TestApiViewset:

    def get_response_as_view(self, actions, request, pk=None, viewset=None):
        kwargs = {'request': request, 'pk': pk}
        viewset = viewset or TimeSheetViewsets
        view = viewset.as_view(actions)
        response = view(**kwargs)
        response.render()
        return response

    def update_scheme(self, company, scheme):
        company.timesheet_approval_scheme = scheme
        company.save()

    @pytest.fixture
    def signature_data(self, picture):
        return dict(supervisor_signature=copy.deepcopy(picture))

    @pytest.fixture
    def master_company_with_pin(self, master_company):
        self.update_scheme(master_company, master_company.TIMESHEET_APPROVAL_SCHEME.PIN)
        return master_company

    @pytest.fixture
    def master_company_with_signature(self, master_company):
        self.update_scheme(master_company, master_company.TIMESHEET_APPROVAL_SCHEME.SIGNATURE)
        return master_company

    def test_approve_by_failed_pin_code(
        self, company_rel, company_contact_rel, timesheet, master_company_with_pin, rf
    ):
        req = rf.post('/{}/approve_by_pin/'.format(timesheet.pk), data=json.dumps({'pin_code': '1233'}),
                      content_type='application/json')
        response = self.get_response_as_view({'post': 'approve_by_pin'}, req, pk=timesheet.pk)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data['status'] == 'error'
        assert 'pin_code' in response.data['errors']
        assert 'Incorrect pin code' in response.data['errors']['pin_code']

    def test_approve_by_pin_code(self, timesheet, company_rel, company_contact_rel, master_company_with_pin, rf):
        req = rf.post('/{}/approve_by_pin/'.format(timesheet.pk), data=json.dumps({'pin_code': '1234'}),
                      content_type='application/json')

        assert timesheet.supervisor_approved_at is None

        response = self.get_response_as_view({'post': 'approve_by_pin'}, req, pk=timesheet.pk)
        assert response.data is None
        assert response.status_code == status.HTTP_200_OK

        timesheet.refresh_from_db()

        assert timesheet.supervisor_approved_at is not None

    def test_approve_with_incorrect_scheme(self, timesheet, company_rel, company_contact_rel, signature_data,
                                           master_company_with_pin, rf):
        req = rf.post('/{}/approve_by_signature/'.format(timesheet.pk), data=signature_data,
                      content_type=MULTIPART_CONTENT)

        response = self.get_response_as_view({'post': 'approve_by_signature'}, req, pk=timesheet.pk)

        assert 'errors' in response.data
        assert 'non_field_errors' in response.data['errors']
        assert 'Incorrect approval scheme' in response.data['errors']['non_field_errors']
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_approve_by_signature(self, timesheet, company_rel, company_contact_rel, signature_data,
                                  master_company_with_signature, rf):
        req = rf.post('/{}/approve_by_signature/'.format(timesheet.pk), data=signature_data,
                      content_type=MULTIPART_CONTENT)

        assert timesheet.supervisor_approved_at is None

        response = self.get_response_as_view({'post': 'approve_by_signature'}, req, pk=timesheet.pk)

        assert response.status_code == status.HTTP_200_OK
        assert response.data is None

        timesheet.refresh_from_db()

        assert timesheet.supervisor_approved_at is not None

    def test_approve_with_empty_signature(
        self, timesheet, company_rel, company_contact_rel, signature_data, master_company_with_signature, rf
    ):
        req = rf.post('/{}/approve_by_signature/'.format(timesheet.pk), content_type=MULTIPART_CONTENT)

        response = self.get_response_as_view({'post': 'approve_by_signature'}, req, pk=timesheet.pk)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

        assert 'errors' in response.data
        assert 'supervisor_signature' in response.data['errors'] and \
               'No file was submitted.' in response.data['errors']['supervisor_signature']

    def test_approve_with_empty_pincode(self, timesheet, master_company_with_pin, rf):
        req = rf.post('/{}/approve_by_pin/'.format(timesheet.pk), content_type='application/json')
        response = self.get_response_as_view({'post': 'approve_by_pin'}, req, pk=timesheet.pk)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert isinstance(response.data, dict)
        assert 'errors' in response.data
        assert 'pin_code' in response.data['errors'] and \
               'This field is required.' in response.data['errors']['pin_code']

    @mock.patch.object(CompanyContact, 'get_master_company', return_value=[])
    def test_approve_by_signature_no_companies(
            self, mock_comp, timesheet, company_rel, company_contact_rel,
            signature_data, master_company_with_signature, rf):
        req = rf.post('/{}/approve_by_signature/'.format(timesheet.pk),
                      data=signature_data, content_type=MULTIPART_CONTENT)

        assert timesheet.supervisor_approved_at is None

        response = self.get_response_as_view(
            {'post': 'approve_by_signature'}, req, pk=timesheet.pk)

        assert 'errors' in response.data

    def test_approve_by_signature_already_approved(
            self, timesheet_approved, company_rel, signature_data,
            company_contact_rel, master_company_with_signature, rf):
        req = rf.post('/{}/approve_by_signature'.format(timesheet_approved.pk),
                      data=signature_data, content_type=MULTIPART_CONTENT)

        response = self.get_response_as_view(
            {'post': 'approve_by_signature'}, req, pk=timesheet_approved.pk)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_approve_by_pin_code_already_approved(
            self, timesheet_approved, company_rel, company_contact_rel,
            master_company_with_pin, rf):
        req = rf.post('/{}/approve_by_pin/'.format(timesheet_approved.pk),
                      data=json.dumps({'pin_code': '1234'}),
                      content_type='application/json')

        response = self.get_response_as_view(
            {'post': 'approve_by_pin'}, req, pk=timesheet_approved.pk)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @mock.patch.object(TimeSheetViewset, 'paginated')
    def test_handle_history(self, mock_paginated, rf, timesheet, user):
        mock_paginated.return_value = Response({'results': [timesheet]})

        req = rf.get('/history/')
        force_authenticate(req, user=user)

        viewset = TimeSheetViewset()
        viewset.request = Request(req)

        response = viewset.handle_history(viewset.request)

        assert len(response.data['results']) == 1

    @mock.patch.object(TimeSheetViewset, 'paginated')
    def test_handle_history_candidate(self, mock_paginated, rf, timesheet,
                                      user_another):
        mock_paginated.return_value = Response({'results': [timesheet]})

        req = rf.get('/history/')
        force_authenticate(req, user=user_another)

        viewset = TimeSheetViewset()
        viewset.request = Request(req)

        response = viewset.handle_history(viewset.request)

        assert len(response.data['results']) == 1

    @mock.patch.object(TimeSheetViewset, 'paginated')
    def test_handle_history_no_auth(self, mock_paginated, rf, timesheet):
        mock_paginated.return_value = Response({'results': []})

        req = rf.get('/history/')
        req.user = AnonymousUser()

        viewset = TimeSheetViewset()
        viewset.request = req

        response = viewset.handle_history(req)

        assert len(response.data['results']) == 0

    @freeze_time(datetime(2017, 1, 1, 9))
    @mock.patch('r3sourcer.apps.hr.models.hr_utils')
    @mock.patch('r3sourcer.apps.hr.api.viewsets.hr_utils')
    @mock.patch('r3sourcer.apps.hr.api.viewsets.generate_invoice')
    def test_submit_hours_candidate(self, mock_invoice, mock_task, mock_going_to_work, timesheet):
        data = {
            'shift_started_at': timezone.now(),
        }
        viewset = TimeSheetViewset()

        response = viewset.submit_hours(data, timesheet)

        assert response.data['id'] == str(timesheet.id)

    @freeze_time(datetime(2017, 1, 1, 9))
    @mock.patch('r3sourcer.apps.hr.api.viewsets.generate_invoice')
    def test_submit_hours_supervisor(self, mock_invoice, timesheet):
        data = {
            'shift_started_at': timezone.now(),
        }
        viewset = TimeSheetViewset()

        response = viewset.submit_hours(data, timesheet, False)

        assert response.data['id'] == str(timesheet.id)

    @freeze_time(datetime(2017, 1, 1, 0, 30))
    def test_get_unapproved_queryset(self, rf, user, timesheet_approved):
        viewset = TimeSheetViewset()

        req = rf.get('/')
        force_authenticate(req, user=user)
        viewset.request = Request(req)

        response = viewset.get_unapproved_queryset(req)

        assert len(response) == 1

    def test_get_unapproved_queryset_candidate(self, rf, user, timesheet):
        viewset = TimeSheetViewset()

        req = rf.get('/')
        force_authenticate(req, user=user)
        viewset.request = Request(req)

        response = viewset.get_unapproved_queryset(req)

        assert len(response) == 0

    def test_handle_request(self, rf, user, timesheet):
        viewset = TimeSheetViewset()

        req = rf.get('/')
        req.user = user

        response = viewset.handle_request(req, timesheet.id)

        assert response.data['id'] == str(timesheet.id)

    @mock.patch.object(TimeSheetViewset, 'submit_hours')
    def test_handle_request_put(self, mock_submit, rf, user, timesheet):
        mock_submit.return_value = Response([timesheet])

        viewset = TimeSheetViewset()

        req = rf.put('/')
        req.user = user

        response = viewset.handle_request(Request(req), timesheet.id)

        assert len(response.data) == 1

    @mock.patch.object(TimeSheetViewset, 'get_object')
    def test_evaluate(self, mock_obj, rf, timesheet, user):
        mock_obj.return_value = timesheet
        data = {
            'was_on_time': True,
            'was_motivated': True,
            'had_ppe_and_tickets': True,
            'met_expectations': True,
            'representation': True
        }
        req = rf.put('/{}/evaluate/'.format(timesheet.pk),
                     data=json.dumps(data),
                     content_type='application/json')

        response = self.get_response_as_view(
            {'put': 'evaluate'}, req, pk=timesheet.pk)

        assert response.data['status'] == 'success'


@pytest.mark.django_db
class TestJobViewset:
    view_name = 'api:hr/jobs-fillin'

    @freeze_time(datetime(2017, 1, 1, 6))
    @mock.patch('r3sourcer.apps.hr.utils.job.get_available_candidate_list')
    def test_fillin_partially_available(
        self, mock_available_candidate_list, client, user, job_with_four_shifts, shift_first, shift_second,
            shift_third, shift_fourth, rf, skill_rel, skill_rel_second, candidate_rel, candidate_rel_second
    ):
        mock_available_candidate_list.return_value.fetch.return_value = CandidateContact.objects.all()
        url = reverse(self.view_name, args=[job_with_four_shifts.pk])
        client.force_login(user)
        response = client.get(url).json()

        assert len(response['shifts']) == 4
        assert len(response['list']) == 2

    @freeze_time(datetime(2017, 1, 1, 0))
    @mock.patch('r3sourcer.apps.hr.utils.job.get_available_candidate_list')
    def test_fillin_partially_available_with_unavailable(
        self, mock_available_candidate_list, client, user, job_with_four_shifts, shift_first, shift_second,
            shift_third, shift_fourth, rf, skill_rel, skill_rel_second, candidate_rel, candidate_rel_second,
            job_offer_for_candidate_fifth_shift
    ):
        mock_available_candidate_list.return_value.fetch.return_value = CandidateContact.objects.all()
        url = reverse(self.view_name, args=[job_with_four_shifts.pk])
        client.force_login(user)
        response = client.get(url,  {'available': 'False'}).json()

        assert len(response['shifts']) == 4
        assert len(response['list']) == 1


    @freeze_time(datetime(2017, 1, 1, 0))
    @mock.patch('r3sourcer.apps.hr.utils.job.get_available_candidate_list')
    def test_fillin_partially_available_with_available_true(
        self, mock_available_candidate_list, client, user, job_with_four_shifts, shift_first, shift_second,
            shift_third, shift_fourth, rf, skill_rel, skill_rel_second, candidate_rel, candidate_rel_second,
            job_offer_for_candidate_fifth_shift
    ):
        mock_available_candidate_list.return_value.fetch.return_value = CandidateContact.objects.all()
        url = reverse(self.view_name, args=[job_with_four_shifts.pk])
        client.force_login(user)
        response = client.get(url,  {'available': 'True'}).json()

        assert len(response['shifts']) == 4
        assert len(response['list']) == 2
