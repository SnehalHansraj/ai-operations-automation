# OpsPilot: AI Operations Automation Agent

An agentic AI pipeline that takes an unstructured incoming request (email, support ticket, chat message), classifies it, extracts structured data, looks up live order/shipment status, applies business rules, generates a response, notifies a human channel, and **measures its own performance**. Stack: Python, FastAPI, LLMs (local Qwen3 via Ollama, routed through **LiteLLM**), Agentic AI, Make.com, PostgreSQL/SQLite, REST APIs, Docker.

## Architecture

```
Incoming Request (webhook / API call)
        │
        ▼
   AI AGENT (backend/agents/agent.py)
        │
   ┌────┼────────────┬───────────────┐
   ▼    ▼             ▼               ▼
 LLM   Order API   Business Rules   Notifier
(classify)  (status)   (decide)   (Slack / email)
   │
   └─ LiteLLM → Ollama (Qwen3) | OpenAI | Anthropic
        │
        ▼
   PostgreSQL / SQLite (cases + full step-by-step trace)
        │
        ▼
   Metrics Dashboard (/dashboard)
```

The agent doesn't just call an LLM once: it **decides at runtime** which tool to call next based on the previous tool's output (e.g. it escalates instead of auto-responding when business rules flag a customs hold or a 3+ day delay). Every step is logged to `agent_steps` for auditability.

## Project structure

```
ai-operations-automation/
├── backend/
│   ├── main.py              # FastAPI app entrypoint
│   ├── agents/agent.py      # orchestration: the "agentic" core
│   ├── api/routes.py        # /api/requests, /api/cases, /api/metrics
│   ├── services/            # llm_service, order_service, notification_service
│   ├── models/models.py     # SQLAlchemy models (Case, AgentStep)
│   └── db.py
├── automation/
│   └── make-workflow.json   # Make.com scenario blueprint + rebuild steps
├── data/
│   ├── generate_test_cases.py
│   ├── run_test_cases.py    # runs 100 cases against the live API, prints metrics
│   └── run_demo_cases.py    # 8 curated end-to-end demo scenarios
├── dashboard/index.html     # live metrics dashboard
├── tests/
│   ├── test_agent.py        # unit tests for the agent pipeline
│   ├── test_litellm.py      # LiteLLM provider tests (offline, no model needed)
│   └── test_email.py        # manual SMTP check (sends a real email)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## LLM providers (via LiteLLM)

`backend/services/llm_service.py` is the only file that branches on provider. Choose one in `.env`:

| `LLM_PROVIDER` | What it does |
|---|---|
| `litellm` | Calls go through [LiteLLM](https://github.com/BerriAI/litellm)'s unified API. Default model: local `qwen3:4b` on Ollama |
| `ollama` | Calls Ollama's REST API directly |
| `openai` / `anthropic` | Cloud models via their official SDKs |
| `mock` | Deterministic rule-based classifier: no model, no keys, zero cost |

With `litellm`, switching models is one env variable, with no code change:

```
LLM_PROVIDER=litellm
LITELLM_MODEL=ollama_chat/qwen3:4b          # default (local, private, free)
# LITELLM_MODEL=gpt-4o-mini                 # + OPENAI_API_KEY
# LITELLM_MODEL=anthropic/claude-sonnet-4-6 # + ANTHROPIC_API_KEY
```

The LiteLLM path reuses the same prompts, JSON extraction and validation as the direct Ollama path, and strips Qwen3's `<think>` blocks before parsing.

## Running locally

Needs Python 3.11+ and [Ollama](https://ollama.com) with the model pulled (`ollama pull qwen3:4b`). To run without a model, set `LLM_PROVIDER=mock`.

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env   # defaults to a local SQLite file, no Postgres needed

uvicorn backend.main:app --reload
```

(To use Postgres instead of SQLite, edit `.env` and uncomment the `DATABASE_URL=postgresql://...` line.)

Once it's up:

- API root: http://localhost:8000
- Interactive API docs (Swagger): http://localhost:8000/docs
- Metrics dashboard: http://localhost:8000/dashboard

Send a test request:

```bash
curl -X POST http://localhost:8000/api/requests \
  -H "Content-Type: application/json" \
  -d '{"text": "My package hasn'"'"'t arrived yet. Order #12345 was supposed to arrive yesterday."}'
```

You'll get back the classified issue type, the order status, the generated response, and the processing time. Refresh `/dashboard` to see it reflected in the metrics.

## Running with Docker

```bash
cp .env.example .env
docker compose up --build
```

Inside the container `localhost` is the container itself, so to reach Ollama on your machine set `OLLAMA_BASE_URL=http://host.docker.internal:11434` in `.env` (or use `LLM_PROVIDER=mock`).

## Tests

```bash
pip install pytest
python -m pytest tests/test_agent.py tests/test_litellm.py -v
```

These need no database, no Ollama and no API keys: `test_litellm.py` uses LiteLLM's built-in `mock_response`, so the real `litellm.completion()` path runs offline.

`tests/test_email.py` is a manual SMTP check that sends a real email using the `SMTP_*` settings in `.env`: run it with `python tests/test_email.py`.

## Measured benchmark (100 cases)

```bash
# with the API running:
python data/generate_test_cases.py     # writes data/test_cases.csv (100 rows)
python data/run_test_cases.py --base-url http://localhost:8000
```

It reports classification accuracy, average and P95 processing time, escalation rate, and time saved versus a 5-minute manual baseline, all measured from the actual run.

For a short guided walkthrough of 8 scenarios (auto-resolution, delay, damage, wrong item, refund, cancellation, customs escalation with email, missing order ID):

```bash
python data/run_demo_cases.py
```

## Make.com integration

`automation/make-workflow.json` documents the scenario: **Webhook → HTTP (calls this API) → Router (resolved/escalated) → Slack notify → Google Sheets log**. Make.com scenarios are built in their visual editor, not imported from raw JSON, so this file is a precise blueprint plus step-by-step rebuild instructions. Follow "how_to_rebuild_in_make" to recreate it in ~10 minutes with a free Make.com account, using this API's `/api/requests` endpoint as the HTTP module's target (use `ngrok http 8000` to expose your local API for testing).

## Example use case

**E-commerce / logistics delayed-delivery automation:**

> "My package hasn't arrived yet. Order #12345 was supposed to arrive yesterday."

The agent extracts the order number, classifies it as `delayed_delivery`, calls the shipment-status API, checks business rules (auto-respond vs. escalate based on how many days late / customs hold), generates a contextual reply, logs the case, and notifies the ops channel by Slack or email.
