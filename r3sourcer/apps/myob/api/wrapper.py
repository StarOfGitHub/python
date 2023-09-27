# coding: utf-8

import base64
import datetime
import decimal
import json
import logging
import re
import time

import pytz
import requests
from django.conf import settings
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _
from rest_framework import status

from r3sourcer.apps.core.models import Company
from r3sourcer.apps.myob.api.utils import get_myob_app_info
from r3sourcer.apps.myob.models import MYOBRequestLog, MYOBCompanyFileToken, MYOBCompanyFile
from r3sourcer.apps.myob.services.exceptions import MyOBCredentialException, MYOBException, MYOBProgrammingException, \
    MYOBImplementationException, MYOBServerException
from r3sourcer.helpers.datetimes import utc_now

log = logging.getLogger(__name__)


def check_account_id(url1, url2):
    pattern = '^(?P<protocol>\w+)\:\/\/(?P<domain_name>[\w,\d,\.]+)\/' \
              'accountright\/(?P<account_id>[\d,\w\-]+)(?P<path>.+)?'
    return re.match(pattern, url1).groupdict()['account_id'] == re.match(pattern, url2).groupdict()['account_id']


def decimal_default(obj):
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    raise TypeError


def myob_request(method, url, **kwargs):
    """
    This function makes requests to MYOB API
    """
    retry = kwargs.pop('retry', 0)

    method = method.lower()
    if method not in ('get', 'put', 'post', 'delete'):
        msg = 'request method "{}" is not supported'.format(method)
        raise MYOBProgrammingException(msg)
    request = getattr(requests, method)

    log_kw = {}
    headers = kwargs.get('headers')
    if headers is not None:
        log_kw['headers'] = json.dumps(headers)
    data = kwargs.get('data')
    if data is not None:
        log_kw['data'] = json.dumps(data, default=decimal_default)
    json_ = kwargs.get('json')
    if json_ is not None:
        log_kw['json'] = json.dumps(json_, default=decimal_default)
    params = kwargs.get('params')
    if params is not None:
        log_kw['params'] = json.dumps(params, default=decimal_default)

    req_log = MYOBRequestLog.objects.create(method=method, url=url, **log_kw)

    if json_:
        kwargs['json'] = None
        kwargs['data'] = json.dumps(json_, default=decimal_default)
    resp = request(url, **kwargs)

    req_log.resp_status_code = resp.status_code
    req_log.resp_content = resp.content
    try:
        if int(resp.headers.get('content-length', 0)) > 0:
            req_log.resp_json = resp.json(parse_float=decimal.Decimal)
    except ValueError as e:
        log.info('{}'.format(e))
    req_log.save()

    if retry >= 3 and resp.status_code >= 500:
        raise MYOBServerException(resp.text)

    if resp.status_code == 403 and 'over qps' in resp.text.lower():
        log.warning('MYOB server response: %s. Resend request in 1 sec',
                    resp.text)
        time.sleep(1)
        return myob_request(method, url, **kwargs)
    elif resp.status_code >= 500:
        # TODO: review this behaviour
        log.warning('MYOB server returns %s error. Resend request in 3 sec...',
                    resp.status_code)
        time.sleep(3)
        return myob_request(method, url, retry=retry+1, **kwargs)

    return resp


class MYOBAuth(object):
    """
    This class is responsible for authentication in MYOB API using session data or token object.
    If you want to create an instance you have to pass a request or instance of MYOBAuthData to the class constructor
    It also creates MYOBAuthData which contains information needed for further requests to MYOB.
    It does it not obviously in persist() method and this method can be called at the end of every operation.
    """
    MYOB_AUTH_URL = 'https://secure.myob.com/oauth2/account/authorize'
    MYOB_TOKEN_URL = 'https://secure.myob.com/oauth2/v1/authorize'
    MYOB_ACCOUNT_URL = 'https://secure.myob.com/oauth2/account/'

    def __init__(self, request=None, auth_data=None, app_info=None):
        """
        request - django request object
        auth_data - instance of MYOBAuthData model
        app_info - dict with keys 'api_key' and 'api_secret'
        """
        if not request and not auth_data:
            raise MYOBProgrammingException('provide request or auth_data')

        self.request = request      # use and save request.session values
        self.auth_data = auth_data  # persisted values to MYOBAuthData
        self.auth_vars = {}         # some secret values are not persisted

        if app_info:
            self.app_info = app_info
        elif self.auth_data:
            self.app_info = {
                'api_key': self.auth_data.client_id,
                'api_secret': self.auth_data.client_secret
            }
        elif self.request:
            self.app_info = request.session.get('app_info')

        if not self.app_info:
            self.app_info = get_myob_app_info()

    def get_auth_url(self):
        return self.MYOB_AUTH_URL

    def get_token_url(self):
        return self.MYOB_TOKEN_URL

    def get_account_url(self):
        return self.MYOB_ACCOUNT_URL

    def get_redirect_uri(self):
        url = reverse('myob:authorized')
        if self.request is not None:
            url = self.request.build_absolute_uri(url)
        return url

    def get_myob_signin_url(self, state=None):
        params = {
            'scope': 'CompanyFile',
            'response_type': 'code',
            'client_id': self.get_api_key(),
            'redirect_uri': self.get_redirect_uri(),
        }
        if state is None:
            # could use oauth2 state param more properly
            params['state'] = str(utc_now().timestamp())
        url = self.get_auth_url()
        req = requests.Request(method="GET", url=url, params=params)
        return req.prepare().url

    def get_api_key(self):
        return self.app_info['api_key']

    def get_api_secret(self):
        return self.app_info['api_secret']

    def get_access_code(self):
        if self.request and 'myob_access_code' in self.request.session:
            return self.request.session.get('myob_access_code')
        if self.auth_vars.get('access_code') is not None:
            return self.auth_vars['access_code']
        raise MYOBProgrammingException('access code not set')

    def get_access_token(self):
        if self.request and 'myob_access_token' in self.request.session:
            return self.request.session.get('myob_access_token')
        if self.auth_vars.get('access_token') is not None:
            return self.auth_vars['access_token']
        if self.auth_data:
            return self.auth_data.access_token
        raise MYOBProgrammingException('access token not set')

    def get_refresh_token(self):
        if self.request and 'myob_refresh_token' in self.request.session:
            return self.request.session.get('myob_refresh_token')
        if self.auth_vars.get('refresh_token') is not None:
            return self.auth_vars['refresh_token']
        if self.auth_data:
            return self.auth_data.refresh_token
        raise MYOBProgrammingException('refresh token not set')

    def get_user_uid(self):
        if self.request and 'myob_user_uid' in self.request.session:
            return self.request.session.get('myob_user_uid')
        if self.auth_vars.get('user_uid') is not None:
            return self.auth_vars['user_uid']
        if self.auth_data:
            return self.auth_data.myob_user_uid
        raise MYOBProgrammingException('user uid not set')

    def get_user_username(self):
        if self.request and 'myob_user_username' in self.request.session:
            return self.request.session.get('myob_user_username')
        if self.auth_vars.get('user_username') is not None:
            return self.auth_vars['user_username']
        if self.auth_data:
            return self.auth_data.myob_user_username
        raise MYOBProgrammingException('user uid not set')

    def get_expires_in(self):
        if self.request and 'myob_expires_in' in self.request.session:
            return self.request.session.get('myob_expires_in')
        if self.auth_vars.get('expires_in') is not None:
            return self.auth_vars['expires_in']
        if self.auth_data:
            return self.auth_data.expires_in
        raise MYOBProgrammingException('expires in not set')

    def get_expires_at(self):
        if self.request and 'myob_expires_at' in self.request.session:
            expires_at = self.request.session.get('myob_expires_at')
            expires_at = datetime.datetime.strptime(
                expires_at, '%Y-%m-%d %H:%M:%S'
            )
            return pytz.timezone(settings.TIME_ZONE).localize(expires_at)
        if self.auth_vars.get('expires_at') is not None:
            expires_at = self.auth_vars['expires_at']
            expires_at = datetime.datetime.strptime(
                expires_at, '%Y-%m-%d %H:%M:%S'
            )
            return pytz.timezone(settings.TIME_ZONE).localize(expires_at)
        if self.auth_data:
            return self.auth_data.expires_at
        raise MYOBProgrammingException('expires in not set')

    def set_attr(self, attr, value, persist=False):
        session_attr = 'myob_' + attr
        if self.request:
            self.request.session[session_attr] = value
        if self.auth_data:
            if attr in ('access_token', 'refresh_token', 'expires_in'):
                setattr(self.auth_data, attr, value)
            elif attr in ('user_uid', 'user_username'):
                setattr(self.auth_data, session_attr, value)
            elif attr in ('expires_at'):
                value_modified = datetime.datetime.strptime(
                    value, '%Y-%m-%d %H:%M:%S'
                )
                setattr(self.auth_data, attr, value_modified)
        self.auth_vars[attr] = value
        if persist:
            self.persist()

    def retrieve_access_code(self):
        if not self.request:
            raise MYOBProgrammingException('request not set')
        access_code = self.request.GET.get('code')  # code!
        if access_code is None:
            raise MYOBProgrammingException('access_code not provided')
        self.set_attr('access_code', access_code)
        return access_code

    def retrieve_access_token(self, data=None):
        if not data:
            data = {
                'client_id': self.get_api_key(),
                'client_secret': self.get_api_secret(),
                'scope': 'CompanyFile',
                'code': self.get_access_code(),
                'redirect_uri': self.get_redirect_uri(),
                'grant_type': 'authorization_code'
            }

        url = self.get_token_url()
        resp = myob_request('post', url, data=data)
        log.info('%s %s', resp.status_code, resp.content)

        if resp.status_code != status.HTTP_200_OK:
            raise MYOBImplementationException('MYOB API returned %s status code: %s' % (resp.status_code, resp.content))

        resp_data = resp.json(parse_float=decimal.Decimal)
        return resp_data

    def refresh_access_token(self, data=None):
        if not data:
            data = {
                'client_id': self.get_api_key(),
                'client_secret': self.get_api_secret(),
                'refresh_token': self.get_refresh_token(),
                'grant_type': 'refresh_token'
            }

        url = self.get_token_url()
        resp = myob_request('post', url, data=data)
        log.info('%s %s', resp.status_code, resp.content)

        resp_data = resp.json(parse_float=decimal.Decimal)
        expires_at = int(resp_data['expires_in'])  # value in seconds
        self.auth_data.access_token = resp_data['access_token']
        self.auth_data.refresh_token = resp_data['refresh_token']
        self.auth_data.expires_in = resp_data['expires_in']
        self.auth_data.expires_at = utc_now() + datetime.timedelta(seconds=expires_at)
        self.auth_data.save()
        return resp


class MYOBClient(object):
    """
    Main client class for accessing MYOB API.
    """
    MYOB_API_URL = 'https://api.myob.com/accountright/'

    def __init__(self, request=None, cf_data=None, auth_data=None):
        if not any((request, cf_data, auth_data)):
            raise MYOBProgrammingException('provide request, or instance of MYOBAuthData or MYOBCompanyFileToken')

        if not auth_data:
            auth_data = cf_data.auth_data if cf_data else None
        if not cf_data:
            cf_data = auth_data.company_file_token.first()

        self.request = request
        self.cftoken = None
        self.cf_data = cf_data
        self.cf_vars = {}
        self.api = None  # needs custom initalization

        self.auth = MYOBAuth(request=request, auth_data=auth_data)

    def get_accounts(self, company_file, company_file_token):
        _url = company_file.cf_uri
        url = '%s/GeneralLedger/Account' % _url
        headers = self.get_headers(federated_login=True)
        headers['x-myobapi-cftoken'] = company_file_token
        resp = self.api_request('get', url, headers=headers)
        return resp

    def check_company_file(self, company_file, username, password):
        url = company_file.cf_uri
        headers = self.get_headers(federated_login=True)
        cf_token = self.encode_cf_token(username, password)
        headers['x-myobapi-cftoken'] = cf_token
        resp = self.api_request('get', url, headers=headers)
        return resp.status_code == 200

    def get_api_url(self):
        return self.MYOB_API_URL

    def refresh(self):
        auth = self.auth
        auth.refresh_access_token()
        self.auth = auth

    def persist(self, company_id=None):
        self.auth.persist()
        if self.request:
            self.request.session.save()
        if company_id:
            company = Company.objects.filter(id=company_id).first()
        else:
            company = None
        self.cf_data, created = MYOBCompanyFileToken.persist(self, company)

    def set_attr(self, attr, value, persist=False):
        session_attr = 'myob_' + attr
        if self.request:
            self.request.session[session_attr] = value
        self.cf_vars[attr] = value
        if persist:
            self.persist()

    def set_company_file(self, cf, persist=True):
        self.set_attr('cf_id', cf['Id'])
        self.set_attr('cf_uri', cf['Uri'])
        self.set_attr('cf_name', cf['Name'])
        if persist:
            self.persist()

    def get_cf_id(self):
        if self.request and 'myob_cf_id' in self.request.session:
            return self.request.session.get('myob_cf_id')
        if self.cf_vars.get('cf_id') is not None:
            return self.cf_vars['cf_id']
        if self.cf_data:
            return self.cf_data.company_file.cf_id
        raise MYOBProgrammingException('cf id not set')

    def get_cf_uri(self):
        if self.request and 'myob_cf_uri' in self.request.session:
            return self.request.session.get('myob_cf_uri')
        if self.cf_vars.get('cf_uri') is not None:
            return self.cf_vars['cf_uri']
        if self.cf_data:
            return self.cf_data.company_file.cf_uri
        raise MYOBProgrammingException('cf uri not set')

    def get_cf_name(self):
        if self.request and 'myob_cf_name' in self.request.session:
            return self.request.session.get('myob_cf_name')
        if self.cf_vars.get('cf_name') is not None:
            return self.cf_vars['cf_name']
        if self.cf_data:
            return self.cf_data.company_file.cf_name
        raise MYOBProgrammingException('cf name not set')

    def get_cf_token(self):
        if self.request and 'myob_cf_token' in self.request.session:
            token = self.request.session.get('myob_cf_token')

        elif self.cf_vars.get('cf_token') is not None:
            token = self.cf_vars['cf_token']

        elif self.cf_data:
            token = self.cf_data.cf_token
        else:
            token = None

        if token is None or not token.strip():
            raise MyOBCredentialException('Company file token is invalid')

        return token

    def encode_cf_token(self, username, password):
        cf_token = '{}:{}'.format(username, password)
        cf_token = cf_token.encode('utf-8')
        cf_token = base64.b64encode(cf_token)
        cf_token = cf_token.decode('utf-8')
        return cf_token

    def get_headers(self, federated_login=False):
        """ See http://myobapi.tumblr.com/post/109848079164/20151-release-notes
            for details on federated login.  Found it in ruby implementation,
            though it is not mentioned in documentation.
        """
        api_key = self.auth.get_api_key()
        access_token = self.auth.get_access_token()
        headers = {
            'Authorization': 'Bearer {}'.format(access_token),
            'x-myobapi-key': api_key,
            'x-myobapi-version': 'v2',
            'Accept-Encoding': 'gzip,deflate',
            'Content-Type': 'application/json',
        }
        if not federated_login:
            headers['x-myobapi-cftoken'] = self.get_cf_token()
        return headers

    def api_request(self, method, url, **kwargs):
        r = myob_request(method, url, **kwargs)
        if int(r.status_code) == 401:
            self.refresh()
            kwargs['headers'] = self.get_headers()
            return self.api_request(method, url, **kwargs)
        return r

    def api_call(self, method, uri, **kwargs):

        if 'headers' not in kwargs:
            kwargs['headers'] = self.get_headers()
        return self.api_request(method, uri, **kwargs)

    def get_company_files(self):
        url = self.get_api_url()
        headers = self.get_headers(federated_login=True)
        return self.api_request('get', url, headers=headers).json()

    def get_resources(self):
        uri = self.get_cf_uri()
        return self.api_call('get', uri)

    def get_current_user(self):
        uri = self.get_cf_uri() + '/CurrentUser'
        return self.api_call('get', uri)

    def init_api(self, timeout=False):
        if self.api is None:
            self.api = MYOBAccountRightV2API(self)
            self.api._init_api(timeout)


class MYOBAccountRightV2API(object):
    """ Collection of MYOBAccountRightAPIResource objects """

    def __init__(self, myob_client):
        self._client = myob_client

    def _init_api(self, timeout=False):
        self._init_api_resources(timeout)
        self._init_api_access_methods(timeout)

    def _init_api_resources(self, timeout=False):
        cf_uri = self._client.get_cf_uri()
        resp = self._client.get_resources()
        data = resp.json()

        if isinstance(data, str):
            raise MYOBImplementationException(_("MyOB settings are incorrectly configured"))

        if 'Resources' not in data:
            message = data.get('Message', None)

            if timeout and message == 'Access denied':
                return

            self._init_api_resources()

        for uri in data['Resources']:
            if not check_account_id(uri, cf_uri):
                msg = _("Resource URI differs from Company File URI")
                raise MYOBImplementationException(msg)
            uri_path = uri[len(cf_uri):]
            uri_path_parts = uri_path.strip('/').split('/')

            api_path = ''
            api_point = self
            for part in uri_path_parts:
                api_path += '/' + part
                if not hasattr(api_point, part):
                    r = MYOBAccountRightV2Resource(self._client, uri, api_path)
                    setattr(api_point, part, r)
                api_point = getattr(api_point, part)

        print('api resources initialized')

    def _init_api_access_methods(self, timeout=False):
        cf_uri = self._client.get_cf_uri()
        resp = self._client.get_current_user()
        data = resp.json()

        if 'UserAccess' not in data:
            message = data.get('Message', None)

            if timeout and message == 'Access denied':
                return

            self._init_api_access_methods()

        for user_access in data['UserAccess']:
            uri = user_access['ResourcePath']
            available_methods = user_access['Access']

            if not check_account_id(uri, cf_uri):
                msg = _("Resource (Access) URI differs from Company File URI")
                raise MYOBImplementationException(msg)
            uri_path = uri[len(cf_uri):]
            uri_path_parts = uri_path.strip('/').split('/')

            api_path = ''
            api_point = self
            for part in uri_path_parts:
                api_path += '/' + part
                if not hasattr(api_point, part):
                    # XXX: some resources are not set yet...
                    r = MYOBAccountRightV2Resource(self._client, uri, api_path)
                    setattr(api_point, part, r)
                api_point = getattr(api_point, part)

            if api_point != self:
                api_point._init_access(available_methods)

        print('api access methods initialized')


class MYOBAccountRightV2Resource(object):
    """ MYOB Account Right V2 API Resource """

    def __init__(self, myob_client, uri, api_path):
        self._uri = uri
        self._path = api_path
        self._client = myob_client
        self._access = None
        self._allow_get = False
        self._allow_put = False
        self._allow_post = False
        self._allow_delete = False
        self._initialized = False

    def _init_access(self, available_methods):
        self._access = available_methods
        for method in available_methods:
            setattr(self, '_allow_' + method.lower(), True)
        self._initialized = True

    def _check_method(self, value):
        if not value:
            if not self._initialized:
                msg = "API not initialized or resource method not available"
            else:
                msg = "Resource method is not supported"
            raise MYOBException(msg)

    def _get_uri(self):
        return self._uri

    def _get_response(self, resp, raw_resp=False):
        try:
            return resp if raw_resp else resp.json(parse_float=decimal.Decimal)
        except ValueError as e:
            log.warning('{}'.format(e))

    def get(self, raw_resp=False, uid=None, **kwargs):
        """ Use the HTTP GET method to retrieve data from the database.
            This includes both lists and individual records.
            http://developer.myob.com/api/accountright/api-overview/creating-updating/
        """
        self._check_method(self._allow_get)
        uri = self._get_uri()
        if uid:
            uri = '/'.join([uri.rstrip('/'), uid])
        resp = self._client.api_call('get', uri, **kwargs)
        return self._get_response(resp, raw_resp)

    def put(self, raw_resp=False, uid=None, **kwargs):
        """ Use the PUT method to update an existing entry in the database.
            http://developer.myob.com/api/accountright/api-overview/creating-updating/

            Please note: When updating an existing record,
            you will need to add the unique record identifier GUID
            to the end of the URI
        """
        self._check_method(self._allow_put)
        uri = self._get_uri()
        if uid:
            uri = '/'.join([uri.rstrip('/'), uid])
        resp = self._client.api_call('put', uri, **kwargs)
        return self._get_response(resp, raw_resp)

    def post(self, raw_resp=False, **kwargs):
        """ Use the POST method to add a new entry to the database,
            whether it already exists or not.
            http://developer.myob.com/api/accountright/api-overview/creating-updating/
        """
        self._check_method(self._allow_post)
        resp = self._client.api_call('post', self._get_uri(), **kwargs)
        return self._get_response(resp, raw_resp)

    def delete(self, raw_resp=False, uid=None, **kwargs):
        self._check_method(self._allow_delete)
        uri = self._get_uri()
        if uid:
            uri = '/'.join([uri.rstrip('/'), uid])
        resp = self._client.api_call('delete', uri, **kwargs)
        return self._get_response(resp, raw_resp)

    def iterator(self, **kwargs):
        data = self.get(**kwargs)
        total = data['Count']
        count = 0
        while True:
            for i in data.get('Items', []):
                count += 1
                print('{}:{}'.format(total, count))
                yield(i)
            next_page_link = data.get('NextPageLink')
            if next_page_link:
                data = self._client.api_call('get', next_page_link)
            else:
                break
