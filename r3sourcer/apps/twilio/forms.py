import json

from django.utils.translation import ugettext_lazy as _
from django.conf import settings
from django import forms


class SMSForm(forms.Form):
    """
    SMS form for modal dialog
    """

    body = forms.CharField(widget=forms.Textarea(), label=_("Text"))
    params = forms.CharField(widget=forms.HiddenInput())

    def clean_params(self):
        params = self.cleaned_data['params']
        try:
            params = json.loads(params)
        except:
            params = {}
        return params
