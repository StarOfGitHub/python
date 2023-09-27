import os
from setuptools import setup

PACKAGE_NAME = 'r3sourcer'
DIRNAME = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(DIRNAME, 'README.md')) as f:
    README = f.read()

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name=PACKAGE_NAME,
    version='0.1',
    packages=[PACKAGE_NAME],
    description='r3sourcer-module',
    long_description=README,
    include_package_data=True,
    entry_points='''
        [console_scripts]
        django=helpers.commands:django
        app=helpers.commands:app
        py_test=helpers.commands:py_test
        celery=helpers.commands:celery
        _supervisord=helpers.commands:supervisord
        _supervisorctl=helpers.commands:supervisorctl
    '''
)
