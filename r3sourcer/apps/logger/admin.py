from django.apps import apps
from django.conf import settings
from django.conf.urls import url
from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.admin.utils import unquote
from django.shortcuts import render
from django.utils.encoding import force_text
from django.utils.text import capfirst
from django.utils.translation import ugettext as _

from .main import endless_logger


class LoggerMixin(object):
    change_form_template = 'admin/change_form_with_log.html'
    change_list_template = 'admin/change_list_with_log.html'

    def get_urls(self):
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        my_urls = [
            url(r'^(.+)/log_history/$',
                self.admin_site.admin_view(self.log_history_view),
                name='%s_%s_log_history' % info),
        ]
        return my_urls + urls

    def log_history_view(self, request, object_id):
        model = self.model
        obj = self.get_object(request, unquote(object_id))
        opts = model._meta
        action_list = endless_logger.get_object_history(model,
                                                        object_id=object_id)

        context = dict(
            self.admin_site.each_context(request),
            title=_('Log history: %s') % force_text(obj),
            action_list=action_list,
            module_name=capfirst(force_text(opts.verbose_name_plural)),
            object=obj,
            opts=opts,
            preserved_filters=self.get_preserved_filters(request),
        )
        return render(request, "admin/log_history.html", context)


def logger_view(request):
    model_name = request.GET.get('model_name', None)
    from_date = request.GET.get('from', None)
    to_date = request.GET.get('to', None)
    model_list = []
    for model in apps.get_models():
        if hasattr(model, "use_logger") and getattr(model, "use_logger")():
            model_list.append('{}.{}'.format(model._meta.app_label,
                                             model.__name__).lower())

    context = dict(
        title=_('Log history'),
        model_list=model_list,
        from_date=from_date,
        to_date=to_date,
        selected_model=model_name,
        stuff_url_prefix=settings.DJANGO_STUFF_URL_PREFIX
    )
    return render(request, "admin/log_history_list_view.html", context)


class LoggerAdminSite(AdminSite):
    def get_urls(self):
        from django.conf.urls import url
        my_urls = [
            url(r'^logger/$', admin.site.admin_view(logger_view), name='log_history_list_view')
        ]
        return my_urls

admin_logger = LoggerAdminSite()
