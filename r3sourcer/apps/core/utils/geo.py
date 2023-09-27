from time import sleep
from datetime import datetime, date, time

import googlemaps
import googlemaps.exceptions

from django.conf import settings

from r3sourcer.helpers.datetimes import utc_now

MODE_DRIVING = 'driving'
MODE_TRANSIT = 'transit'
MAX_DIMENSIONS = 25


class GMapsException(Exception):
    """
    Class for google maps api errors
    """
    # Need to fix request parameters
    # Requested is invalid
    INVALID_REQUEST = 'INVALID_REQUEST', 101

    # Request to calculate distance is too large
    MAX_ELEMENTS_EXCEEDED = 'MAX_ELEMENTS_EXCEEDED', 102

    # Needs to change account or wait
    OVER_QUERY_LIMIT = 'OVER_QUERY_LIMIT', 103

    # Requires authenticating
    REQUEST_DENIED = 'REQUEST_DENIED', 104

    # Unexpected error.
    # Can be fixed after retry
    UNKNOWN_ERROR = 'UNKNOWN_ERROR', 199

    def __init__(self, e):
        """
        Exception wrapper
        :param e:
        """
        self.message = str(e)
        self.status, self.code = self.dispatch_exception(e)

    def __str__(self):
        """
        :return str:
        """
        return 'Error code {} - {}'.format(self.code, self.message)

    @staticmethod
    def dispatch_exception(e):
        """
        Exception type dispatcher
        :param e:
        :return tuple(str, int):
        """
        if hasattr(e, 'status') and hasattr(GMapsException, e.status):
            return getattr(GMapsException, e.status)

        # Bad request processing
        if hasattr(e, 'status_code') and e.status_code == 400:
            return GMapsException.INVALID_REQUEST

        return GMapsException.UNKNOWN_ERROR


class GMaps(object):
    """
    Google Maps helper

    Validating address:

        # Invalid
        >> gmaps.is_address_valid('')
        << False

        # Valid
        >> gmaps.is_address_valid('Kiev')
        << True

        # Can't check it now
        >> gmaps.is_address_valid('Kiev')
        << None

    """
    def __init__(self, key, ignore_exceptions=None):
        """
        GMaps wrapper instance
        :param key:
        :param ignore_exceptions:
        """
        self._client = googlemaps.Client(key=key)
        self._ignore_exceptions = ignore_exceptions or [199]

    def set_retry_codes(self, codes):
        """
        Sets exceptions codes that will be ignored

        By default ignores 199 (Unknown) only errors. If maximum
        retries limit is reached, exception will be raised anyway.

        :param codes:
        :return:
        """
        self._ignore_exceptions = codes

    def is_address_valid(self, address, retries=5, retry_interval=0):
        """
        Checks is address valid.

        None - can not be checked now
        True - valid
        False - invalid

        :param str address:
        :param int retries:
        :param int|float retry_interval:
        :return bool|None:
        """
        try:
            self.get_coordinates(address, retries, retry_interval)
            return True
        except GMapsException as e:
            return False if e.code == GMapsException.INVALID_REQUEST[1] else None

    def get_coordinates(self, address, retries=5, retry_interval=0):
        """
        Returns tuple with address coordinates
        :param str address:
        :param int retries:
        :param int|float retry_interval:
        :return tuple(float, float):
        """
        try:
            response = self._client.geocode(address)
            if not response:
                raise googlemaps.exceptions.ApiError(
                    status='INVALID_REQUEST',
                    message='Invalid address requested'
                )

            return (
                response[0]['geometry']['location']['lat'],
                response[0]['geometry']['location']['lng']
            )
        except Exception as e:
            exc = GMapsException(e)
            if exc.code in self._ignore_exceptions and retries > 0:
                if retry_interval > 0:
                    sleep(retry_interval)
                return self.get_coordinates(address, retries-1, retry_interval)

            raise exc

    def get_distance(self, origins, destinations, mode=None, retries=5, retry_interval=0):
        """
        Returns list with calculated distances
        :param str origins:
        :param str destinations:
        :param str|None mode:
        :param int retries:
        :param int|float retry_interval:
        :return list:
        """
        try:
            dm_results = self._client.distance_matrix(
                origins,
                destinations,
                mode,
                departure_time=int(
                    datetime.combine(utc_now().date(), time(6, 0)).timestamp()
                ) if mode == MODE_TRANSIT else None
            )

            result = []
            for row in dm_results.get('rows', []):
                data_row = []
                for element in row.get('elements', []):
                    if element['status'] != 'OK':
                        # TODO: Not sure that we need empty element. Leaved as is.
                        data_row.append({"distance": None, "duration": None})
                    else:
                        data_row.append({"distance": element['distance']['value'],
                                         "duration": element['duration']['value']})
                if len(data_row) == 1:
                    result.append(data_row[0])
                else:
                    result.append(data_row)

            return result
        except Exception as e:
            exc = GMapsException(e)
            if exc.code in self._ignore_exceptions and retries > 0:
                if retry_interval > 0:
                    sleep(retry_interval)
                return self.get_distance(origins, destinations, mode, retries-1, retry_interval)

            raise exc


def fetch_geo_coord_by_address(address):
    """
    Shortcut to fetch geocoding coordinates of the first result
    or return:

    None - When got invalid request
    False - Otherwise

    Automatically retries to load data if fails.

    :param address:
    :return tuple(float, float)|bool|None:
    """
    try:
        client = GMaps(key=settings.GOOGLE_GEO_CODING_API_KEY)
        return client.get_coordinates(address)
    except GMapsException as e:
        return (None, None) if e.code == GMapsException.INVALID_REQUEST[1] else (False, False)
    except ValueError:
        return (None, None)


def calc_distance(origins, destinations, mode=None):
    """
    Shortcut to fetch distance calculations between some points on map
    or return:

    None - When got invalid request
    False - Otherwise

    Automatically retries to load data if fails.

    :param origins:
    :param destinations:
    :param mode:
    :return list|bool|None:
    """
    try:
        client = GMaps(key=settings.GOOGLE_DISTANCE_MATRIX_API_KEY)
        return client.get_distance(origins, destinations, mode)
    except GMapsException as e:
        return None if e.code == GMapsException.INVALID_REQUEST[1] else []
    except ValueError:
        return None
