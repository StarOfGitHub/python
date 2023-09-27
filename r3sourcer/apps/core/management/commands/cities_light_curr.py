from cities_light.management.commands.cities_light import Command as CitiesLightCommand
from cities_light.exceptions import InvalidItems
from cities_light.signals import country_items_pre_import, country_items_post_import
from cities_light.settings import ICountry

from r3sourcer.apps.core.models import Country


class Command(CitiesLightCommand):

    def country_import(self, items):
        try:
            country_items_pre_import.send(sender=self, items=items)
        except InvalidItems:
            return
        try:
            country = Country.objects.get(code2=items[ICountry.code])
        except Country.DoesNotExist:
            if self.noinsert:
                return
            country = Country(code2=items[ICountry.code])

        country.name = items[ICountry.name]
        # Strip + prefix for consistency. Note that some countries have several
        # prefixes ie. Puerto Rico
        country.phone = items[ICountry.phone].replace('+', '')
        country.code3 = items[ICountry.code3]
        country.continent = items[ICountry.continent]
        country.currency = items[ICountry.currencyCode]
        country.tld = items[ICountry.tld][1:]  # strip the leading dot
        if items[ICountry.geonameid]:
            country.geoname_id = items[ICountry.geonameid]

        country_items_post_import.send(sender=self, instance=country,
                                       items=items)

        self.save(country)
