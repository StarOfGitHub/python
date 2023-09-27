import requests

from django import forms


class MYOBKeysForm(forms.Form):
    key = forms.CharField(
        label='API Key',
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'c-field'})
    )

    secret = forms.CharField(
        label='API Secret',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'c-field'})
    )


class CompanyFileSignInForm(forms.Form):

    def __init__(self, *args, **kwargs):
        self.myob_client = kwargs.pop('myob_client', None)
        if self.myob_client is None:
            raise Exception("Provide MYOB client instance!")

        companies = kwargs.pop('companies', [])
        super(CompanyFileSignInForm, self).__init__(*args, **kwargs)

        choices = [(a.id, a.name) for a in companies]
        self.fields['company'].choices = [('', 'None')] + choices

    username = forms.CharField(
        label='Username',
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'c-field'})
    )

    password = forms.CharField(
        label='Password',
        max_length=100,
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'c-field'})
    )

    company = forms.ChoiceField(required=False)

    def clean(self):
        cleaned_data = super(CompanyFileSignInForm, self).clean()
        username = cleaned_data.get('username')
        password = cleaned_data.get('password')
        company_id = cleaned_data.get('company')
        if username:
            url = self.myob_client.get_cf_uri()
            cf_token = self.myob_client.encode_cf_token(username, password)
            headers = self.myob_client.get_headers()
            headers['x-myobapi-cftoken'] = cf_token
            # test if we can access company file.
            resp = requests.get(url, headers=headers)
            if resp.status_code != 200:
                raise forms.ValidationError('Could not sign in. Try again.')
            else:
                self.myob_client.set_attr('cf_token', cf_token)
                self.myob_client.persist(company_id)
