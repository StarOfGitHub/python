import logging

import requests

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render

from r3sourcer.apps.core.models import Company

from . api.wrapper import MYOBAuth
from . api.wrapper import MYOBClient
from . api.forms import CompanyFileSignInForm, MYOBKeysForm


log = logging.getLogger(__name__)


@login_required
def index(request):
    postfix = '_ssl' if request.is_secure() else ''
    initial_keys = {
        'key': settings.MYOB_APP['api_key{}'.format(postfix)],
        'secret': settings.MYOB_APP['api_secret{}'.format(postfix)]
    }
    context = {
        'title': 'MYOB Sign In',
        'signin_url': reverse('myob:signin'),
        'form': MYOBKeysForm(initial=initial_keys)
    }
    return render(request, 'myob/index.html', context)


@login_required
def signin(request):
    app_info = None
    if request.method == 'POST':
        form = MYOBKeysForm(request.POST)
        if form.is_valid():
            app_info = {
                'api_key': form.cleaned_data['key'],
                'api_secret': form.cleaned_data['secret']
            }

            request.session['app_info'] = app_info
            request.session.save()

    auth_client = MYOBAuth(request, app_info=app_info)
    myob_signin_url = auth_client.get_myob_signin_url()
    return HttpResponseRedirect(myob_signin_url)


@login_required
def authorized(request):
    auth_client = MYOBAuth(request)
    auth_client.retrieve_access_code()
    auth_client.retrieve_access_token()

    url = reverse('myob:cf_list')
    return HttpResponseRedirect(url)


@login_required
def cf_list(request):
    client = MYOBClient(request)

    resp = client.get_company_files()
    data = resp.json()

    for i in range(len(data)):
        data[i]['signin_url'] = reverse('myob:cf_signin', kwargs={
            'cf_id': data[i]['Id']
        })

    context = {
        'title': 'MYOB Company Files',
        'request': request,
        'cf_list': data,
    }
    return render(request, 'myob/cf_list.html', context)


@login_required
def cf_signin(request, cf_id):
    client = MYOBClient(request)

    resp = client.get_company_files()
    data = resp.json()

    cf = None
    for i in range(len(data)):
        if data[i]['Id'] == cf_id:
            cf = data[i]
            break
    if cf is None:
        url = reverse('myob:cf_list')
        return HttpResponseRedirect(url)

    client.set_company_file(cf)

    companies = Company.objects.filter(myobcompanyfiletoken__isnull=True)
    if request.method == 'POST':
        f = CompanyFileSignInForm(request.POST,
                                  myob_client=client,
                                  companies=companies)
        if f.is_valid():
            # NOTE: form validation sets cf_token and persist data!
            return HttpResponseRedirect(reverse('myob:cf_authorized'))
    else:
        f = CompanyFileSignInForm(myob_client=client, companies=companies)

    cf['signin_url'] = reverse('myob:cf_signin', kwargs={'cf_id': cf['Id']})

    context = {
        'title': 'MYOB Company File Sign In',
        'form': f,
        'cf': cf,
        'cf_list_url': reverse('myob:cf_list'),
    }
    return render(request, 'myob/cf_signin.html', context)


@login_required
def cf_authorized(request):
    client = MYOBClient(request)
    cf_uri = client.get_cf_uri()
    headers = client.get_headers()

    resp = requests.get(cf_uri, headers=headers)
    data = resp.json()

    context = {
        'title': "MYOB API",
        'raw_json': data,
        'CompanyFile': data['CompanyFile'],
        'Resources': data['Resources'],
    }
    return render(request, 'myob/cf_api.html', context)
