EXTRA_ARGS?=

run:
	source .venv/bin/activate && poetry run metadata-processing --env development

# Dev
DOCKER_DEV_CONF?=-f docker-compose.metadata-processing.yml -f docker-compose.metadata-processing.dev.yml

dev-docker-build:
	TAG=dev docker-compose ${DOCKER_DEV_CONF} build $(EXTRA_ARGS)

dev-docker-up:
	TAG=dev docker-compose ${DOCKER_DEV_CONF} up -d
	TAG=dev docker-compose ${DOCKER_DEV_CONF} logs -f

dev-docker-down:
	TAG=dev docker-compose ${DOCKER_DEV_CONF} down -v

# Staging
DOCKER_STAGING_CONF?=-f docker-compose.metadata-processing.yml -f docker-compose.metadata-processing.staging.yml

staging-docker-build:
	TAG=staging docker-compose ${DOCKER_STAGING_CONF} build $(EXTRA_ARGS)

staging-docker-up:
	TAG=staging docker-compose ${DOCKER_STAGING_CONF} up -d -V
	TAG=staging docker-compose ${DOCKER_STAGING_CONF} logs -f

staging-docker-logs:
	TAG=staging docker-compose ${DOCKER_STAGING_CONF} logs -f

staging-docker-down:
	TAG=staging docker-compose ${DOCKER_STAGING_CONF} down

staging-docker-cycle:
	make staging-docker-down
	make staging-docker-build
	make staging-docker-up
	make staging-docker-logs

# Prod
docker-build:
	TAG=latest docker-compose -f docker-compose.metadata-processing.yml build

docker-up:
	TAG=latest docker-compose -f docker-compose.metadata-processing.yml up -d -V

docker-down:
	TAG=latest docker-compose -f docker-compose.metadata-processing.yml down

docker-push:
	docker save -o tezland-metadata-processing-latest.tar tezland/metadata-processing:latest
	rsync tezland-metadata-processing-latest.tar tezland-metadata-latest.tar docker-compose.metadata-processing.yml tz1and.com:/home/yves/docker
	ssh tz1and.com "source .profile; cd docker; docker load -i tezland-metadata-processing-latest.tar; docker load -i tezland-metadata-latest.tar"
#	; rm tezland-metadata-processing-latest.tar"
	rm tezland-metadata-processing-latest.tar
