# Alpenstroke
Describe a workout in plain words. Alpenstroke turns it into structured data, tracks your training load, and uses [Apertus](https://huggingface.co/swiss-ai), Switzerland's fully open LLM, to explain what's going on and plan your next week. It is fully self-hostable: your training data never has to leave your own server.

> Built for [Hack Apertus 2026](https://hackapertus.devpost.com/), Track 2B (Own Project).

---

## The problem

Competitive swimmers log a lot of training, but most logs are either a paper notebook or a rigid app where you fill in every set by hand. Neither one tells you the thing that matters most before a meet: *am I overdoing it?*

Warning signs like rising effort at the same volume, recurring cramps, or a stalled event time are usually spread across weeks of notes. A coach catches them. A swimmer training alone often doesn't.

## How it works

```
"10x100 free on 1:30, last three were hard, calf cramp again"
                │
                ▼
   ┌─────────────────────────┐
   │ 1. Parse (Apertus)      │  free text → sets, intervals, effort, symptoms
   └────────────┬────────────┘
                ▼  user confirms
   ┌─────────────────────────┐
   │ 2. Metrics (plain code) │  session load, weekly volume, acute:chronic ratio
   └────────────┬────────────┘
                ▼
   ┌─────────────────────────┐
   │ 3. Analyze (Apertus)    │  metrics + recent notes → concerns + recommendation
   └────────────┬────────────┘
                ▼
   ┌─────────────────────────┐
   │ 4. Plan (Apertus)       │  goal event + date → next week's plan
   └─────────────────────────┘
```

**Design principle: code does the math, the model does the language.** Training-load metrics are computed deterministically and unit-tested. Apertus is used only where a language model is the right tool: understanding free-text logs and explaining the numbers in plain words. Every model response is validated against a schema before it is stored.

## Features

- [ ] Natural-language workout logging with a confirm-before-save step
- [ ] Training-load metrics: session load (RPE × minutes), weekly volume, acute:chronic workload ratio
- [ ] Per-workout analysis with concerns, a recommendation, and a confidence level
- [ ] Weekly plan generation toward a goal event and date
- [ ] Feedback loop: mark advice as helpful or not, fed back into later analyses
- [ ] One-command self-hosted deployment, cloud or local model

## Sovereign by design

- **Runs anywhere.** `docker compose up` starts the API and Postgres. No external CDNs, analytics, or third-party services.
- **Swap the model endpoint with one variable.** Point `APERTUS_BASE_URL` at the Public AI inference API, or at your own vLLM server running Apertus on-premise. The app code doesn't change.
- **Your data stays yours.** Training logs and health notes live in your own database.

## Quickstart

```bash
git clone https://github.com/<you>/Alpenstroke.git
cd Alpenstroke
cp .env.example .env        # add your APERTUS_API_KEY
docker compose up --build
```

Then open http://localhost:8000/docs for the interactive API docs.

### Running against a local Apertus model

```bash
pip install vllm
vllm serve swiss-ai/Apertus-v1.5-8B --port 8001
```

Then set these in `.env`:

```
APERTUS_BASE_URL=http://host.docker.internal:8001/v1
APERTUS_MODEL=swiss-ai/Apertus-v1.5-8B
APERTUS_API_KEY=not-needed
```

## Configuration

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | Postgres connection string | set by `docker-compose.yml` |
| `APERTUS_BASE_URL` | Any OpenAI-compatible endpoint serving Apertus | `https://api.publicai.co/v1` |
| `APERTUS_API_KEY` | API key for that endpoint | — |
| `APERTUS_MODEL` | Model name | `swiss-ai/apertus-70b-instruct` |

## API

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `POST` | `/athletes` | Create an athlete profile |
| `GET` | `/athletes/{id}` | Get a profile |
| `POST` | `/workouts/parse` | Free text → structured workout draft (not saved) |
| `POST` | `/workouts` | Save a confirmed workout |
| `GET` | `/workouts/athlete/{id}` | Workout history |
| `POST` | `/workouts/{id}/analyze` | Analyze a workout in context |
| `POST` | `/athletes/{id}/plan` | Generate next week's plan |

## Evaluation

*Results coming soon.* A set of synthetic athlete scenarios (`evals/scenarios/`) compares Apertus 8B and 70B on:

| Metric | 8B | 70B |
|---|---|---|
| Valid-JSON rate | – | – |
| Overload correctly flagged | – | – |
| Median latency | – | – |
| Tokens per analysis | – | – |

## Project structure

```
app/
  main.py            FastAPI app and router wiring
  config.py          Settings from environment variables
  db.py              SQLAlchemy engine and session
  models.py          ORM models
  schemas.py         Pydantic request/response schemas
  routers/           HTTP endpoints
  services/
    llm.py           Apertus client and schema-validated calls
    metrics.py       Deterministic training-load metrics
scripts/seed.py      Synthetic athletes and workouts for demos and evals
evals/               Model evaluation scenarios and runner
tests/               Unit tests
```

## Tech stack

Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 16 · Pydantic · OpenAI-compatible client · Docker Compose · Apertus

## Disclaimer

Alpenstroke is a training aid, not medical advice. Recurring pain, cramps, or other symptoms should be discussed with a coach or a medical professional.

## License

[Apache-2.0](LICENSE)

## Team

- Nikita Kolesnikov — backend, AI integration