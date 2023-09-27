from collections import OrderedDict

from django.conf import settings
from django.utils.module_loading import import_string

from rest_framework.routers import DefaultRouter


class ApiRouter(DefaultRouter):

    base_endpoint_class = import_string(settings.DEFAULT_ENDPOINT_CLASS)

    def __init__(self, *args, **kwargs):
        self._endpoints = OrderedDict()
        self._registry = {}
        super().__init__(*args, **kwargs)

    def register(
        self, model=None, endpoint=None, fields=None, permission_classes=None, serializer=None, filter_class=None,
        read_only=False, viewset=None, search_fields=None, ordering_fields=None, base_viewset=None,
        base_name=None, base_serializer=None, **kwargs
    ):

        if endpoint is None or isinstance(endpoint, type):
            extra = {}
            if base_viewset is not None:
                extra['base_viewset'] = base_viewset
            if base_serializer is not None:
                extra['base_serializer'] = base_serializer

            endpoint_kwargs = {
                'model': model,
                'fields': fields,
                'permission_classes': permission_classes,
                'serializer': serializer,
                'filter_class': filter_class,
                'read_only': read_only,
                'viewset': viewset,
                'search_fields': search_fields,
                'ordering_fields': ordering_fields
            }
            endpoint_kwargs.update(extra)

        if endpoint is None:
            endpoint = self.base_endpoint_class(**endpoint_kwargs)
        elif isinstance(endpoint, type):
            endpoint = endpoint(**endpoint_kwargs)

        url = endpoint.get_url() if 'url' not in kwargs else kwargs.pop('url')
        self._endpoints[url] = endpoint

        if base_name is None:
            base_name = url

        replace_endpoint = kwargs.pop('replace', False)
        if replace_endpoint:
            for idx, (prefix, view, name) in enumerate(router.registry):
                if prefix == url:
                    del router.registry[idx]
                    break

        super().register(url, endpoint.get_viewset(), base_name=base_name, **kwargs)

    def get_endpoint(self, url):
        return self._endpoints[url]

    def registerViewSet(self, *args, **kwargs):
        super().register(*args, **kwargs)


router = import_string(settings.ROUTER_CLASS)()
