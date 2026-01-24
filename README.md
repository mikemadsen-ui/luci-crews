# LUCI CrewAI Service

This is a complete CrewAI service for LUCI, designed to run on cloud platforms (Railway or Render) with easy prompt editing via YAML configuration files.

## Quick Start

### 1. Create a New GitHub Repository

```bash
# Create new repo on GitHub called "luci-crews" (or similar)
# Clone it locally
git clone https://github.com/YOUR_ORG/luci-crews.git
cd luci-crews

# Copy all files from this directory
cp -r /path/to/luci/docs/railway-crewai-setup/* .

# Commit and push
git add .
git commit -m "Initial CrewAI service setup"
git push
```

### 2. Choose Your Platform

- [Deploy to Render](#deploy-to-render) (recommended)
- [Deploy to Railway](#deploy-to-railway)

---

## Deploy to Render

### 1. Create Render Account & Connect Repo

1. Go to [render.com](https://render.com) and sign up with GitHub
2. Click **New +** → **Web Service**
3. Connect your `luci-crews` repository
4. Render will auto-detect `render.yaml` and the Dockerfile

### 2. Set Environment Variables

In Render dashboard, go to your service → **Environment** tab:

| Variable | Value | Required |
|----------|-------|----------|
| `SUPABASE_URL` | Your Supabase project URL | Yes |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key | Yes |
| `OPENAI_API_KEY` | Your OpenAI API key | Yes |
| `OPENAI_MODEL_NAME` | `gpt-4o-mini` (or `gpt-4o`) | No |
| `ANTHROPIC_API_KEY` | Your Anthropic API key | No |
| `GOOGLE_API_KEY` | Your Google AI API key | No |
| `CRON_SECRET` | Secret for batch job auth | If using batch |
| `NEXTJS_APP_URL` | Your Vercel frontend URL | If using batch |
| `AVOMA_API_KEY` | Avoma integration key | No |
| `AVOMA_MCP_URL` | Avoma MCP endpoint | No |
| `MAVENLINK_API_TOKEN` | Mavenlink API token | No |

### 3. Get Your Service URL

After deployment, Render gives you a URL like:
```
https://luci-crews.onrender.com
```

### 4. Update LUCI App

In your main LUCI Vercel deployment, add environment variable:
```
CREWAI_PYTHON_SERVICE_URL=https://luci-crews.onrender.com
```

### Render Pricing

- **Free Tier**: 750 hours/month, spins down after 15 min inactivity (cold starts ~30s)
- **Starter**: $7/month - always on, 512MB RAM (recommended for production)
- **Standard**: $25/month - 2GB RAM, better for heavy CrewAI workloads

---

## Deploy to Railway

### 1. Create Railway Project

1. Go to [railway.app](https://railway.app) and sign in with GitHub
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select your `luci-crews` repository
4. Railway will auto-detect the Dockerfile

### 2. Set Environment Variables

In Railway dashboard, go to your service → **Variables** tab:

| Variable | Value | Required |
|----------|-------|----------|
| `SUPABASE_URL` | Your Supabase project URL | Yes |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key | Yes |
| `OPENAI_API_KEY` | Your OpenAI API key | Yes |
| `OPENAI_MODEL_NAME` | `gpt-4o-mini` (or `gpt-4o`) | No |
| `ANTHROPIC_API_KEY` | Your Anthropic API key | No |
| `GOOGLE_API_KEY` | Your Google AI API key | No |
| `CRON_SECRET` | Secret for batch job auth | If using batch |
| `NEXTJS_APP_URL` | Your Vercel frontend URL | If using batch |
| `AVOMA_API_KEY` | Avoma integration key | No |
| `MAVENLINK_API_TOKEN` | Mavenlink API token | No |
| `PORT` | `8000` | Auto-set |

### 3. Get Your Service URL

After deployment, Railway gives you a URL like:
```
https://luci-crews-production.up.railway.app
```

### 4. Update LUCI App

In your main LUCI Vercel deployment, add environment variable:
```
CREWAI_PYTHON_SERVICE_URL=https://luci-crews-production.up.railway.app
```

### Railway Pricing

- **Free Tier**: $5/month credit (enough for testing)
- **Hobby**: $5/month + usage
- **Pro**: $20/month + usage (recommended for production)

Typical usage for CrewAI: ~$10-30/month depending on crew execution frequency.

---

## Project Structure

```
luci-crews/
├── Dockerfile                    # Docker deployment config
├── pyproject.toml               # Python dependencies
├── railway.json                 # Railway-specific settings
├── render.yaml                  # Render-specific settings
├── README.md                    # This file
└── src/
    └── luci_crews/
        ├── __init__.py
        ├── main.py              # FastAPI server
        ├── config/
        │   ├── agents.yaml      # EDIT AGENT PROMPTS HERE
        │   └── tasks.yaml       # EDIT TASK PROMPTS HERE
        └── crews/
            ├── __init__.py
            ├── sales_pipeline_crew.py
            ├── account_health_crew.py
            ├── implementation_crew.py
            └── sentiment_crew.py
```

## Editing Prompts

### Edit Agent Prompts

Open `src/luci_crews/config/agents.yaml`:

```yaml
sales_pipeline_analyst:
  role: "Sales Pipeline Analyst"
  goal: >
    YOUR CUSTOM GOAL HERE...
  backstory: >
    YOUR CUSTOM BACKSTORY HERE...
```

### Edit Task Prompts

Open `src/luci_crews/config/tasks.yaml`:

```yaml
analyze_pipeline:
  description: >
    YOUR CUSTOM TASK DESCRIPTION HERE...

    Use placeholders like {user_name}, {opportunities_data}, etc.
  expected_output: >
    DESCRIBE WHAT OUTPUT YOU WANT...
```

### Deploy Changes

```bash
git add .
git commit -m "Update crew prompts"
git push
# Both Railway and Render auto-deploy on push!
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/docs` | GET | Swagger UI documentation |
| `/api/crew/sales_pipeline` | POST | Run sales pipeline analysis |
| `/api/crew/account` | POST | Run account health analysis |
| `/api/crew/implementation` | POST | Run implementation analysis |
| `/api/crew/sentiment` | POST | Run sentiment analysis |
| `/api/config/agents` | GET | View current agent configs |
| `/api/config/tasks` | GET | View current task configs |

## Testing Locally

```bash
# Install dependencies
pip install -e .

# Set environment variables
export OPENAI_API_KEY=your-key-here
export SUPABASE_URL=your-supabase-url
export SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Run server
uvicorn src.luci_crews.main:app --reload --port 8000

# Test health endpoint
curl http://localhost:8000/health

# Test a crew
curl -X POST http://localhost:8000/api/crew/sales_pipeline \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test",
    "user_email": "test@example.com",
    "opportunities": [],
    "summary": {"totalAmount": 0, "avgProbability": 0}
  }'
```

## Updating LUCI Proxy Routes

Your LUCI Next.js app needs to proxy requests to this service. Update the crew routes:

```javascript
// src/app/api/crew/sales_pipeline/route.js
const pythonServiceUrl = process.env.CREWAI_PYTHON_SERVICE_URL;

// Forward request to deployed service
const response = await fetch(`${pythonServiceUrl}/api/crew/sales_pipeline`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(requestData),
});
```

## Troubleshooting

### Service Not Starting
- Check deployment logs for errors
- Verify `OPENAI_API_KEY` and `SUPABASE_*` vars are set

### Crew Timeouts
- Both Railway and Render support long-running requests (no 300s Vercel limit)
- Complex crews may take 2-5 minutes

### CORS Errors
- Add your LUCI domain to the `allow_origins` list in `main.py`

### Cold Starts (Render Free Tier)
- Free tier spins down after 15 min of inactivity
- First request after idle takes ~30s
- Upgrade to Starter ($7/mo) for always-on

## Adding New Crews

1. Add agent definition to `config/agents.yaml`
2. Add task definition to `config/tasks.yaml`
3. Create new crew class in `crews/` directory
4. Add endpoint in `main.py`
5. Push to deploy

## Support

- CrewAI Docs: https://docs.crewai.com
- Render Docs: https://render.com/docs
- Railway Docs: https://docs.railway.app
- FastAPI Docs: https://fastapi.tiangolo.com

