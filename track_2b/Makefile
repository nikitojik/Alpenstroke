.PHONY: run up down logs seed test eval

run:
	docker compose up --build

up:
	docker compose up --build -d
	@echo "Alpenstroke: http://localhost:$${APP_PORT:-8000}"

down:
	docker compose down

logs:
	docker compose logs -f app

seed:
	docker compose exec app python -m scripts.seed

test:
	docker run --rm -v "$(CURDIR)/src:/src" -w /src python:3.12-slim \
		sh -c "pip install -q -r requirements.txt && python -m pytest -q"
eval:
	docker compose run --rm --build --no-deps --user "$$(id -u):$$(id -g)" \
		-v "$(CURDIR)/data:/data" app python -m scripts.evaluate $(ARGS)