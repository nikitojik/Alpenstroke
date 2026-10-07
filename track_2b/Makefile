.PHONY: run up down logs seed test eval prod model airgapped airgapped-check airgapped-down

run:
	docker compose up --build

up:
	docker compose up --build -d
	@echo "Alpenstroke: http://localhost:$${APP_PORT:-8000}"

down:
	docker compose down

logs:
	docker compose logs -f alpenstroke

seed:
	docker compose exec alpenstroke python -m scripts.seed

test:
	docker run --rm -v "$(CURDIR)/src:/src" -w /src python:3.12-slim \
		sh -c "pip install -q -r requirements.txt && python -m pytest -q"

eval:
	docker compose run --rm --build --no-deps --user "$$(id -u):$$(id -g)" \
		-v "$(CURDIR)/data:/data" alpenstroke python -m scripts.evaluate $(ARGS)

prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env up --build -d

# ---------- без интернета: Apertus 8B в llama.cpp ----------

GGUF_URL := https://huggingface.co/Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF/resolve/main/apertus-v1.5-8b-text-q4_k_m.gguf
GGUF_SHA := a037df8d87ff6caacee794ee85f55342f2152e0d359b7389033300c3bee5f299
AIRGAPPED := docker compose -f compose.airgapped.yml

model:
	mkdir -p models
	test -f models/apertus-v1.5-8b-text-q4_k_m.gguf || curl -L --fail -o models/apertus-v1.5-8b-text-q4_k_m.gguf "$(GGUF_URL)"
	echo "$(GGUF_SHA)  models/apertus-v1.5-8b-text-q4_k_m.gguf" | shasum -a 256 -c -

airgapped:
	test -f models/apertus-v1.5-8b-text-q4_k_m.gguf || (echo "Run make model first"; exit 1)
	$(AIRGAPPED) up --build -d
	@echo "Loading the model takes a minute or two. Then open http://localhost:8000"

airgapped-check:
	$(AIRGAPPED) exec alpenstroke python -m scripts.egress_check

airgapped-down:
	$(AIRGAPPED) down