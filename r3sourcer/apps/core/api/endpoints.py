from django.conf import settings
from django.utils.module_loading import import_string

from inflector import Inflector
from rest_framework import viewsets

from r3sourcer.apps.core_adapter.factories import serializer_factory, viewset_factory


def get_all_field_names(model):
    return [
        field.name for field in model._meta.get_fields()
        if not hasattr(field, 'field') or getattr(field, 'related_name', None) is not None
    ]


class ApiEndpoint:

    base_serializer = import_string(settings.BASE_SERIALIZER)
    base_viewset = import_string(settings.BASE_VIEWSET)
    base_readonly_viewset = import_string(settings.BASE_READONLY_VIEWSET)

    model = None
    fields = None
    serializer = None
    serializer_fields = None

    permission_classes = None
    filter_class = None
    search_fields = None
    ordering_fields = None
    viewset = None

    read_only = False
    include_str = True

    inflector_language = import_string(settings.INFLECTOR_LANGUAGE)

    _translated_fields = None
    _translated_field_names = None
    _default_language_field_names = None

    def __init__(self, model=None, **kwargs):
        self.inflector = Inflector(self.inflector_language)

        if model is not None:
            self.model = model

        arg_names = (
            'fields', 'serializer', 'permission_classes', 'filter_class', 'search_fields', 'viewset', 'read_only',
            'include_str', 'ordering_fields', 'base_viewset', 'base_serializer'
        )
        for arg_name in arg_names:
            setattr(self, arg_name, kwargs.pop(arg_name, getattr(self, arg_name, None)))

        if len(kwargs.keys()) > 0:
            raise Exception('{} got an unexpected keyword argument: "{}"'.format(
                self.__class__.__name__, list(kwargs.keys())[0]
            ))

        if self.serializer is not None:
            assert self.fields is None, 'You cannot specify both fields and serializer'
        else:
            assert self.viewset is not None or self.model is not None, \
                'You need to specify at least a model or a viewset'
            self.get_serializer()

        if self.viewset is not None:
            for attr in ('permission_classes', 'filter_class', 'search_fields', 'ordering_fields'):
                assert getattr(self, attr, None) is None, 'You cannot specify both {} and viewset'.format(attr)
        else:
            self.get_viewset()

        if self.model is None:
            self.model = self.get_serializer().Meta.model

    @property
    def singular_model_name(self):
        return self.model._meta.model_name.lower()

    @property
    def model_name(self):
        return self.inflector.pluralize(self.singular_model_name)

    @property
    def application_name(self):
        return self.model._meta.app_label.lower()

    def get_serializer_fields(self):
        if self.serializer_fields is None:
            self.serializer_fields = self.get_fields_for_serializer()

        return self.serializer_fields

    def get_fields_for_serializer(self):
        if self.fields is None:
            if self.serializer_fields is None:
                self.fields = tuple(f for f in get_all_field_names(self.model))
                if self.include_str:
                    self.fields += ('__str__', )
            else:
                self.fields = tuple(f for f in self.serializer_fields if not isinstance(f, (list, dict)))

        return self.fields

    def get_serializer(self, data=None):
        if self.serializer is None:
            if self.viewset is None:
                self.serializer = serializer_factory(self)
            else:
                self.serializer = self.viewset.serializer_class

        if data is None:
            return self.serializer

        return self.serializer(data)

    def get_base_viewset(self):
        return self.base_viewset if not self.read_only or self.base_viewset != viewsets.ModelViewSet \
            else self.base_readonly_viewset

    def get_viewset(self):
        if self.viewset is None:
            self.viewset = viewset_factory(self)
        elif not hasattr(self.viewset, 'endpoint'):
            self.viewset.endpoint = self

        return self.viewset

    def get_url(self):
        return '{}/{}'.format(
            self.application_name.replace('_', '-'),
            self.model_name.replace('_', '-')
        )
