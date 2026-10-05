# Alpenstroke

Describe a workout in plain words. Alpenstroke turns it into structured data, tracks your training load, and uses [Apertus](https://huggingface.co/swiss-ai), Switzerland's fully open LLM, to explain what's going on and plan your next week. It is fully self-hostable: your training data never has to leave your own server.

> Built for [Hack Apertus 2026](https://hackapertus.ch/), Track 2B (Own Project). The project lives in [`track_2b/`](track_2b/), following the official template.

---

## The problem

Competitive swimmers log a lot of training, but most logs are either a paper notebook or a rigid app where you fill in every set by hand. Neither one tells you the thing that matters most before a meet: *am I overdoing it?*

Warning signs like rising effort at the same volume, recurring cramps, or a sudden jump in volume are usually spread across weeks of notes. A coach catches them. A swimmer training alone often doesn't.

## How it works

```
"10x100 free on 1:30, last three were hard, calf cramp again"
                │
                ▼
   ┌─────────────────────────┐
   │ 1. Parse (Apertus)      │  free text in any language → sets, effort, symptoms
   └────────────┬────────────┘
                ▼  swimmer confirms the draft
   ┌─────────────────────────┐
   │ 2. Metrics (plain code) │  session load, weekly volume, acute:chronic ratio
   └────────────┬────────────┘
                ▼
   ┌─────────────────────────┐
   │ 3. Analyze (Apertus)    │  metrics + recent notes → concerns + recommendation
   └────────────┬────────────┘
                ▼
   ┌─────────────────────────┐
   │ 4. Plan (Apertus)       │  goal event + date → next 7 days
   └─────────────────────────┘
```

**Design principle: code does the math, the model does the language.** Training-load metrics, weekly volume targets, dates and totals are computed deterministically and unit-tested. Apertus does what a language model is good at: reading free-text logs and explaining the numbers in plain words. Every model answer is validated against a schema and checked by code before it is stored:

- **Grounding:** the model may only raise a problem with a body part the swimmer actually mentioned. Invented injuries trigger a retry.
- **Plan rules:** no more than two hard days in a row, a session is never shorter than its main set, races only on the goal date, a caution is required when the analysis found a symptom.
- **Volume:** the weekly target comes from code. If the model misses it, the days are scaled proportionally.
- **Honest confidence:** with less than four weeks of history there is no target, no week-over-week comparison, and confidence is forced to low.

## Features

- [x] Natural-language workout logging in any language, with a confirm-before-save step
- [x] Training-load metrics: session load (RPE × minutes), weekly volume, acute:chronic workload ratio
- [x] Per-workout analysis with concerns, a recommendation and a confidence level
- [x] Weekly plan toward a goal event and date
- [x] Feedback: mark advice as helpful or not
- [x] Web UI with no external CDNs, plus a JSON API
- [x] One-command self-hosted deployment

## Run it

Requirements: Docker with Compose, and an OpenAI-compatible endpoint serving Apertus.

```bash
git clone https://github.com/nikitojik/alpenstroke.git
cd alpenstroke/track_2b
cp .env.example .env        # set LLM_API_KEY (and LLM_NAME / LLM_BASE_URL if needed)
make run
```

Open http://localhost:8000. On first start the database is migrated and three demo swimmers are created:

| Swimmer | What the data shows |
|---|---|
| Demo: Steady | six even weeks, nothing to fix |
| Demo: Spike | last week's volume jumped (ACWR 1.63, overload) |
| Demo: Cramps | recurring calf cramps on butterfly in the notes |

Other targets: `make up` (background), `make down`, `make logs`, `make seed` (recreate the demo swimmers), `make test` (unit tests, no network or database).

## Configuration

| Variable | Description | Default |
|---|---|---|
| `LLM_NAME` | Model name on the endpoint | `swiss-ai/apertus-70b-instruct` |
| `LLM_BASE_URL` | Any OpenAI-compatible endpoint serving Apertus | `https://api.publicai.co/v1` |
| `LLM_API_KEY` | API key for that endpoint | required |
| `POSTGRES_PASSWORD` | Database password, set your own on a server | `alpenstroke` |
| `APP_PORT` | Port on the host | `8000` |

## Sovereign by design

- **No third parties at runtime.** Fonts and scripts are served by the app itself. The only outbound connection is to `LLM_BASE_URL`.
- **Swap the model endpoint with one variable.** Point `LLM_BASE_URL` at a hosted Apertus endpoint, or at your own vLLM or llama.cpp server running Apertus on-premise. The app code doesn't change.
- **Your data stays yours.** Training logs and health notes live in your own Postgres. The athlete's name is never sent to the model.

## API

Interactive docs at http://localhost:8000/docs.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health`, `/health/db` | Liveness and database checks |
| `POST` | `/athletes` | Create an athlete profile |
| `GET` / `PATCH` | `/athletes/{id}` | Get or update a profile |
| `POST` | `/workouts/parse` | Free text → structured workout draft (not saved) |
| `POST` | `/workouts` | Save a confirmed workout |
| `GET` | `/workouts?athlete_id={id}` | Workout history |
| `POST` | `/workouts/{id}/analyze` | Analyze a workout in the context of the last six weeks |
| `POST` | `/athletes/{id}/plan` | Generate the next 7 days |

## Project structure

```
track_2b/
  Makefile               make run, up, down, logs, seed, test
  Dockerfile             app image (non-root, healthcheck)
  docker-compose.yml     app + Postgres 16
  technical_report.md    architecture, evaluation, limitations
  src/
    app/
      main.py            FastAPI app
      config.py          settings from LLM_* and DATABASE_URL
      models/            SQLAlchemy models
      schemas/           Pydantic schemas, also used to validate model output
      routers/           JSON API
      web/, templates/   web UI (Jinja2 + HTMX)
      services/
        llm.py           Apertus client: schema-validated JSON with one retry
        parser.py        free text → workout
        metrics.py       deterministic training-load metrics
        grounding.py     body-part grounding check
        analyzer.py      workout analysis
        planner.py       weekly plan and its code checks
    migrations/          Alembic
    scripts/             demo data and demo runners
    tests/               unit tests
  data/                  evaluation data
  docs/                  diagrams and notes
```

## Tech stack

Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 16 · Pydantic · Jinja2 + HTMX · OpenAI-compatible client · Docker Compose · Apertus

## Disclaimer

Alpenstroke is a training aid, not medical advice. Recurring pain, cramps or other symptoms should be discussed with a coach or a medical professional.

## License

[Apache-2.0](LICENSE)

## Team

- Nikita Kolesnikov
