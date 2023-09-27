from rest_framework import status
from rest_framework.exceptions import APIException


class MYOBClientException(Exception):
    """
    Default MYOB Client exception
    """


class MYOBException(APIException):
    """
    General MYOB related Exception
    """
    status_code = status.HTTP_400_BAD_REQUEST


class MyOBCredentialException(MYOBException):
    """
    MYOB Exception raised when API use bad credentials
    """


class MYOBProgrammingException(MYOBException):
    """
    MYOB Exception raised when API wrapper is used improperly.
    """


class MYOBImplementationException(MYOBException):
    """
    MYOB Exception raised when current API implementation
    encounters unexpected and unhandled situation.
    """


class MYOBServerException(MYOBException):
    """
    MYOB Server Exception (5xx) raised after retries.
    """