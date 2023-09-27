from rest_framework import status
from rest_framework.exceptions import APIException


class Custom409(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'A conflict occurred'
