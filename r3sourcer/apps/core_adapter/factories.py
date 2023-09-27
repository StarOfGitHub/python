from six import string_types

from django.core.exceptions import FieldDoesNotExist
from django.db.models.fields import NOT_PROVIDED
from django.db.models.fields.reverse_related import ManyToOneRel, OneToOneRel

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers, filters


class NullToDefaultMixin(object):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.Meta.fields:
            try:
                model_field = self.Meta.model._meta.get_field(field)
                if hasattr(model_field, 'default') and model_field.default != NOT_PROVIDED:
                    self.fields[field].allow_null = True
            except FieldDoesNotExist:
                pass

    def validate(self, data):
        for field in self.Meta.fields:
            try:
                model_field = self.Meta.model._meta.get_field(field)
                if hasattr(model_field, 'default') and model_field.default != NOT_PROVIDED and \
                        data.get(field, NOT_PROVIDED) is None:
                    data.pop(field)
            except FieldDoesNotExist:
                pass

        return data


def serializer_factory(endpoint):
    meta_attrs = {
        'model': endpoint.model,
        'fields': endpoint.get_serializer_fields()
    }
    meta_parents = (object, )
    if hasattr(endpoint.base_serializer, 'Meta'):
        meta_parents = (endpoint.base_serializer.Meta, ) + meta_parents

    Meta = type('Meta', meta_parents, meta_attrs)

    cls_name = '{}Serializer'.format(endpoint.model.__name__)
    cls_attrs = {
        'Meta': Meta,
    }

    for meta_field in meta_attrs['fields']:
        if not isinstance(meta_field, string_types) or meta_field == '__all__':
            continue

        try:
            model_field = endpoint.model._meta.get_field(meta_field)
            if isinstance(model_field, OneToOneRel):
                cls_attrs[meta_field] = serializers.PrimaryKeyRelatedField(read_only=True)
            elif isinstance(model_field, ManyToOneRel):
                cls_attrs[meta_field] = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
        except FieldDoesNotExist:
            cls_attrs[meta_field] = serializers.ReadOnlyField()

    return type(cls_name, (NullToDefaultMixin, endpoint.base_serializer, ), cls_attrs)


def viewset_factory(endpoint):
    base_viewset = endpoint.get_base_viewset()

    cls_name = '{}ViewSet'.format(endpoint.model.__name__)
    tmp_cls_attrs = {
        'serializer_class': endpoint.get_serializer(),
        'queryset': endpoint.model.objects.all(),
        'endpoint': endpoint,
        '__doc__': base_viewset.__doc__
    }

    cls_attrs = {
        key: value for key, value in tmp_cls_attrs.items()
        if key == '__doc__' or getattr(base_viewset, key, None) is None
    }

    if endpoint.permission_classes is not None:
        cls_attrs['permission_classes'] = endpoint.permission_classes

    filter_backends = list(getattr(base_viewset, 'filter_backends', []))

    for filter_type, backend in (
        ('filter_class', DjangoFilterBackend),
        ('search_fields', filters.SearchFilter),
        ('ordering_fields', filters.OrderingFilter),
    ):
        if getattr(endpoint, filter_type, None) is not None:
            filter_backends.append(backend)
            cls_attrs[filter_type] = getattr(endpoint, filter_type)

    if len(filter_backends) > 0:
        cls_attrs['filter_backends'] = filter_backends

    rv = type(cls_name, (base_viewset,), cls_attrs)

    return rv
