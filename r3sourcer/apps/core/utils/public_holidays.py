import enum
import requests
import datetime


__all__ = [
    'EnricoApiException', 'RequestParams', 'EnricoApi'
]


class EnricoApiException(Exception):
    pass


class Actions(enum.Enum):

    GET_FOR_MONTH = 'getPublicHolidaysForMonth'
    GET_FOR_YEAR = 'getPublicHolidaysForYear'
    GET_SUPPORTED_COUNTRIES = 'getSupportedCountries'
    CHECK_HOLIDAY = 'isPublicHoliday'


class RequestParams(object):

    __slots__ = [
        'action',
        'country',
        'year',
        'date',
        'month'
    ]

    def __init__(self, action, **params):
        assert isinstance(action, str)

        self.action = action

        for key, value in params.items():
            setattr(self, key, value)

    def to_dict(self):
        return {
            key: getattr(self, key)
            for key in self.__slots__ if getattr(self, key, None) is not None
        }


class EnricoApi(object):

    url = 'http://kayaposoft.com/enrico/json/{version}/index.php'
    version = 'v1.0'
    actions = (
        Actions.GET_FOR_MONTH.value,
        Actions.GET_FOR_YEAR.value,
        Actions.GET_SUPPORTED_COUNTRIES.value
    )

    def _request(self, params):
        """
        
        :param params: instance of RequestParams
        :return: dict Response data
        """

        assert isinstance(params, RequestParams)
        url = self.get_api_url()
        try:
            response = requests.get(url, params.to_dict())
            json_response = response.json()
        except Exception as e:
            raise EnricoApiException(e)
        return json_response

    def get_api_url(self):
        return self.url.format(version=self.version)

    def fetch_for_year(self, country, year):
        """
        Fetch holidays for year
        
        :param country: str Country code
        :param year: int Year for search
        :return: list
        """

        params = RequestParams(action=Actions.GET_FOR_YEAR.value, country=country, year=year)
        return self._request(params)

    def fetch_for_month(self, country, year, month):
        """
        Fetch holidays for year
         
        :param country: str Country code
        :param year: int Year for search
        :param month: int Moth for search
        :return: list
        """

        params = RequestParams(action=Actions.GET_FOR_MONTH.value, country=country, year=year, month=month)
        return self._request(params)

    def fetch_supported_countries(self):
        """
        Get supported countries
        
        :return: list
        """

        params = RequestParams(action=Actions.GET_SUPPORTED_COUNTRIES.value)
        return self._request(params)

    def is_holiday(self, country, date):
        """
        Check if date is holiday
        
        :param country: str Country code
        :param date: 
        :return: bool Return True if date is holiday
        """

        assert isinstance(date, (datetime.datetime, datetime.date))

        date_str = date.strftime('%d-%m-%Y')
        params = RequestParams(action=Actions.CHECK_HOLIDAY.value, country=country, date=date_str)
        return self._request(params)['isPublicHoliday']
