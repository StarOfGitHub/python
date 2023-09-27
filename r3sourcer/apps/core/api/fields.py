import base64
import copy
import mimetypes
import six
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.files.base import ContentFile
from imghdr import what
from rest_framework import serializers

from ..utils.utils import get_thumbnail_picture


class ApiAbsoluteUrlMixin():
    def get_absolute(self, value):
        if not value:
            return value
        request = self.context.get('request', None)
        domain = Site.objects.get_current().domain
        if request is not None:
            return 'https://{domain}{path}'.format(domain=domain, path=value) #request.build_absolute_uri(value)
        return value


class ApiBaseRelatedField(serializers.RelatedField):
    def to_representation(self, value):
        str_val = str(value)
        data = {
            'id': value.pk,
            'name': str_val,
            '__str__': str_val,
        }
        if hasattr(value, 'timezone'):
            data['timezone'] = value.timezone

        return data

    @classmethod
    def to_read_only_data(cls, value):
        return cls(read_only=True).to_representation(value)


class ApiBase64FileField(serializers.FileField):
    """
    A Django REST framework field for handling file-uploads through raw post data.
    It uses base64 for encoding and decoding the contents of the file.
    """

    def to_internal_value(self, data):
        # Check if this is a base64 string
        if isinstance(data, six.string_types):
            if 'data:' in data and ';base64,' in data:
                header, data = data.split(';base64,')
            else:
                header = 'image/jpeg'

            try:
                decoded_file = base64.b64decode(data.encode('ascii'))
            except (TypeError, UnicodeEncodeError):
                self.fail('invalid')

            file_name = str(uuid.uuid4())
            file_extension = self.get_file_extension(file_name, decoded_file, header.replace('data:', ''))

            complete_file_name = "%s%s" % (file_name, file_extension, )

            data = ContentFile(decoded_file, name=complete_file_name)

        return super().to_internal_value(data)

    def get_file_extension(self, file_name, decoded_file, mime_type=None):
        file_extension = what(file_name, decoded_file)

        if not file_extension and mime_type:
            file_extension = mimetypes.guess_extension(mime_type)
        else:
            file_extension = '.%s' % file_extension

        return file_extension


class ApiBase64ImageField(ApiBase64FileField, serializers.ImageField):
    """
    A Django REST framework field for handling image-uploads through raw post data.
    It uses base64 for encoding and decoding the contents of the file.
    """

    def get_file_extension(self, file_name, decoded_file, mime_type=None):
        extension = super().get_file_extension(file_name, decoded_file, mime_type)
        extension = ".jpg" if extension == ".jpeg" else extension

        return extension


class ApiContactPictureField(ApiAbsoluteUrlMixin, ApiBase64ImageField):

    def to_representation(self, value):
        if settings.AWS_STORAGE_BUCKET_NAME:
            data = {
                'thumb': get_thumbnail_picture(value, 'micro'),
                'origin': get_thumbnail_picture(value, 'large'),
            }
        else:
            data = {
                'thumb': self.get_absolute(get_thumbnail_picture(value, 'micro')),
                'origin': self.get_absolute(get_thumbnail_picture(value, 'large')),
            }

        return data


class ApiChoicesField(serializers.ChoiceField):

    def __init__(self, choices, **kwargs):
        super().__init__(choices, **kwargs)

        self.choice_strings_to_values = {
            self._convert_to_text(key): key for key in self.choices.keys()
        }

    def _convert_to_text(self, val):
        if isinstance(val, timedelta):
            val = int(val.total_seconds())

        return six.text_type(val)

    def to_internal_value(self, data):
        if data == '' and self.allow_blank:
            return ''

        try:
            if type(data) != bool:
                data = int(float(data))
        except ValueError:
            if data in serializers.BooleanField.TRUE_VALUES:
                data = True
            elif data in serializers.BooleanField.FALSE_VALUES:
                data = False

        try:
            return self.choice_strings_to_values[six.text_type(data)]
        except (KeyError, ValueError):
            self.fail('invalid_choice', input=data)

    def to_representation(self, value):
        if value in ('', None):
            return value

        if isinstance(value, timedelta):
            return int(value.total_seconds())

        return self.choice_strings_to_values.get(six.text_type(value), value)


class EmptyNullField(serializers.Field):

    def run_validation(self, data=serializers.empty):
        if data is None:
            data = serializers.empty

        return super().run_validation(data)

    @classmethod
    def from_field(cls, field):
        field_class = field.__class__

        except_classes = (serializers.BooleanField,
                          serializers.NullBooleanField)
        if issubclass(field_class, except_classes):
            return serializers.NullBooleanField(*field._args, **field._kwargs)

        class Internal(cls, field_class):
            pass

        kwargs = copy.copy(field._kwargs)
        kwargs['allow_null'] = True

        return Internal(*field._args, **kwargs)
