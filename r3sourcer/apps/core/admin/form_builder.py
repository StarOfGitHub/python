from django.contrib import admin

from easy_select2.widgets import SELECT2_WIDGET_JS, SELECT2_WIDGET_CSS
from polymorphic.admin import PolymorphicInlineSupportMixin, StackedPolymorphicInline

from ..forms import FormBuilderAdminForm
from .. import models


class FormFieldInline(StackedPolymorphicInline):

    class ModelFormFieldInline(StackedPolymorphicInline.Child):
        model = models.ModelFormField

    class SelectFormFieldInline(StackedPolymorphicInline.Child):
        model = models.SelectFormField

    class TextFormFieldInline(StackedPolymorphicInline.Child):
        model = models.TextFormField

    class TextAreaFormFieldInline(StackedPolymorphicInline.Child):
        model = models.TextAreaFormField

    class NumberFormFieldInline(StackedPolymorphicInline.Child):
        model = models.NumberFormField

    class DateFormFieldInline(StackedPolymorphicInline.Child):
        model = models.DateFormField

    class FileFormFieldInline(StackedPolymorphicInline.Child):
        model = models.FileFormField

    class CheckBoxFormFieldInline(StackedPolymorphicInline.Child):
        model = models.CheckBoxFormField

    class RadioButtonsFormFieldInline(StackedPolymorphicInline.Child):
        model = models.RadioButtonsFormField

    class ImageFormFieldInline(StackedPolymorphicInline.Child):
        model = models.ImageFormField

    class RelatedFormFieldInline(StackedPolymorphicInline.Child):
        model = models.RelatedFormField

    model = models.FormField

    child_inlines = (
        ModelFormFieldInline,
        SelectFormFieldInline,
        TextFormFieldInline,
        TextAreaFormFieldInline,
        NumberFormFieldInline,
        DateFormFieldInline,
        FileFormFieldInline,
        CheckBoxFormFieldInline,
        RadioButtonsFormFieldInline,
        ImageFormFieldInline,
        RelatedFormFieldInline
    )


class FormFieldGroupInLine(admin.StackedInline):

    fields = ('name', 'position')
    model = models.FormFieldGroup
    extra = 0


class FormFieldInLine(admin.StackedInline):

    fields = (('custom_field', 'model_field'), ('required', 'unique'), 'position')
    model = models.FormField
    extra = 0


class FormLanguageInline(admin.TabularInline):
    model = models.FormLanguage
    extra = 0


class FormAdmin(admin.ModelAdmin):

    list_display = ('builder', 'company')
    inlines = [FormFieldGroupInLine, FormLanguageInline]


class FormBuilderAdmin(admin.ModelAdmin):

    form = FormBuilderAdminForm

    class Media:
        css = SELECT2_WIDGET_CSS
        js = SELECT2_WIDGET_JS


class FormFieldGroupAdmin(PolymorphicInlineSupportMixin, admin.ModelAdmin):
    list_display = ('name', 'form', 'company')
    list_filter = ('form',)

    inlines = [FormFieldInline]

    @classmethod
    def company(cls, obj):
        return obj.form.company


admin.site.register(models.FormBuilder, FormBuilderAdmin)
admin.site.register(models.FormFieldGroup, FormFieldGroupAdmin)
admin.site.register(models.Form, FormAdmin)
admin.site.register(models.FormBuilderExtraFields, admin.ModelAdmin)
