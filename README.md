# AI Operations Automation Agent

An agentic AI pipeline that takes an unstructured incoming request (email, support ticket, chat message), classifies it, extracts structured data, looks up live order/shipment status, applies business rules, generates a response, notifies a human channel, and **measures its own performance** — built to demonstrate the exact stack used in logistics/ops-automation job descriptions (Python, FastAPI, LLMs, Agentic AI, Make.com, PostgreSQL, REST APIs, Docker).

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
(classify)  (status)   (decide)     (Slack/log)
        │
        ▼
   PostgreSQL (cases + full step-by-step trace)
        │
        ▼
   Metrics Dashboard (/dashboard)
```

The agent doesn't just call an LLM once — it **decides at runtime** which tool to call next based on the previous tool's output (e.g. it escalates instead of auto-responding when business rules flag a customs hold or a 3+ day delay). Every step is logged to `agent_steps` for auditability.

## Project structure

```
ai-operations-automation/
├── backend/
│   ├── main.py              # FastAPI app entrypoint
│   ├── agents/agent.py      # orchestration — the "agentic" core
│   ├── api/routes.py        # /api/requests, /api/cases, /api/metrics
│   ├── services/            # llm_service, order_service, notification_service
│   ├── models/models.py     # SQLAlchemy models (Case, AgentStep)
│   └── db.py
├── automation/
│   └── make-workflow.json   # Make.com scenario blueprint + rebuild steps
├── data/
│   ├── generate_test_cases.py
│   └── run_test_cases.py    # runs 100 cases against the live API, prints real metrics
├── dashboard/index.html     # live metrics dashboard
├── tests/test_agent.py      # unit tests, no Docker needed
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## Quick start (Docker — recommended)

Needs only Docker + Docker Compose installed. No API keys required to run it end-to-end (uses the built-in rule-based "mock" LLM provider).

```bash
cd ai-operations-automation
cp .env.example .env
docker compose up --build
```

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

You'll get back the classified issue type, the order status, the generated response, and the processing time — refresh `/dashboard` to see it reflected in the metrics.

## Running the 100-case measured benchmark

This is what generates the real (not fabricated) numbers for your resume/portfolio.

```bash
# with the API already running via docker compose:
pip install httpx
python data/generate_test_cases.py     # writes data/test_cases.csv (100 rows)
python data/run_test_cases.py --base-url http://localhost:8000
```

It prints something like:

```
=== Results ===
Cases processed:            100
Classification accuracy:    91.0%
Avg. processing time:       0.04s
P95 processing time:        0.09s
Escalation rate:            18.0%
Time saved vs 5-min manual: 99.9%
```

...and a ready-to-paste CV line at the bottom. **These are your own real numbers from your own run** — re-run it and quote whatever you actually get, don't copy the example above verbatim.

## Running locally without Docker

```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env   # defaults to a local SQLite file — no Postgres needed

uvicorn backend.main:app --reload --app-dir .
```

(To use Postgres instead of SQLite locally, edit `.env` and uncomment the `DATABASE_URL=postgresql://...` line, pointing it at your own Postgres instance.)

Run unit tests (no DB needed):

```bash
pip install pytest
pytest tests/
```

## Switching to a real LLM

By default `LLM_PROVIDER=mock` in `.env` — a deterministic rule-based classifier that mimics exactly what an LLM call returns, so the project runs with zero cost and zero keys. To use a real model:

```
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

or

```
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

No other code changes needed — `backend/services/llm_service.py` is the only file that branches on provider.

## Make.com integration

`automation/make-workflow.json` documents the scenario: **Webhook → HTTP (calls this API) → Router (resolved/escalated) → Slack notify → Google Sheets log**. Make.com scenarios are built in their visual editor, not imported from raw JSON, so this file is a precise blueprint plus step-by-step rebuild instructions — open it and follow "how_to_rebuild_in_make" to recreate it in ~10 minutes with a free Make.com account, using this API's `/api/requests` endpoint as the HTTP module's target (use `ngrok http 8000` to expose your local API for testing).

## Example use case this was built for

**E-commerce / logistics delayed-delivery automation** (directly relevant to logistics/cross-border-parcel companies):

> "My package hasn't arrived yet. Order #12345 was supposed to arrive yesterday."

The agent extracts the order number, classifies it as `delayed_delivery`, calls the shipment-status API, checks business rules (auto-respond vs. escalate based on how many days late / customs hold), generates a contextual reply, logs the case, and notifies the ops channel — end to end in well under a second.

## Suggested CV entry

```
AI Operations Automation Agent
Python, FastAPI, LLMs, Agentic AI, Make.com, PostgreSQL, REST APIs, Docker

- Built an AI-powered operations workflow that converts unstructured requests
  into structured actions using LLMs, Python, and REST APIs.
- Automated request classification, data extraction, and database updates
  through an agentic workflow (LLM -> order API -> business rules -> response)
  and a Make.com automation scenario.
- Integrated external APIs with FastAPI services to retrieve data, apply
  business rules, and generate contextual responses, with full per-step
  execution tracing for auditability.
- Measured processing time, classification accuracy, and escalation rate
  across a 100-case test dataset via an automated benchmark script and a
  live metrics dashboard.
- Containerized the full stack (API + PostgreSQL) with Docker Compose for
  one-command setup.
```
