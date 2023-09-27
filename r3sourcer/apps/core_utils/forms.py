from django import forms
from django.contrib.admin.widgets import AdminDateWidget


class DateRangeBaseForm(forms.Form):
    def __init__(self, request, *args, **kwargs):
        super(DateRangeBaseForm, self).__init__(*args, **kwargs)
        self.request = request


class DateCondRangeForm(DateRangeBaseForm):
    def __init__(self, *args, **kwargs):
        field_name = kwargs.pop('field_name')
        suffix = kwargs.pop('suffix', '')

        self.from_field_name = '%s%s__gte' % (field_name, suffix)
        self.to_field_name = '%s%s__lte' % (field_name, suffix)

        super(DateCondRangeForm, self).__init__(*args, **kwargs)

        self.fields[self.from_field_name] = forms.DateField(
            label='',
            widget=AdminDateWidget(
                attrs={'placeholder': 'From date'}
            ),
            localize=True,
            required=False
        )
        self.fields[self.to_field_name] = forms.DateField(
            label='',
            widget=AdminDateWidget(
                attrs={'placeholder': 'To date'}
            ),
            localize=True,
            required=False
        )
