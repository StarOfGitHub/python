import os
import sys
import click
from invoke import run
from jinja2 import Template

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def set_env(*args):
    configs = list(args)
    if not configs:
        configs = ['.env_defaults', '.env']

    for config in configs:
        if os.path.isfile(os.path.join(BASE_DIR, config)):
            with open(os.path.join(BASE_DIR, config), 'r') as f:
                for line in f.readlines():
                    if not line.strip():
                        continue
                    var, value = line.split('=', 1)
                    os.environ[var.strip()] = value.strip().strip('"')


def django():
    """Django manage.py
    """

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "r3sourcer.settings.prod")
    set_env('.env_defaults', '.env', '.env_test')

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


def celery():
    set_env()

    from celery.__main__ import main

    return main()


@click.group()
def app():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "r3sourcer.settings.prod")
    set_env()


@app.command()
def start():
    os.chdir(BASE_DIR)
    run('honcho start', warn=True, pty=True)


@app.command()
@click.option('--app', default='')
@click.argument('app', default='')
def test(app):
    set_env('.env_test')
    os.chdir(BASE_DIR)

    if app:
        app = os.path.join('apps', app)

    run('pytest --cov={app} --cov-report=term-missing --cov-config .coveragerc {app}'.format(
        app=os.path.join('r3sourcer', app)), warn=True, pty=True)


@click.command()
def py_test():
    os.chdir(BASE_DIR)
    set_env('.env_defaults', '.env', '.env_test')
    run('pytest')


@app.command()
@click.option('--site_root')
def nginx_config(site_root):
    required_env = ['DOMAIN_NAME', 'API_DOMAIN_NAME']
    os.environ.setdefault('SITE_CONTENT_ROOT', site_root)

    if not all([req in os.environ for req in required_env]):
        raise ValueError("Required env variables: {}".format('. '.join(required_env)))
    with open(os.path.join(BASE_DIR, 'conf/templates/nginx.conf'), 'r') as templ_conf_file:
        sys.stdout.write(Template(templ_conf_file.read()).render(**os.environ))


@app.command()
def crontab_config():
    required_env = ['BASE_DIR']
    if not all([req in os.environ for req in required_env]):
        raise ValueError("Required env variables: {}".format('. '.join(required_env)))
    with open(os.path.join(BASE_DIR, 'conf/templates/crontab'), 'r') as templ_conf_file:
        sys.stdout.write(Template(templ_conf_file.read()).render(**os.environ))


@click.command()
def supervisord():
    os.chdir(BASE_DIR)
    set_env()
    run('''
        {BASE_DIR}/venv/py2/bin/supervisord -c \\
        {BASE_DIR}/{SUPERVISOR_CONF}
    '''.format(
        BASE_DIR=BASE_DIR,
        SUPERVISOR_CONF=os.environ.get('SUPERVISOR_CONF'),
    ))


@click.command(context_settings=dict(
    ignore_unknown_options=True,
))
@click.argument('supervisor_args', nargs=-1, type=click.UNPROCESSED)
def supervisorctl(supervisor_args):
    os.chdir(BASE_DIR)
    set_env()
    command = (
        '{BASE_DIR}/venv/py2/bin/supervisorctl '
        ' -c {BASE_DIR}/{SUPERVISOR_CONF}'
    ).format(
        BASE_DIR=BASE_DIR,
        SUPERVISOR_CONF=os.environ.get('SUPERVISOR_CONF'),
    )
    args = [
        command
    ]
    args += list(supervisor_args)
    run(' '.join(args))
