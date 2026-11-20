DEV_PROJECT := kosa-dev-$(shell pwd | cksum | cut -d ' ' -f 1)
COMPOSE := docker compose --env-file .env.example -f compose.yaml -f infra/test.compose.yaml
DEV := $(COMPOSE) -p $(DEV_PROJECT)

.PHONY: help up ps logs down test e2e

help:
	@printf '%s\n' 'make up    Start mock Studio and print its addresses' \
		'make ps    Show local services and ports' \
		'make logs  Follow local service logs' \
		'make down  Stop local services and keep their data' \
		'make test  Run backend tests with an isolated PostgreSQL' \
		'make e2e   Run browser tests with an isolated Studio'

up:
	cd PRJ && $(DEV) up --build --detach --wait --wait-timeout 120 db api worker web
	@cd PRJ && web=$$($(DEV) port web 80) && api=$$($(DEV) port api 8000) && \
		printf 'Web: http://%s/\nAPI: http://%s/docs\n' "$$web" "$$api"

ps:
	cd PRJ && $(DEV) ps

logs:
	cd PRJ && $(DEV) logs --follow --tail=100

down:
	cd PRJ && $(DEV) down

test:
	@cd PRJ || exit 1; \
		project=kosa-test-$$$$; \
		trap 'result=$$?; $(COMPOSE) -p "$$project" --profile test down --rmi local || exit 1; exit "$$result"' EXIT; \
		trap 'exit 130' INT; trap 'exit 143' TERM; \
		$(COMPOSE) -p "$$project" --profile test run --build --rm test

e2e:
	cd PRJ && sh scripts/e2e.sh
