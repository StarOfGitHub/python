# Project setup steps

## Main info:

1. Install docker for your operation system (Docker community Edition: CE): https://docs.docker.com/engine/installation/#platform-support-matrix;

2. For using docker without sudo run
    `sudo usermod -aG docker $USER`


## Development:

1. Generate ssh key for git and add generated public key to your bitbucket ssh keys. Set env PRIVATE_REPO_KEY to the private key's path value (.env file);
2. Generate ssh keys for JWT and add generated keys to "keys" folder in your project root.
3. Run docker-compose -f docker-compose.dev.yml build;
4. Run all containers  as daemon: 
docker-compose -f docker-compose.dev.yml up -d;
5. Stop/Start containers:
docker-compose -f docker-compose.dev.yml stop/start;
6. Check logs from container:
docker-compose -f docker-compose.dev.yml logs -f service_name;

### Helper commands for developers:

1. Createsuperuser: `docker-compose exec web bin/django createsuper`;
2. Migrate: `docker-compose exec web bin/django migrate`;
3. Execute bash commands: `docker-compose exec web ls -la`;
4. Attach to bash: `docker-compose exec web bash`;

# Nginx configuration

For using system Nginx server set env variable `USE_NGINX_DOCKER` to `0` and `NGINX_CONFIG_PATH` to nginx virtualhost file's directory path.

For using Docker nginx server set env variable `USE_NGINX_DOCKER` to `1` (default).

###  Nginx env variables:

* `DOMAIN_NAME` domain name server (`example.com`)
* `USE_TLS` - switch on/off ssl settings from nginx config file (choices: `0`, `1`. Default: `1`).
    * `0` - disable HTTPS;
    * `1` - enable HTTPS.

#### Extra settings:

* `USE_NGINX_DOCKER` - we can use nginx server without docker (choices: `0`, `1`. Default: `1`):
    * `0`- use nginx from system;
    * `1`- use docker nginx;
* `NGINX_CONFIG_PATH` - if you use system nginx server (`USE_NGINX_DOCKER`=0), set `NGINX_CONFIG_PATH` (default: `/etc/nginx/sites-enabled/`; example: `/usr/local/etc/nginx/servers/`).
* `NGINX_VOLUME` - directory which would be mounted to nginx container and used as `conf` and `www` root. Example: `%s/crm/static, %s/crm/media` & `%s/some-r3sourcer/static`, & `%s/some-r3sourcer/media`, etc. We can use system nginx server, see `USE_NGINX_DOCKER` env.
* `DJANGO_STUFF_URL_PREFIX` -  django stuff prefix. Would be used in urls and nginx configuration.
* `DJANGO_DEBUG` - debug mode (choices: `0`, `1`. Default: `1`).
* `CACHE_KEY_PREFIX` - cache key prefix. Would be used for different projects and the same redis container (default: `r3sourcer-cms`).
* `DJANGO_UWSGI_PORT` - used for binding external port to container listening. (Default: `8081`).
* `ALLOWED_HOSTS` - Django ALLOWED_HOSTS setting (https://docs.djangoproject.com/en/1.10/ref/settings/#allowed-hosts), use separator `,` (example test.ru,example.com). (Default: `*`)


# WEB-UI configuration

To use web-ui module set env variable `DJANGO_STUFF_URL_PREFIX`. This variable (`DJANGO_STUFF_URL_PREFIX`) responsible for the django stuff url placement. Web-ui will be available by the root url "/".
For disabling web-ui module set env `DJANGO_STUFF_URL_PREFIX` to the empty value (`DJANGO_STUFF_URL_PREFIX=`).
Example: `DJANGO_STUFF_URL_PREFIX=ecore` (by default) => `/ecore/`, `/ecore/admin`.
This variable used in the Nginx routing configuration.


# Make commands
#### Setup docker app
    make

#### Apply migrations
    make migrate

#### Start develop server
    make runserver

#### Collect static
    make static

### Supervisor
#### Supervisord
    make supervisord

#### Supervisor status
    make supervisor

#### Stop/Restart
    make supervisor-stop
    make supervisor-restart
    make restart-uwsgi
    make restart-celery
    make restart-celerycam
    make restart-celery-beat

#### Start all containers
    make docker-start-all

#### Other commands
    make bash-app
    make shell_plus
    make pip-install


# Tests
#### Run tests
    make tests

#### Run tests locally
    pytest

#### Rut tests with coverage
    make tests_cov

#### Rut tests with coverage locally
    pytest --cov=r3sourcer --cov-report=term-missing
