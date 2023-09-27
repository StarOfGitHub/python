import mock
import pytest
import googlemaps
from django.core.exceptions import ValidationError

from r3sourcer.apps.core.models import CompanyContactRelationship
from r3sourcer.apps.core.utils.companies import get_closest_companies, get_master_companies
from r3sourcer.apps.core.utils.geo import fetch_geo_coord_by_address, calc_distance
from r3sourcer.apps.core.utils.validators import string_is_numeric


class TestGeo:

    @mock.patch('r3sourcer.apps.core.utils.geo.googlemaps')
    def test_fetch_geo_coord_successfull(self, mock_googlemaps):
        mock_gmaps = mock_googlemaps.Client.return_value
        mock_gmaps.geocode.return_value = [
            {
                'geometry': {
                    'location': {
                        'lat': 42,
                        'lng': 24
                    }
                }
            }
        ]

        lat, lng = fetch_geo_coord_by_address('test address')

        assert (lat, lng) == (42, 24)

    @mock.patch('r3sourcer.apps.core.utils.geo.googlemaps')
    def test_fetch_geo_coord_unsuccessfull(self, mock_googlemaps):
        mock_gmaps = mock_googlemaps.Client.return_value
        mock_gmaps.geocode.side_effect = googlemaps.exceptions.ApiError('REQUEST_DENIED')
        lat, lng = fetch_geo_coord_by_address('test address')
        assert (lat, lng) == (False, False)

    @mock.patch('r3sourcer.apps.core.utils.geo.googlemaps')
    def test_fetch_geo_coord_wrong_gkey(self, mock_googlemaps):
        mock_gmaps = mock_googlemaps.Client.return_value
        mock_gmaps.geocode.side_effect = ValueError('error')
        lat, lng = fetch_geo_coord_by_address('test address')

        assert (lat, lng) == (False, False)

    @mock.patch('r3sourcer.apps.core.utils.geo.googlemaps')
    def test_calc_distance_successfull(self, mock_googlemaps):
        mock_gmaps = mock_googlemaps.Client.return_value
        mock_gmaps.distance_matrix.return_value = {
            'destination_addresses': ['test address 1', 'test address 2'],
            'rows': [{'elements': [
                {
                    'status': 'OK',
                    'distance': {'value': 1535427, 'text': '1,535 km'},
                    'duration': {'value': 87821, 'text': '1 day 0 hours'}
                },
                {
                    'status': 'OK',
                    'distance': {'value': 1538731, 'text': '1,539 km'},
                    'duration': {'value': 89893, 'text': '1 day 1 hour'}
                }
            ]}],
            'origin_addresses': ['test_address'],
            'status': 'OK'
        }
        distance_matrix = calc_distance('test address', ['test address 1', 'test address 2'])
        assert distance_matrix == [[
            {'distance': 1535427, 'duration': 87821},
            {'distance': 1538731, 'duration': 89893}
        ]]

    @mock.patch('r3sourcer.apps.core.utils.geo.googlemaps.Client')
    def test_calc_distance_unsuccessfull(self, mock_googlemaps):
        mock_gmaps = mock_googlemaps.return_value
        mock_gmaps.distance_matrix.side_effect = googlemaps.exceptions.ApiError('REQUEST_DENIED')
        res = calc_distance('test address', ['test address 1', 'test address 2'])

        assert res == []

    @mock.patch('r3sourcer.apps.core.utils.geo.googlemaps.Client')
    def test_calc_distance_query_limit_reached(self, mock_googlemaps):
        mock_gmaps = mock_googlemaps.return_value
        mock_gmaps.distance_matrix.side_effect = googlemaps.exceptions.ApiError('OVER_QUERY_LIMIT')
        res = calc_distance('test address', ['test address 1', 'test address 2'])

        assert res == []

    @mock.patch('r3sourcer.apps.core.utils.geo.googlemaps.Client')
    def test_calc_distance_query_wrong_gkey(self, mock_googlemaps):
        mock_gmaps = mock_googlemaps.return_value
        mock_gmaps.distance_matrix.side_effect = ValueError('error')
        res = calc_distance('test address', ['test address 1', 'test address 2'])

        assert res == []


class TestCompanies:
    def test_get_closest_companies(self, staff_user, staff_relationship):
        request = mock
        request.user = staff_user
        companies = get_closest_companies(request)
        assert len(companies) == 1

    def test_get_master_companies_closest(self, staff_user, staff_relationship):
        request = mock
        request.user = staff_user
        companies = get_master_companies(request)
        assert len(companies) == 1
        assert staff_relationship.company in companies

    def test_get_master_companies_not_closest(self, staff_company_contact, company_rel):
        CompanyContactRelationship.objects.create(
            company_contact=staff_company_contact,
            company=company_rel.regular_company,
        )
        request = mock
        request.user = staff_company_contact.contact.user
        companies = get_master_companies(request)
        assert len(companies) == 1
        assert company_rel.master_company in companies


class TestValidators:

    def test_not_numeric_values(self):
        with pytest.raises(ValidationError):
            string_is_numeric('test1')

        with pytest.raises(ValidationError):
            string_is_numeric('1test')

    def test_numeric_values(self):
        assert string_is_numeric('123') is None
        assert string_is_numeric('012') is None
