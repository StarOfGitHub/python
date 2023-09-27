import base64
from datetime import datetime, timedelta

import mock
import pytest
import pytz

from django_mock_queries.query import MockSet
from rest_framework.exceptions import ValidationError
from rest_framework import fields

from r3sourcer.apps.core.api.fields import (
    ApiAbsoluteUrlMixin, ApiBaseRelatedField,
    ApiContactPictureField, ApiBase64ImageField, ApiChoicesField,
    EmptyNullField,
)


class TestApiAbsoluteUrlMixin:

    def get_object(self, request):
        obj = ApiAbsoluteUrlMixin()
        type(obj).context = mock.PropertyMock(
            return_value={'request': request}
        )

        return obj

    def test_get_absolute(self):
        req = mock.MagicMock()
        req.build_absolute_uri.return_value = 'path/url'
        obj = self.get_object(req)

        assert obj.get_absolute('url') == 'path/url'

    def test_get_absolute_value_none(self):
        req = mock.MagicMock()
        req.build_absolute_uri.return_value = 'url'
        obj = self.get_object(req)

        assert obj.get_absolute(None) is None

    def test_get_absolute_value_empty(self):
        req = mock.MagicMock()
        req.build_absolute_uri.return_value = 'url'
        obj = self.get_object(req)

        assert obj.get_absolute('') == ''

    def test_get_absolute_request_none(self):
        obj = self.get_object(None)

        assert obj.get_absolute('url') == 'url'


class TestApiBaseRelatedField:

    def test_to_representation(self):
        obj = ApiBaseRelatedField(queryset=MockSet())

        mock_obj = mock.MagicMock()
        type(mock_obj).id = mock.PropertyMock(return_value=1)
        mock_obj.__str__.return_value = 'str'

        assert obj.to_representation(mock_obj) == {
            'id': 1,
            'name': 'str',
            '__str__': 'str',
        }


class TestApiBase64ImageField:

    @pytest.fixture
    def base64_data(self, picture):
        res = base64.b64encode(picture.read())
        picture.seek(0)
        return res

    @pytest.fixture
    def obj(self):
        return ApiBase64ImageField()

    @mock.patch('r3sourcer.apps.core.api.fields.what', return_value='jpeg')
    def test_get_file_extension_jpg(self, mock_what, obj):
        assert obj.get_file_extension('', '') == '.jpg'

    @mock.patch('r3sourcer.apps.core.api.fields.what', return_value='png')
    def test_get_file_extension_not_jpg(self, mock_what, obj):
        assert obj.get_file_extension('', '') == '.png'

    @mock.patch.object(ApiBase64ImageField, 'get_file_extension', return_value='.jpg')
    def test_to_internal_value(self, mock_ext, base64_data, obj, picture):
        res = obj.to_internal_value(base64_data.decode('utf-8'))

        assert res.read() == picture.read()

    @mock.patch.object(ApiBase64ImageField, 'get_file_extension', return_value='.jpg')
    def test_to_internal_value_with_type(self, mock_ext, base64_data, obj,
                                         picture):
        res = obj.to_internal_value(
            'data:image/jpeg;base64,%s' % base64_data.decode('utf-8'))

        assert res.read() == picture.read()

    def test_to_internal_value_with_image_type(self, obj, picture):
        res = obj.to_internal_value(picture)

        assert res is picture

    @mock.patch.object(ApiBase64ImageField, 'fail',
                       side_effect=ValidationError('error'))
    @mock.patch.object(ApiBase64ImageField, 'get_file_extension',
                       return_value='jpg')
    def test_to_internal_value_error(self, mock_ext, mock_fail, obj):
        with pytest.raises(ValidationError):
            obj.to_internal_value('\xf134')


class TestApiContactPictureField:

    @mock.patch('r3sourcer.apps.core.api.fields.get_thumbnail_picture',
                side_effect=['small', 'large'])
    def test_get_absolute(self, mock_get_pic):
        with mock.patch.object(ApiContactPictureField, 'get_absolute', side_effect=['small', 'large']):
            obj = ApiContactPictureField()

            mock_obj = mock.MagicMock()

            assert obj.to_representation(mock_obj) == {
                'thumb': 'small',
                'origin': 'large',
            }


class TestApiChoicesField:

    @pytest.fixture
    def field(self):
        return ApiChoicesField(choices={timedelta(seconds=60): 'val'},
                               allow_blank=True)

    def test_convert_to_text_timedelta(self, field):
        res = field._convert_to_text(timedelta(minutes=1))

        assert res == '60'

    def test_to_internal_value_timedelta(self, field):
        res = field.to_internal_value('60.0')

        assert res == timedelta(seconds=60)

    def test_to_internal_value_empty_data(self, field):
        res = field.to_internal_value('')

        assert res == ''

    def test_to_internal_value_str_data(self):
        field = ApiChoicesField(choices={'test': 'val'})

        res = field.to_internal_value('test')

        assert res == 'test'

    def test_to_internal_value_error(self, field):
        with pytest.raises(ValidationError):
            field.to_internal_value('test')


class TestEmptyNullField:

    @pytest.fixture
    def field(self):
        class Field(EmptyNullField, fields.CharField):
            pass

        return Field(required=False, default='')

    def test_run_validation(self, field):
        res = field.run_validation(data='test')

        return res == 'test'

    def test_run_validation_empty(self, field):
        res = field.run_validation(data=None)

        return res == ''
