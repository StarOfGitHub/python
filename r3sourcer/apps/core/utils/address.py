from unidecode import unidecode
from django.db.models import Q
from django.utils.text import slugify
from django.utils.translation import ugettext_lazy as _
from rest_framework.exceptions import ParseError

from r3sourcer.apps.core.models import Country, Region, City


def get_address_parts(address_data):
    address_parts = {}

    for item in address_data.get('address_components', []):
        for item_type in item['types']:
            if item_type != 'political':
                address_parts[item_type] = item
                # converts names to unicode
                address_parts[item_type]['short_name'] = unidecode(address_parts[item_type]['short_name'])
                address_parts[item_type]['long_name'] = unidecode(address_parts[item_type]['long_name'])

    return address_parts


def get_street_address(address_parts):
    if address_parts.get('route'):
        street_address = address_parts['route']['long_name']
        street_number = address_parts.get('street_number', {}).get('long_name', '')
        if street_number:
            street_address = ' '.join([street_number, street_address])
    elif address_parts.get('locality'):
        street_address = address_parts['locality']['long_name']
    else:
        street_address = ''
    return street_address


def parse_google_address(address_data):
    address_parts = get_address_parts(address_data)
    location = address_data.get('geometry', {}).get('location')
    if not address_parts.get('country') or not address_parts.get('locality'):
        raise ParseError({'address': _('Please enter a valid address')})
    if not address_parts.get('postal_code'):
        raise ParseError({'address': _("The entered address doesn't have postal code. Please enter more detailed address.")})

    # get country
    country = Country.objects.get(code2=address_parts['country']['short_name'])
    # get region
    region_part_key = sorted([x for x in address_parts.keys()
                          if 'administrative_area_level_' in x])
    region_part_key = region_part_key[0] if region_part_key else 'locality'
    region_short_name = address_parts.get(region_part_key)['short_name']
    region_long_name = address_parts.get(region_part_key)['long_name']
    # sarch for existing region
    region = Region.objects.filter(Q(name__icontains=region_long_name) | \
                                    Q(alternate_names__contains=region_short_name),
                                    country=country) \
                           .first()
    # create new region if it doesn't exist
    if not region:
        region = Region.objects.create(name=region_long_name,
                                        country=country,
                                        display_name=region_short_name,
                                        alternate_names=region_short_name)

    # get city part
    city_part = address_parts.get('locality') or address_parts.get('sublocality')
    city_long_name = city_part['long_name']
    city_search = '%s%s' % (city_long_name.replace(' ', ''), country.name.replace(' ', ''))
    # filter by country, region and search_names
    cities = City.objects.filter(country=country,
                                 region=region,
                                 search_names__icontains=city_search)
    # filter by name
    city = cities.filter(name=city_long_name).first()
    # filter by Alternate names
    if not city:
        city = cities.filter(alternate_names__contains=city_long_name).first()
    # create If not exists
    if not city:
        city = City.objects.create(country=country, region=region, name=city_long_name, search_names=city_long_name,
                                   latitude=location.get('lat', 0), longitude=location.get('lng', 0))


    postal_code = address_parts.get('postal_code', {}).get('long_name')
    address = {
        'country': str(country.id),
        'state': str(region.id) if region else None,
        'city': str(city.id),
        'postal_code': postal_code,
        'street_address': get_street_address(address_parts),
    }

    if location:
        address.update({
            'latitude': location.get('lat', 0),
            'longitude': location.get('lng', 0),
        })

    if address_data.get('apartment'):
        address['apartment'] = address_data['apartment']

    return address
