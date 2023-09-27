# MYOB API wrapper #

### Urls

OAuth2 (MYOB user sign-in)
https://secure.myob.com/oauth2/account/

Access & Refresh token
https://secure.myob.com/oauth2/v1/authorize

API calls
https://api.myob.com/

### Setup

First of all Company Files should be set-up for work with app.

User has to sign into MYOB account.
(MYOBAuthData object is stored).

Having signed in, user can grant app permission to access certain company files.
Admin is presented with a list of CompanyFiles to work with.
Admin has to sign into a chosen CompanyFile and link it to the Account.
(MYOBCompanyFile and MYOBCompanyFileToken are stored)

(repeat this steps to add multiple company files)

http://<server_address>[:<port>]/myob/


### CLI USAGE

After Company Files have been set-up one can use MYOBClient via cli.

#### option1
from endless_myob.models import MYOBCompanyFileToken
from endless_myob.api import MYOBClient
cft = MYOBCompanyFileToken.objects.first()  # or filter as you like
client = MYOBClient(cf_data=cft)

#### option2
from endless_myob.helpers import get_myob_client
client = get_myob_client(cf_id=<company_file_id>)
client = get_myob_client()  # will use default (first) company file

#### we also need to initialize client API
client.init_api()

#### now we can access AccountRightV2 resources
#### json response by myob api
json_data = client.api.Contact.get()

sorted(list(json_data.keys())) == ['Count', 'Items', 'NextPageLink']

json_data['Count']  # total count of items in result set
json_data['Items']  # items returned by this request (<= Count)
json_data['NextPageLink']  # api link to access next item set or None

#### access response returned by requests lib if neccessary
raw_resp = client.api.Contact.get(raw_resp=True)

#### use the iterator for json items if neccessary
it = client.api.Contact.iterator()
for item in it:
    do_something(item)

#### filter data using OData params supported by MYOB
#### http://developer.myob.com/api/accountright/api-overview/retrieving-data/
data = client.api.Contact.get(params={'$filter': "LastModified gt datetime'2016-07-20'"})

#### get items by gUID
item_uid = data['Items'][0]['UID']
item = client.api.Contact.get(uid=item_uid)
assert item == data['Items'][0]
