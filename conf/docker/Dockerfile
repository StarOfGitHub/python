FROM python:3.8-buster

WORKDIR /app/
COPY dependencies ./dependencies
COPY helpers ./helpers
COPY ["docker-entrypoint.sh", "Procfile", "README.md", "setup.py", "manage.py", "./"]
RUN curl -sL https://deb.nodesource.com/setup_10.x | bash -
RUN apt-get update && apt-get install -y nodejs
RUN npm i -g bower
RUN mkdir -p r3sourcer var/log var/run var/www var/tmp
RUN pip install -r dependencies/pip_pytest.txt

# available only uwsgi port
EXPOSE 8081
