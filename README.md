# LUCI CrewAI Service

FastAPI service powering LUCI's AI analysis crews. Runs CrewAI agents for account analysis, coaching, meeting intelligence, and more. Deployed on Railway via Docker.

## Project Structure

```
luci-crews/
├── Dockerfile
├── pyproject.toml
├── railway.json
├── render.yaml
├── README.md
└── src/
    └── luci_crews/
        ├── main.py                  # FastAPI app + crew endpoints
        ├── models.py                # Pydantic request/response models
        ├── config_store.py          # Supabase-backed config persistence
        ├── config_loader.py         # YAML config loading with LRU cache
        ├── ai_settings_helper.py    # Multi-provider LLM fallback
        ├── alert_service.py         # Crew error alerting with dedup
        ├── avoma_mcp.py             # Avoma meeting/transcript access via MCP
        ├── mcp_client.py            # Generic MCP client utilities
        ├── mavenlink_client.py      # Mavenlink API integration
        ├── config/
        │   ├── agents.yaml          # Agent prompt defaults
        │   └── tasks.yaml           # Task prompt defaults
        ├── crews/                   # ~30 specialized CrewAI crews
        │   ├── base_crew.py
        │   ├── account_analysis_crew.py
        │   ├── account_health_crew.py
        │   ├── ae_coaching_crew.py
        │   ├── agenda_generation_crew.py
        │   ├── call_analysis_crew.py
        │   ├── call_verification_crew.py
        │   ├── contextual_drilldown_crew.py
        │   ├── csm_coaching_crew.py
        │   ├── email_draft_crew.py
        │   ├── executive_briefing_crew.py
        │   ├── expansion_specialist_crew.py
        │   ├── feature_extraction_crew.py
        │   ├── implementation_crew.py
        │   ├── meddpicc_gap_actions_crew.py
        │   ├── opportunity_strategy_crew.py
        │   ├── pm_coaching_crew.py
        │   ├── product_intelligence_crew.py
        │   ├── profile_builder_crew.py
        │   ├── project_analysis_crew.py
        │   ├── project_sentiment_crew.py
        │   ├── qbr_summary_crew.py
        │   ├── renewal_readiness_crew.py
        │   ├── sales_pipeline_crew.py
        │   ├── sc_coaching_crew.py
        │   ├── sc_prep_crew.py
        │   ├── sdr_coaching_crew.py
        │   ├── sentiment_crew.py
        │   ├── strategic_action_crew.py
        │   ├── support_coaching_crew.py
        │   └── support_resolution_crew.py
        ├── routes/
        │   ├── analysis.py          # Analysis endpoints
        │   ├── coaching.py          # Coaching endpoints
        │   ├── config.py            # Config CRUD endpoints
        │   ├── health.py            # Health + capabilities
        │   └── studio.py            # Crew Studio dynamic runner
        └── utils/
            ├── json_extractor.py    # LLM response JSON parsing/repair
            ├── streaming.py         # SSE streaming utilities
            ├── account_lookup.py    # Supabase account lookups
            └── data_freshness.py    # Sync staleness tracking
```

## API Endpoints

### Health & Info

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service info and endpoint listing |
| `/health` | GET | Health check (used by Railway) |
| `/api/capabilities` | GET | AI provider status (OpenAI, Anthropic, Google) |

### Crew Endpoints (`/api/crew`)

**Account & Pipeline Analysis**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/crew/sales_pipeline` | POST | Sales pipeline analysis |
| `/api/crew/account-analysis` | POST | Unified account analysis (sentiment + health) |
| `/api/crew/implementation` | POST | Implementation project analysis |
| `/api/crew/project-analysis` | POST | Project analysis (routes and main) |
| `/api/crew/project-sentiment` | POST | Project sentiment analysis |
| `/api/crew/product-intelligence` | POST | Product intelligence |
| `/api/crew/renewal-readiness` | POST | Renewal readiness assessment |
| `/api/crew/expansion-specialist` | POST | Expansion opportunity analysis |
| `/api/crew/opportunity` | POST | Opportunity strategy analysis |
| `/api/crew/meddpicc-gap-actions` | POST | MEDDPICC gap recommendations |
| `/api/crew/strategic-action` | POST | Strategic action planning |
| `/api/crew/executive-briefing` | POST | Executive morning briefing (delta-aware) |
| `/api/crew/drilldown` | POST | Contextual drilldown |
| `/api/crew/custom-analysis` | POST | Custom analysis with user-defined context |

**Meeting & Communication**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/crew/call-analysis` | POST | Call analysis |
| `/api/crew/call-verification` | POST | Call verification |
| `/api/crew/feature-extraction` | POST | Feature extraction from transcripts |
| `/api/crew/agenda-generation` | POST | Meeting agenda generation |
| `/api/crew/sc-prep` | POST | Solutions Consultant prep |
| `/api/crew/email-draft` | POST | Email draft generation |
| `/api/crew/qbr-summary` | POST | QBR summary generation |
| `/api/crew/profile_builder` | POST | Profile builder |

**Coaching**

All coaching endpoints support streaming via `?stream=true`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/crew/ae-coaching` | POST | Account Executive coaching |
| `/api/crew/csm-coaching` | POST | Customer Success Manager coaching |
| `/api/crew/sc-coaching` | POST | Solutions Consultant coaching |
| `/api/crew/sdr-coaching` | POST | SDR coaching |
| `/api/crew/pm-coaching` | POST | Implementation Consultant coaching |
| `/api/crew/support-coaching` | POST | Support agent coaching |

**Support**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/crew/support_resolution` | POST | Support resolution analysis |
| `/api/crew/support_training` | POST | Alias for support_resolution |

**Studio**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/crew/studio-run` | POST | Dynamic crew runner with MCP tool access |
| `/api/crew/sandbox-test` | POST | Sandbox test/validation |

### Configuration (`/api/config`)

Agent and task configs are stored in YAML (defaults) with Supabase overrides.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/config/agents` | GET | List all agent configs |
| `/api/config/agents/{name}` | GET | Get specific agent config |
| `/api/config/agents/{name}` | PUT | Update agent config (persists to Supabase) |
| `/api/config/agents/{name}` | DELETE | Reset agent to YAML defaults |
| `/api/config/tasks` | GET | List all task configs |
| `/api/config/tasks/{name}` | GET | Get specific task config |
| `/api/config/tasks/{name}` | PUT | Update task config |
| `/api/config/tasks/{name}` | DELETE | Reset task to YAML defaults |

## Key Features

- **Multi-provider LLM fallback** - Tries OpenAI, Anthropic, and Google with automatic failover
- **SSE streaming** - Real-time streaming responses for coaching and analysis endpoints
- **Two-tier configuration** - YAML defaults with Supabase database overrides, editable via API
- **Error alerting** - Deduped alerts (24h window) with email notifications via luci-worker
- **Avoma MCP integration** - Meeting transcripts and notes via Model Context Protocol
- **Delta analysis** - Executive briefings compare against previous analysis to highlight changes
- **Batch processing** - Task priority support (LOW/MEDIUM/HIGH) for cost optimization
- **Data freshness tracking** - Warns when source data is stale

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Supabase service role key |
| `OPENAI_API_KEY` | Yes | Primary LLM provider |
| `OPENAI_MODEL_NAME` | No | Model name (default: gpt-4o-mini) |
| `ANTHROPIC_API_KEY` | No | Anthropic fallback provider |
| `GOOGLE_API_KEY` | No | Google AI fallback provider |
| `LUCI_WORKER_URL` | No | luci-worker URL for alert emails |
| `AVOMA_API_KEY` | No | Avoma meeting intelligence |
| `AVOMA_MCP_URL` | No | Avoma MCP endpoint |
| `MAVENLINK_API_TOKEN` | No | Mavenlink integration |
| `CRON_SECRET` | No | Auth for batch/scheduled jobs |
| `NEXTJS_APP_URL` | No | LUCI frontend URL |

## Local Development

```bash
# Install dependencies
pip install -e .

# Set environment variables (copy .env.example to .env)
cp .env.example .env

# Run server
uvicorn src.luci_crews.main:app --reload --port 8000

# Health check
curl http://localhost:8000/health

# Swagger docs
open http://localhost:8000/docs
```

## Deployment

The service runs on Railway via Docker (4 uvicorn workers). Auto-deploys on push to main.

```bash
git add .
git commit -m "Update crew prompts"
git push
```

Railway and Render configs are included (`railway.json`, `render.yaml`). The Dockerfile uses Python 3.11-slim with a health check at `/health`.

## Editing Prompts

Agent and task prompts live in `src/luci_crews/config/agents.yaml` and `tasks.yaml`. These serve as defaults - you can also override them at runtime through the `/api/config` endpoints, which persist changes to Supabase.
