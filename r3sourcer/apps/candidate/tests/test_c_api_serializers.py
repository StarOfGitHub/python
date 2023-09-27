import mock
import pytest
from decimal import Decimal

from rest_framework.exceptions import ValidationError
from django_mock_queries.query import MockModel

from r3sourcer.apps.candidate.api.serializers import (
    CandidateContactSerializer, CandidateContactRegisterSerializer
)
from r3sourcer.apps.candidate.models import CandidateContact
from r3sourcer.apps.hr import models as hr_models


@pytest.mark.django_db
class TestCandidateContactSerializer:

    @pytest.fixture
    def serializer_obj(self):
        return CandidateContactSerializer()

    def test_can_create_contact(self, contact, serializer_obj):
        candidate_contact_data = {
            'contact': contact,
            'tax_number': '123'
        }
        instance = serializer_obj.create(candidate_contact_data)

        assert isinstance(instance, CandidateContact)
        assert instance.pk is not None

    def test_create_contact_without_contact(self, contact, serializer_obj):
        candidate_contact_data = {
            'tax_number': '123'
        }
        with pytest.raises(Exception):
            serializer_obj.create(candidate_contact_data)

    @mock.patch.object(CandidateContact, 'get_active_states')
    def test_get_active_states(self, mock_states, candidate, serializer_obj):
        mock_states.return_value = [
            MockModel(state=MockModel(name_after_activation='test'))
        ]

        res = serializer_obj.get_active_states(candidate)

        assert len(res) == 1
        assert res == [{'id': None, 'number': None, '__str__': 'test'}]

    def test_get_active_states_none(self, serializer_obj):
        res = serializer_obj.get_active_states(None)

        assert res is None

    @mock.patch.object(hr_models.CandidateScore, 'get_average_score', return_value=Decimal('5.00'))
    def test_get_average_score(self, mock_states, candidate, serializer_obj):
        res = serializer_obj.get_average_score(candidate)

        assert res == '5.00'

    def test_get_average_score_none(self, serializer_obj):
        res = serializer_obj.get_average_score(None)

        assert res is None

    def test_create_validate_contact_error(self, contact, candidate,
                                           serializer_obj):
        candidate_contact_data = {
            'contact': contact,
            'tax_number': '123'
        }
        with pytest.raises(ValidationError):
            serializer_obj.create(candidate_contact_data)

    @mock.patch.object(CandidateContact, 'get_bmi', return_value=5)
    def test_get_bmi(self, mock_bmi, candidate, serializer_obj):
        res = serializer_obj.get_bmi(candidate)

        assert res == 5

    def test_get_bmi_none(self, serializer_obj):
        res = serializer_obj.get_bmi(None)

        assert res is None

    def test_get_skill_list(self, candidate, serializer_obj,
                            skill_rel):
        res = serializer_obj.get_skill_list(candidate)

        assert res[0]['skill']['__str__'] == 'Driver'

    def test_get_skill_list_no_items(self, candidate,
                                     serializer_obj):
        res = serializer_obj.get_skill_list(candidate)

        assert res == []

    def test_get_skill_list_none(self, serializer_obj):
        res = serializer_obj.get_skill_list(None)

        assert res is None

    def test_get_tag_list(self, candidate, serializer_obj,
                          tag_rel):
        res = serializer_obj.get_tag_list(candidate)

        assert res[0]['tag']['__str__'] == 'Tag name'

    def test_get_tag_list_no_items(self, candidate,
                                   serializer_obj):
        res = serializer_obj.get_tag_list(candidate)

        assert res == []

    def test_get_tag_list_none(self, serializer_obj):
        res = serializer_obj.get_tag_list(None)

        assert res is None


@pytest.mark.django_db
class TestCandidateContactRegisterSerializer:

    @pytest.fixture
    def serializer_obj(self):
        return CandidateContactRegisterSerializer()

    @pytest.fixture
    def register_data(self, country, skill, tag):
        return {
            'first_name': 'Test',
            'last_name': 'Tester',
            'email': 'tester@test.tt',
            'phone_mobile': '+12345678940',
            'address': {
                'street_address': 'test str',
                'country': country,
            },
            'birthday': '1991-02-02',
            'skills': [skill],
            'tags': [tag],
            'agree': True,
        }

    @mock.patch('r3sourcer.apps.core.models.core.fetch_geo_coord_by_address', return_value=(1, 1))
    def test_create_candidate(self, mock_geo, serializer_obj, register_data):
        instance = serializer_obj.create(register_data)

        assert isinstance(instance, CandidateContact)
        assert instance.pk is not None

    def test_create_candidate_do_not_agree(self, serializer_obj, register_data):
        register_data['agree'] = False

        with pytest.raises(ValidationError):
            serializer_obj.create(register_data)

    @mock.patch('r3sourcer.apps.core.models.core.fetch_geo_coord_by_address', return_value=(1, 1))
    def test_create_candidate_no_tags(self, mock_geo, serializer_obj, register_data):
        register_data['tags'] = None
        instance = serializer_obj.create(register_data)

        assert not instance.tag_rels.exists()

    @mock.patch('r3sourcer.apps.core.models.core.fetch_geo_coord_by_address', return_value=(1, 1))
    def test_create_candidate_no_skills(self, mock_geo,  serializer_obj, register_data):
        register_data['skills'] = None
        instance = serializer_obj.create(register_data)

        assert not instance.candidate_skills.exists()
