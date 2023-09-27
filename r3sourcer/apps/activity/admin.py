import uuid

from django.contrib import admin, messages
from django.urls import reverse
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _

from r3sourcer.apps.activity.filters import (
    ActivityTypeFilter,
    OnlyMyActivityFilter,
    make_actuality_filter,
)
from r3sourcer.apps.activity.models import (
    Activity,
    ActivityDate,
    ActivityRepeat,
    ActivityTemplate,
)
from r3sourcer.apps.core.admin import MessageTemplateAdmin
from r3sourcer.apps.core_utils import admin_helpers
from r3sourcer.apps.core_utils.filters import (
    DatePeriodRangeAdminFilter,
    RelatedDropDownFilter,
)
from r3sourcer.apps.core_utils.mixins import RelatedFieldMixin


class GeneralActivityMixin(RelatedFieldMixin):

    PRIORITY_ICONS = {
        5: 'arrow-up',
        4: 'chevron-up',
        3: 'chevron-right',
        2: 'chevron-down',
        1: 'arrow-down'
    }
    ct_field = "activity_type"
    ct_fk_field = "related_entity_id"

    list_display = ('get_priority', 'get_subject', 'starts_at', 'ends_at', 'get_duration')

    list_display_links = ('get_subject',)

    list_filter = (('starts_at', DatePeriodRangeAdminFilter),
                   ('ends_at', DatePeriodRangeAdminFilter),
                   ActivityTypeFilter, OnlyMyActivityFilter,
                   'done', 'priority',
                   ('contact', RelatedDropDownFilter),
                   make_actuality_filter('starts_at__date', 'ends_at__date', _("Actuality")),
                   )

    search_fields = ('text', 'contact__first_name', 'contact__last_name', 'contact__phone_mobile',
                     'contact__email')

    readonly_fields = ('contact', 'get_priority')

    def get_activity_type(self, obj):
        return mark_safe('<b>{}</b>'.format(obj.get_activity_type_display()))
    get_activity_type.short_description = _("Activity type")

    def get_overdue(self, obj):
        return obj.get_overdue()

    def get_subject(self, obj):
        return obj.template.subject_template
    get_subject.short_description = _("Subject")

    def get_priority(self, obj):
        return mark_safe('<span class="fa fa-{}"></span>'.format(self.PRIORITY_ICONS.get(obj.priority)))
    get_priority.short_description = mark_safe("<i class='fa fa-arrow-up'></i>")

    def get_reminders(self, obj):
        reminders_list = obj.get_reminders()
        result_html_list = []
        for reminder in reminders_list:
            result_html_list.append(str(reminder))
        return "<br/>".join(result_html_list) or "-"
    get_reminders.allow_tags = True

    def get_related_entity(self, obj):
        """ Return entity object link or `-` """
        entity = obj.get_related_entity()
        if entity:
            try:
                admin_url = reverse('admin:{}_{}_change'.format(entity._meta.app_label, entity._meta.model_name),
                                    args=[entity.id])
            except:
                admin_url = 'javascript:void(0);'
            return "<a href='{}'><b>{}</a>".format(admin_url, str(entity))
        return '-'

    get_related_entity.short_description = _("Related entity")
    get_related_entity.allow_tags = _("Related entity")

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['repeat_url'] = '{}?activity_id={}'.format(
                reverse('admin:{}_{}_add'.format(ActivityRepeat._meta.app_label,
                                                 ActivityRepeat._meta.model_name)),
                object_id
        )
        return super(GeneralActivityMixin, self).change_view(request,
                                                             object_id,
                                                             form_url=form_url,
                                                             extra_context=extra_context)


class AdminChangeListConditionsModel(admin.ModelAdmin):

    conditions = ()

    def get_conditions(self):
        return self.conditions

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['extra_conditions'] = self.get_conditions()
        return super(AdminChangeListConditionsModel, self).changelist_view(request, extra_context=extra_context)


class InvolvedContactInline(admin.TabularInline):
    """ Inline involved contacts """

    model = Activity.involved_contacts.through
    # template = 'admin/activity/activity/tabular.html'
    show_change_link = False
    can_delete = True
    extra = 0
    verbose_name = _("Involved contact")
    verbose_name_plural = _("Involved contacts")

    # @staticmethod
    # def get_contact_name(obj):
    #
    #     cc = obj.client_contact.first()
    #     if cc:
    #         return cc
    #
    #     ac = obj.account_contact.first()
    #     if ac:
    #         return ac
    #
    #     try:
    #         rc = obj.recruitee_contacts
    #     except Exception as e:
    #         pass
    #     else:
    #         if rc.recruitee_subcontractors.exists():
    #             return '{} {}'.format(rc.recruitee_subcontractors.first(), str(obj))
    #     return str(obj)

    def get_formset(self, request, obj=None, **kwargs):
        formset = super(InvolvedContactInline, self).get_formset(request, obj=obj, **kwargs)
        formset.form.base_fields['contact'].widget.can_change_related = False
        formset.form.base_fields['contact'].widget.attrs['class'] = 'dropdown-field'
        # formset.form.base_fields['contact'].label_from_instance = self.get_contact_name
        return formset


class ActivityAdmin(GeneralActivityMixin, AdminChangeListConditionsModel):

    conditions = (
        ('priority', 5, 'priority-level-top'),
        ('priority', 4, 'priority-level-high'),
        ('priority', 3, 'priority-level-normal'),
        ('priority', 2, 'priority-level-low'),
        ('priority', 1, 'priority-level-bottom'),
        ('get_overdue', True, 'overdue-activity'),
        ('done', True, 'done-activity')
    )

    fieldsets = (
        (_("Details"), {
            'fields': [
                'priority', ('get_related_entity',),
                'template',
                'entity_object',
                ('starts_at', 'ends_at')]
        }),

        (_("Other"), {
             'classes': ('collapse', ),
             'fields': ['contact', 'done']
        }),
    )

    readonly_fields = ('entity_object_name', 'entity_object_id', 'get_related_entity', 'entity_object')

    inlines = [InvolvedContactInline]

    def get_related_entity(self, obj):
        """ Return entity object link or `-` """
        entity = obj.get_related_entity()
        if entity:
            try:
                admin_url = reverse('admin:{}_{}_change'.format(entity._meta.app_label, entity._meta.model_name),
                                    args=[entity.id])
            except:
                admin_url = 'javascript:void(0);'
            return mark_safe("<a href='{}'><b>{}</a>".format(admin_url, str(entity)))
        return '-'

    get_related_entity.short_description = _("Related entity")

    actions = ['make_as_done']

    def make_as_done(self, request, queryset):
        qs = queryset.update(done=True)
        messages.success(request, _('%s activities was successfully updated' % qs))

    class Media:
        css = {
             'all': ('font-awesome/css/font-awesome.css',)
        }


class ActivityDateAdmin(admin.ModelAdmin):

    readonly_fields = ('activity', 'occur_at', 'activity_repeat', 'status', 'error_text')


class ActivityDateInlineAdmin(admin.TabularInline):

    model = ActivityDate
    extra = 0
    ordering = ['occur_at']
    fieldsets = (
        (_("Main"), {
            'fields': ['occur_at', 'get_status', 'get_details', 'activity']
        }),
    )

    readonly_fields = ('activity', 'get_status', 'get_details')

    def get_details(self, obj):
        if not obj._state.adding:
            url = admin_helpers.get_instance_admin_url(obj, as_url=True)
            return mark_safe(
                '<a href="{}"><i class="fa fa-pencil" aria-hidden="true"></i></a>'.format(url)
            )
        return '-'
    get_details.short_description = _("Details")

    def get_status(self, obj):
        statuses = ActivityDate.STATUS_CHOICES
        if obj.status == statuses.WAITING:
            css_cls = 'fa-clock-o grey-icon'
        elif obj.status == statuses.OCCURRED:
            css_cls = 'fa-check-circle green-icon'
        else:
            css_cls = 'fa-times-circle red-icon'
        return mark_safe('<i class="fa {}" aria-hidden="true"></i>'.format(css_cls))
    get_status.short_description = _("Status")


class ActivityRepeatAdmin(admin.ModelAdmin):
    fieldsets = (
        (_("Main"), {
            'fields': ['activity', 'repeat_type', 'base_type', 'started_at',
                       ('get_enabled', 'get_occurred_activity_count')]
        }),
        (_("Interval"), {
            'fields': ['every']
        }),
        (_("Schedule"), {
            'fields': ['month_of_year', 'day_of_month', 'day_of_week', 'hour',
                       'minute']
        }),
    )

    readonly_fields = ('get_occurred_activity_count', 'get_enabled', )

    inlines = [
        ActivityDateInlineAdmin
    ]

    def get_occurred_activity_count(self, obj):
        if obj:
            return obj.occurred_activities.count()
    get_occurred_activity_count.short_description = _("Activity count")

    def get_enabled(self, obj):
        # TODO: is enabled?
        # if obj and obj.periodic_task:
        #     return obj.periodic_task.enabled
        return obj is not None
    get_enabled.boolean = True
    get_enabled.short_description = _("Running")

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = super(ActivityRepeatAdmin, self).get_readonly_fields(request, obj=obj)
        if obj:
            readonly_fields += ('activity',)
        return readonly_fields

    def get_form(self, request, obj=None, **kwargs):
        form = super(ActivityRepeatAdmin, self).get_form(request, obj=obj, **kwargs)
        if not obj:
            try:
                activity_id = uuid.UUID(request.GET.get('activity_id', ''))
            except:
                raise Http404
            form.base_fields['activity'].initial = get_object_or_404(Activity, pk=activity_id)
            form.base_fields['activity'].queryset = Activity.objects.filter(pk=activity_id)
        return form

    def get_urls(self):
        from django.conf.urls import url
        from functools import update_wrapper

        def wrap(view):
            def wrapper(*args, **kwargs):
                return self.admin_site.admin_view(view)(*args, **kwargs)
            wrapper.model_admin = self
            return update_wrapper(wrapper, view)

        info = self.model._meta.app_label, self.model._meta.model_name

        urlpatterns = [
                          url(r'^(.+)/enabled/(0|1)/$', wrap(self.update_enabled_view), name='%s_%s_change_enabled' % info)
                      ] + super(ActivityRepeatAdmin, self).get_urls()
        return urlpatterns

    def update_enabled_view(self, request, object_id, enabled, *args, **kwargs):
        info = self.model._meta.app_label, self.model._meta.model_name
        enabled_value = int(enabled)

        instance = self.get_object(request, object_id)

        if instance:
            if enabled_value:
                instance.activate()
                message = _("Activity repeat activated")
            else:
                instance.deactivate()
                message = _("Activity repeat deactivated")

            self.message_user(request, message)
            return HttpResponseRedirect(reverse('admin:%s_%s_change' % info, args=[instance.id]))
        raise Http404


admin.site.register(Activity, ActivityAdmin)
admin.site.register(ActivityTemplate, MessageTemplateAdmin)
admin.site.register(ActivityRepeat, ActivityRepeatAdmin)
admin.site.register(ActivityDate, ActivityDateAdmin)
