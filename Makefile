SHELL := /bin/bash

WEBUI_APP_DIR = webui-app
NGINX_SITE_VOLUME = ""
CURRENT_PATH = $(shell pwd)
CURRENT_DATETIME = $(shell date +%Y_%m_%d__%H_%M)

NGINX_DOCKER_VOLUME = /Users/nginx_docker

NGINX_CONF_FILE = var/tmp/nginx.$(DOMAIN_NAME).conf
REDIS_VERSION = alpine
RABBIT_MQ_VERSION = 3
DOCKER_BASE_DIR = /app

PG_VERSION = 9.6
LANG = 'en-au'

include .env_defaults
-include .env

PG_LOGIN = -h $(POSTGRES_HOST) -p $(POSTGRES_PORT) -U $(POSTGRES_USERNAME)
PG_LOGIN_POSTGRES = -h $(POSTGRES_HOST) -p $(POSTGRES_PORT) -U endless

RESTORE_DB_FILE_PATH = var/backups/$(RESTORE_DB_FILE)
RESTORE_DB_FOR_DEV_FILE_PATH = var/backups/$(RESTORE_DB_FOR_DEV_FILE)

define docker_exec
    docker exec $(2) $(DOCKER_APP_NAME) $(1)
endef

define docker_compose_exec
    docker-compose exec $(2) web $(1)
endef

define supervisor
    $(call docker_exec, bin/_supervisorctl $(1))
endef

define nginx_root1
    $(eval NGINX_SITE_VOLUME = $(NGINX_VOLUME)/$(DOCKER_APP_NAME)/)
endef

define nginx_root0
    mkdir -p var/www
    $(eval NGINX_SITE_VOLUME = $(CURRENT_PATH)/var/www/)
endef

define nginx_setup0
    make var/make/local-nginx
endef

define nginx_setup1
    make var/make/docker-nginx
endef

define docker_connect
    docker network connect --ip $2 $(DOCKER_SUB_NET_NAME) $1
endef

define docker_run
	@if !(docker ps -a -f name=$(2) | grep '$(2)$$'); then \
        echo "Run $(1) container"; \
        docker run -itd $(3) --name $(2) $(1); \
        $(call docker_connect,$(2), $(4)); \
    fi;
endef

define create_backup
	mkdir -p var/backups/$(1)
	touch var/backups/$(1)/$(2)
	docker exec -it $(DOCKER_POSTGRES_NAME) pg_dump -U $(POSTGRES_USER) $(POSTGRES_DB) | gzip > var/backups/$(1)/$(2)
	aws s3 cp var/backups/$(1)/$(2) $(S3_BACKUP_FOLDER)$(1)/$(2)
    rm -rf var/backups/$(1)/
endef

all: \
  var/make \
  var/tmp \
  var/run \
  var/make/docker-redis \
  var/make-docker-postgres \
  var/make/docker-rabbitmq \
  var/make/docker-clickhouse \
  var/make/create-app \
  var/make/create-db \
  var/make/nginx \
  var/make/webui-app

.env:
	cp .env_defaults .env
	echo "SYSTEM_USER=$(USER)" >> .env

var/make:
	mkdir -p var/make

var/run:
	mkdir -p var/run

var/tmp:
	mkdir -p var/tmp

var/www:
	mkdir -p var/www

docker-install:
	sudo apt-get install -y --no-install-recommends apt-transport-https ca-certificates curl software-properties-common
	sudo apt-get update
	sudo apt-key adv --keyserver hkp://p80.pool.sks-keyservers.net:80 --recv-keys 58118E89F3A912897C070ADBF76221572C52609D
	sudo apt-get update
	sudo apt-get install -y docker-engine
	sudo apt-add-repository 'deb https://apt.dockerproject.org/repo ubuntu-xenial main'
	sudo usermod -aG docker $(whoami)
	touch $@

var/make/create-db:
	make create-postgres-user
	make create-postgres-db
	@touch $@

create-postgres-user:
	docker exec $(DOCKER_POSTGRES_NAME)  bash -c "psql -U postgres -tAc \"SELECT 1 FROM pg_roles WHERE rolname='$(POSTGRES_USER)'\" | \
	     grep -q 1 || createuser -U postgres -d -e -E -l -w -r -s $(POSTGRES_USER)"

create-postgres-db:
	docker exec -it $(DOCKER_POSTGRES_NAME)  bash -c "psql -U postgres -tAc \"SELECT 1 FROM pg_database WHERE datname='$(POSTGRES_DB)'\" | \
	     grep -q 1 || createdb \
	     -E utf8 \
	     -U $(POSTGRES_USER)  \
	     --lc-collate=en_US.UTF-8 \
	     --lc-ctype=en_US.UTF-8 \
	     --encoding=UTF-8 \
	     --template=template0 \
	     $(POSTGRES_DB)"

var/make/nginx:
	$(call nginx_setup$(USE_NGINX_DOCKER))

var/make/local-nginx:
	$(call docker_exec, app nginx_config --site_root=$(CURRENT_PATH)/var/www > $(NGINX_CONF_FILE));
	@if sudo ls $(NGINX_CONFIG_PATH); then \
        sudo rm -f $(NGINX_CONFIG_PATH)/$(DOMAIN_NAME).conf; \
        sudo ln -s $(CURRENT_PATH)/$(NGINX_CONF_FILE) $(NGINX_CONFIG_PATH)/$(DOMAIN_NAME).conf; \
    else \
	    echo "Nginx path not found, you should setup NGINX_CONFIG_PATH env."; \
	    exit 1; \
    fi;
	@touch $@

var/make/docker-nginx:
	make var/make/create-docker-nginx
	make nginx_config/docker
	@touch $@

nginx_config/docker:
	$(call docker_exec, app nginx_config \
	    --site_root=/www/$(DOCKER_APP_NAME) > \
	    $(NGINX_CONF_FILE))
	@sudo cp $(NGINX_CONF_FILE) $(NGINX_VOLUME)/conf/nginx.$(DOMAIN_NAME).conf
	docker restart nginx

full-clean:
	make clean
	@for CONTAINER in $(DOCKER_POSTGRES_NAME) $(DOCKER_RABBIT_MQ_NAME) $(DOCKER_REDIS_NAME) \
	    $(DOCKER_CLICKHOUSE_NAME) nginx $(DOCKER_APP_NAME); \
	do \
		if docker ps -a | grep $$CONTAINER; then \
		    echo "Remove container: $$CONTAINER"; \
            docker rm -f $$CONTAINER; \
        fi ; \
	done

clean:
	@make rm-docker-app;
	@if (docker images | grep r3sourcer-$(DOCKER_APP_NAME)-image); then \
	    docker rmi r3sourcer-$(DOCKER_APP_NAME)-image; \
	    echo "Image removed"; \
	fi ;

	@if (docker ps -a | grep " webui-$(DOCKER_APP_NAME)"); then \
	    docker stop webui-$(DOCKER_APP_NAME); \
	    echo "WEB-UI container stopped"; \
	    docker rm webui-$(DOCKER_APP_NAME); \
	    echo "WEB-UI container removed"; \
	fi ;
	@if (docker images | grep webui-$(DOCKER_APP_NAME)-image); then \
	    docker rmi webui-$(DOCKER_APP_NAME)-image; \
	    echo "WEB-UI image removed"; \
	fi ;
	@rm -rf var/make

drop_db:
	docker stop $(DOCKER_APP_NAME)
	docker exec $(DOCKER_POSTGRES_NAME) dropdb -U postgres --if-exists $(POSTGRES_DB)

backup_db:
	mkdir -p var/backups/
	touch var/backups/`date +%Y_%m_%d__%H_%M`.bak && \
	ln -sf $(CURRENT_PATH)/var/backups/`date +%Y_%m_%d__%H_%M`.bak var/backups/latest.bak && \
	docker exec -it $(DOCKER_POSTGRES_NAME) pg_dump -U $(POSTGRES_USER) $(POSTGRES_DB) > var/backups/`date +%Y_%m_%d__%H_%M`.bak

backup_db_for_dev:
	mkdir -p var/backups/
	docker exec -it $(DOCKER_POSTGRES_NAME) pg_dump -U $(POSTGRES_USER) $(POSTGRES_DB) > $(RESTORE_DB_FOR_DEV_FILE_PATH)

restore_db:
	make drop_db
	docker cp $(RESTORE_DB_FILE_PATH) $(DOCKER_POSTGRES_NAME):/tmp/$(RESTORE_DB_FILE)
	docker exec -it $(DOCKER_POSTGRES_NAME) pg_restore -U $(POSTGRES_USER) \
		-Fc --create --exit-on-error \
		--dbname postgres \
		--jobs $(RESTORE_DB_JOBS) \
		/tmp/$(RESTORE_DB_FILE)

restore_db_for_dev:
	make drop_db
	make create-postgres-db
	docker cp $(RESTORE_DB_FOR_DEV_FILE_PATH) $(DOCKER_POSTGRES_NAME):/tmp/$(RESTORE_DB_FOR_DEV_FILE)
	docker exec -it $(DOCKER_POSTGRES_NAME) psql -U $(POSTGRES_USER) $(POSTGRES_DB) -f /tmp/$(RESTORE_DB_FOR_DEV_FILE)
	docker exec -it $(DOCKER_POSTGRES_NAME) rm /tmp/$(RESTORE_DB_FOR_DEV_FILE)

clone_prod_db:
	mkdir -p var/backups/
	make prod__backup_db_for_dev
	scp $(PROD_LOGIN):$(PROD_DIR)/var/backups/$(RESTORE_DB_FOR_DEV_FILE) var/backups/
	make restore_db_for_dev

test:
	if (docker ps | grep "$(DOCKER_APP_NAME)"); then \
	    $(call docker_exec, app test); \
	elif [ -a ./app ]; then \
		app test; \
	fi ;

makemessages:
	$(call docker_exec, bin/django makemessages -l $(LANG) --extension=html,jinja)

compilemessages:
	$(call docker_exec, bin/django compilemessages -l $(LANG))

prod__backup_db:
	ssh $(PROD_LOGIN) "cd $(PROD_DIR) && make backup_db"

prod__backup_db_for_dev:
	ssh $(PROD_LOGIN) "cd $(PROD_DIR) && make backup_db_for_dev"

clean_prod_backups:
	find var/backups/* -type f -mtime +2 -exec rm {} \;
	for i in `find var/backups/*.bak -type f ! -path $$(find var/backups/* -printf '%p\n' | sort -r | head -1)`;  do tar -czvf $$i.tar.gz $$i; rm $$i; done

.PHONY: clean static reload create_db_user create_db drop_db backup_db backup_db_for_dev \
	restore_db restore_db_for_dev clone_prod_db makemessages compilemessages \
	prod__backup_db prod__backup_db_for_dev

check-docker-db:
	@docker ps | grep postgres || echo "Not found";

check-docker-redis:
	@docker ps | grep $(DOCKER_REDIS_NAME) || echo "Not found";

check-docker-app:
	@docker ps | grep crm-core-r3sourcer || echo "Not found";

check-docker-rabbit_mq:
	@docker ps | grep $(DOCKER_RABBIT_MQ_NAME) || echo "Not found";

var/make-docker-postgres:
	@$(call docker_run,postgres:$(PG_VERSION),$(DOCKER_POSTGRES_NAME),,$(POSTGRES_CONTAINER_IP)) \

var/make/docker-redis:
	@$(call docker_run,redis:$(REDIS_VERSION),$(DOCKER_REDIS_NAME),,$(REDIS_CONTAINER_IP))

var/make/docker-rabbitmq:
	@$(call docker_run,rabbitmq:$(RABBIT_MQ_VERSION),$(DOCKER_RABBIT_MQ_NAME),,$(RABBIT_MQ_CONTAINER_IP))

var/make/create-docker-nginx:
	sudo mkdir -p $(NGINX_VOLUME)/conf $(NGINX_VOLUME)/$(DOCKER_APP_NAME)/static/ $(NGINX_VOLUME)/$(DOCKER_APP_NAME)/media/ \
	    $(LETSENCRYPT_CERTS_PATH)
	sudo chmod -R 775 $(NGINX_VOLUME)
	if !(docker ps -a| grep " nginx$$"); then \
        docker run -itd --name nginx \
            --volume "$(LETSENCRYPT_CERTS_PATH):$(DOCKER_NGINX_CERTS_PATH)" \
            --volume "$(NGINX_VOLUME):/www:ro" \
            --volume "$(NGINX_VOLUME)/conf/:/etc/nginx/conf.d/:ro" \
            --volume "$(CURRENT_PATH)/conf/production/nginx.conf:/etc/nginx/nginx.conf:ro" \
            -p $(DOCKER_NGINX_HTTP_PORT):80 \
            -p $(DOCKER_NGINX_HTTPS_PORT):443 \
            nginx; \
        $(call docker_connect,nginx,$(NGINX_CONTAINER_IP)); \
	fi;
	@touch $@

rm-docker-nginx:
	if docker ps | grep " nginx"; then \
        docker stop nginx; \
    fi ;
	if docker ps -a | grep " nginx"; then \
        docker rm nginx; \
    fi ;

rm-docker-app:
	@if (docker ps | grep " r3sourcer-$(DOCKER_APP_NAME)"); then \
	    docker stop r3sourcer-$(DOCKER_APP_NAME); \
	fi ;
	@if (docker ps -a | grep " r3sourcer-$(DOCKER_APP_NAME)"); then \
	    docker rm r3sourcer-$(DOCKER_APP_NAME); \
	fi ;
	@rm -f var/make/create-app

var/make/create-app:
	@sudo cp $(PRIVATE_REPO_KEY) var/id_rsa
	@sudo chmod go+r var/id_rsa
	echo "Build docker for prod"
	docker build \
         --build-arg "PRIVATE_REPO_KEY=var/id_rsa" \
         --build-arg "USER_APP=$(SYSTEM_USER)" \
         -t r3sourcer-$(DOCKER_APP_NAME)-image \
         -f conf/docker/Dockerfile.prod .
	sudo rm -f var/id_rsa
	make run-container
	touch $@

run-container:
	$(call nginx_root$(USE_NGINX_DOCKER))
	if test "$(DJANGO_UWSGI_PORT)" = ""; then \
        docker run -itd \
            --dns $(DOCKER_DNS_SERVER) \
            --link "$(DOCKER_POSTGRES_NAME):$(POSTGRES_HOST)" \
            --link "$(DOCKER_REDIS_NAME):$(REDIS_HOST)" \
            --link "$(DOCKER_RABBIT_MQ_NAME):$(RABBIT_MQ_HOST)" \
            --volume "$(CURRENT_PATH)/dependencies/:$(DOCKER_BASE_DIR)/dependencies:ro" \
            --volume "$(CURRENT_PATH)/helpers:$(DOCKER_BASE_DIR)/helpers:ro" \
            --volume "$(CURRENT_PATH)/conf:$(DOCKER_BASE_DIR)/conf" \
            --volume "$(CURRENT_PATH)/docker-entrypoint.sh:$(DOCKER_BASE_DIR)/docker-entrypoint.sh" \
            --volume "$(NGINX_SITE_VOLUME):$(DOCKER_BASE_DIR)/var/www/:rw" \
            --env-file ".env_defaults" --env-file ".env" \
            -e WEBUI_APP_DIR=$(WEBUI_APP_DIR) \
            --name r3sourcer-$(DOCKER_APP_NAME) \
            --restart on-failure \
            r3sourcer-$(DOCKER_APP_NAME)-image; \
    else \
        docker run -itd \
            --dns $(DOCKER_DNS_SERVER) \
            --link "$(DOCKER_POSTGRES_NAME):$(POSTGRES_HOST)" \
            --link "$(DOCKER_REDIS_NAME):$(REDIS_HOST)" \
            --link "$(DOCKER_RABBIT_MQ_NAME):$(RABBIT_MQ_HOST)" \
            --volume "$(CURRENT_PATH)/dependencies/:$(DOCKER_BASE_DIR)/dependencies:ro" \
            --volume "$(CURRENT_PATH)/helpers:$(DOCKER_BASE_DIR)/helpers:ro" \
            --volume "$(CURRENT_PATH)/conf:$(DOCKER_BASE_DIR)/conf" \
            --volume "$(CURRENT_PATH)/docker-entrypoint.sh:$(DOCKER_BASE_DIR)/docker-entrypoint.sh" \
            --volume "$(NGINX_SITE_VOLUME):$(DOCKER_BASE_DIR)/var/www/:rw" \
            --env-file ".env_defaults" --env-file ".env" \
            -e WEBUI_APP_DIR=$(WEBUI_APP_DIR) \
            --name r3sourcer-$(DOCKER_APP_NAME) \
            --restart on-failure \
            -p "$(DJANGO_UWSGI_PORT):8081" \
            r3sourcer-$(DOCKER_APP_NAME)-image; \
    fi;
	$(call docker_connect,r3sourcer-$(DOCKER_APP_NAME),$(REMOTE_CONTAINER_IP));
	make user_permissions;


restart:
	docker restart r3sourcer-$(DOCKER_APP_NAME)

rebuild:
	git pull
	make clean && make
	docker restart nginx

update:
	git pull
	make migrate
	make static
	make reload

app-logs:
	@docker logs -f --tail 10 r3sourcer-$(DOCKER_APP_NAME)

nginx-logs:
	@docker logs -f --tail 20 nginx

runserver:
	@$(call docker_exec, bin/django runserver 0.0.0.0:$(DJANGO_UWSGI_PORT), -it)

pip-install:
	@$(call docker_exec, bin/pip install -r dependencies/pip_py3.txt)

static:
	@$(call docker_exec, bin/django collectstatic --noinput)

migrate:
	@$(call docker_exec, bin/django migrate, -it)

makemigrations:
	@$(call docker_exec, bin/django makemigrations, -it)

reload:
	@$(call docker_exec, touch var/run/uwsgi_reload)

bash-app:
	@$(call docker_exec, bash, -it)

bash-db:
	@docker exec -it $(DOCKER_POSTGRES_NAME) bash

shell_plus:
	@$(call docker_exec, bin/django shell_plus, -it)

supervisord:
	@$(call docker_exec, bin/_supervisord)

supervisor:
	@$(call supervisor, status all)

supervisor-stop:
	@$(call supervisor, stop all)

supervisor-restart:
	@$(call supervisor, restart all)

restart-uwsgi:
	@$(call supervisor, restart uwsgi)

restart-celery:
	@$(call supervisor, restart celery-worker)

restart-celerycam:
	@$(call supervisor, restart celerycam)

restart-celery-beat:
	@$(call supervisor, restart celery-beat)

create-superuser:
	@$(call docker_exec, bin/django createsuper, -it)

docker-app-ip:
	@echo "Container IP: $$(docker inspect --format "{{ .NetworkSettings.IPAddress }}" r3sourcer-$(DOCKER_APP_NAME))"

docker-start-all:
	docker start $(DOCKER_POSTGRES_NAME) $(DOCKER_REDIS_NAME) $(DOCKER_RABBIT_MQ_NAME) $(DOCKER_CLICKHOUSE_NAME) \
	    r3sourcer-$(DOCKER_APP_NAME)


var/make/webui-app:
	echo "WEB-UI installation..."; \
	if ! ls $(WEBUI_APP_DIR); then \
		git clone git@bitbucket.org:r3sourcer_1/endless_webui.git $(WEBUI_APP_DIR); \
	else \
		cd $(WEBUI_APP_DIR) && git pull && cd ..; \
	fi; \
	$(call nginx_root$(USE_NGINX_DOCKER)) \
	mkdir -p $(NGINX_VOLUME)/$(DOCKER_APP_NAME)/webui/; \
	mkdir -p var/www/webui; \
	sudo chmod -R 775 $(NGINX_VOLUME)/$(DOCKER_APP_NAME)/webui/; \
	if ! docker ps -a | grep "webui-$(DOCKER_APP_NAME)$$"; then \
		docker build --tag webui-$(DOCKER_APP_NAME)-image $(WEBUI_APP_DIR); \
		docker run -itd \
            --name webui-$(DOCKER_APP_NAME) \
            -v $(NGINX_SITE_VOLUME)$(WEBUI_APP_DIR):/www/ \
            -v $(shell pwd)/$(WEBUI_APP_DIR)/:/code/ \
            --env-file ".env_defaults" --env-file ".env" \
            webui-$(DOCKER_APP_NAME)-image; \
	fi; \
	echo "WEB-UI successfully installed.";

var/make/docker-clickhouse:
	export LOGGER_PASSWORD="$(LOGGER_PASSWORD)" \
	        && export LOGGER_USER="$(LOGGER_USER)" \
	        && envsubst '$${LOGGER_USER} $${LOGGER_PASSWORD}' < conf/templates/users.xml > $(CURRENT_PATH)/users.xml; \
	if !(docker ps -a| grep " $(DOCKER_CLICKHOUSE_NAME)$$"); then \
		sudo chmod u+x clickhouse-entrypoint.sh; \
		docker run \
			--volume "$(CURRENT_PATH)/clickhouse-entrypoint.sh:/var/lib/clickhouse/clickhouse-entrypoint.sh" \
			--volume "$(CURRENT_PATH)/users.xml:/etc/clickhouse-server/users.xml" \
			--entrypoint /var/lib/clickhouse/clickhouse-entrypoint.sh \
		 	-d --name $(DOCKER_CLICKHOUSE_NAME) --ulimit nofile=262144:262144 yandex/clickhouse-server; \
		$(call docker_connect,$(DOCKER_CLICKHOUSE_NAME),$(CLICKHOUSE_CONTAINER_IP)); \
	fi ;


user_permissions:
	docker exec -it -u 0 r3sourcer-$(DOCKER_APP_NAME) chown $(SYSTEM_USER):$(SYSTEM_USER) var/www/static -R;
	docker exec -it -u 0 r3sourcer-$(DOCKER_APP_NAME) chown $(SYSTEM_USER):$(SYSTEM_USER) var/www/media -R;

prepare-compose:
	make var/make var/tmp var/run
	if test $(PRIVATE_REPO_KEY) = "" || ! ls $(PRIVATE_REPO_KEY); then \
        echo "You should define private key for repo `PRIVATE_REPO_KEY` in .env"; \
        exit 1; \
    fi;
	if test $(JWT_RS256_PRIVATE_KEY_PATH) = "" || ! ls $(JWT_RS256_PRIVATE_KEY_PATH); then \
        echo "You should define private key for repo `JWT_RS256_PRIVATE_KEY_PATH` in .env"; \
        exit 1; \
    fi;
	if test $(JWT_RS256_PUBLIC_KEY_PATH) = "" || ! ls $(JWT_RS256_PUBLIC_KEY_PATH); then \
        echo "You should define public key for repo `JWT_RS256_PUBLIC_KEY_PATH` in .env"; \
        exit 1; \
    fi;
	sudo cp $(PRIVATE_REPO_KEY) conf/id_rsa
	sudo cp $(JWT_RS256_PRIVATE_KEY_PATH) conf/jwtRS256
	sudo cp $(JWT_RS256_PUBLIC_KEY_PATH) conf/jwtRS256.pub
	make var/make/webui-app
	export LOGGER_PASSWORD="$(LOGGER_PASSWORD)" \
	    && export LOGGER_USER="$(LOGGER_USER)" \
	    && envsubst '$${LOGGER_USER} $${LOGGER_PASSWORD}' < conf/templates/users.xml > $(CURRENT_PATH)/users.xml

load_fixtures:
	# $(call docker_compose_exec, bin/django load_workflow)
	# $(call docker_compose_exec, bin/django load_hr_workflow)
	$(call docker_compose_exec, bin/django load_form_builder)
	$(call docker_compose_exec, bin/django loaddata r3sourcer/apps/core/fixtures/company_localization.json)
	$(call docker_compose_exec, bin/django loaddata r3sourcer/apps/core/fixtures/extranet_navigation.json)
	$(call docker_compose_exec, bin/django loaddata r3sourcer/apps/sms_interface/fixtures/sms_templates.json)
	$(call docker_compose_exec, bin/django loaddata r3sourcer/apps/email_interface/fixtures/email_templates.json)

update_web_staging:
	docker-compose stop web
	git pull origin develop
	docker-compose start web

update_web_production:
	docker-compose stop web
	git pull origin master
	docker-compose start web

web_logs:
	docker-compose logs -f --tail 10 web

restart_web:
	docker-compose restart web
	make web_logs

rebuild_web:
	docker-compose stop web
	docker-compose rm -f web
	docker-compose up --build -d web
	make web_logs

nginx_config_docker:
	if [ ! -d "/etc/letsencrypt" ]; then \
		sudo mkdir /etc/letsencrypt; \
	fi;
	docker-compose exec web app nginx_config --site_root=$(DOCKER_BASE_DIR) > conf/docker/nginx.conf
	docker-compose stop nginx
	docker-compose rm -f nginx
	docker-compose up --build -d nginx

generate_jwt_rsa:
	yes y | ssh-keygen -t rsa -b 4096 -f conf/jwtRS256.key -q -N "" > /dev/null
	openssl rsa -in conf/jwtRS256.key -pubout -outform PEM -out conf/jwtRS256.key.pub
	if ! grep -q "JWT_RS256_PRIVATE_KEY_PATH" .env; then \
		echo "JWT_RS256_PRIVATE_KEY_PATH=conf/jwtRS256.key" >> .env; \
	fi;
	if ! grep -q "JWT_RS256_PUBLIC_KEY_PATH" .env; then \
		echo "JWT_RS256_PUBLIC_KEY_PATH=conf/jwtRS256.key.pub" >> .env; \
	fi;

regular_backup:
	$(call create_backup,regular,$(CURRENT_DATETIME).tar.gz)

media_backup:
	mkdir -p media_backup
	make media_backup_clean
	tar -czf media_backup/media.tar.gz /home/ubuntu/endless_project/var/www/media/
	aws s3 cp media_backup/media.tar.gz $(S3_BACKUP_FOLDER)Media/media_$(CURRENT_DATETIME).tar.gz

media_backup_clean:
	rm -f media_backup/media.tar.gz

get_backups_from_remote:
	mkdir -p media_backup/from_remote
	aws s3 sync $(S3_BACKUP_FOLDER) media_backup/from_remote
