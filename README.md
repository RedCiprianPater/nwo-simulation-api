# NWO Simulation API

[![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-009485)]()
[![Docker](https://img.shields.io/badge/docker-supported-2496ed)]()
[![License](https://img.shields.io/badge/license-MIT-blue)]()

Cloud-based simulation service for NWO Robotics. Runs LingBot-World simulations remotely so users don't need 8 GPUs locally. Used by direct API clients and (as of v2.0) by NWO Own Robot agents during their hourly reasoning cycles.

🌐 **Live API:** https://nwo-simulation-api.onrender.com
📖 **Swagger UI:** https://nwo-simulation-api.onrender.com/docs

---

## What's new in v2.0

This API was rebuilt in May 2026 to integrate with NWO Own Robot agents. Breaking changes from v1:

- **Real authentication.** v1 had a hardcoded `test_key`. v2 validates keys against the NWO API key registry at `nwo-capital-api.onrender.com`. Keys are issued per-wallet from the React app at [cpater-nwo-capital.hf.space](https://cpater-nwo-capital.hf.space) → API Keys.
- **Wallet scoping.** Environments, simulations, and training jobs are now scoped to the wallet that created them. Listing endpoints only return your own records. v1 had a cross-wallet data leak; that's fixed.
- **Two header schemes accepted.** Both `Authorization: Bearer <key>` (the original code) and `X-API-Key: <key>` (the README) work. Pick whichever your client prefers.
- **New `/v1/whoami` endpoint.** Lets clients verify which wallet their key resolves to.
- **New `/v1/simulations` LIST endpoint.** Was missing in v1.
- **Per-wallet pending quota.** Caps how many sims a single guardian can have queued at once (default 50).

If you were using the old `test_key`, set `NWO_ALLOW_TEST_KEY=true` in the environment to keep it working during migration. Off by default in production.

---

## Known limitations

Two things you should know before relying on this API:

1. **LingBot-World weights are not loaded by the worker yet.** Per the [nwo-robotics-sim](https://github.com/RedCiprianPater/nwo-robotics-sim) README, LingBot integration is "scaffolded but requires manual setup of the world model weights." Simulations queue successfully, status endpoints work, but no video output is generated until the weights are deployed. The runner-side integration handles this gracefully — agents see a "queued, no metrics yet" status.

2. **Storage is in-memory.** Environments, simulations, and training jobs live in Python dicts. They're lost when the Render container restarts (which happens after 15 min of inactivity on the free tier, or any deploy). The PostgreSQL deps in `requirements.txt` are unused. Migrating to Postgres is its own piece of work; tracked separately.

---

## ✨ Features

| Feature | Status |
|---|---|
| 🌍 Virtual Environment Generation | Endpoint live; depends on LingBot weights |
| 🤖 Robot Simulation | Endpoint live; depends on LingBot weights |
| 🧠 RL Training Jobs | Endpoint live; depends on training worker |
| ⚡ Queue-Based Processing | Redis queue (optional, in-memory fallback) |
| 💳 Pay-Per-Use Billing | Cost estimates returned per request |
| 🔐 Wallet-Scoped Access | ✓ enforced in v2.0 |
| 🤖 NWO Own Robot Integration | ✓ runner v3.5+ |

---

## 💰 Pricing

| Service | Price | Description |
|---|---|---|
| Environment Creation | $0.10 | One-time fee per environment |
| Simulation | $0.01/sec | Billed by actual runtime |
| Training | $0.50/episode | Per training episode |

Billing is tied to the wallet that owns the API key used for the request.

---

## 🔑 Authentication

All endpoints (except `/health`) require an API key. Both header schemes work:

```bash
# Option 1: X-API-Key
curl -H "X-API-Key: $YOUR_KEY" https://nwo-simulation-api.onrender.com/v1/whoami

# Option 2: Authorization: Bearer
curl -H "Authorization: Bearer $YOUR_KEY" https://nwo-simulation-api.onrender.com/v1/whoami
```

### How to get an API key (v2.0)

1. Visit [cpater-nwo-capital.hf.space](https://cpater-nwo-capital.hf.space) (also live at `nwo.capital`)
2. Connect your guardian wallet (MetaMask)
3. Sign one message to authenticate the session
4. Go to **API Keys** → **+ Generate Key**
5. Copy the key (shown once)

The key is bound to your wallet. Every request to this API is logged against that wallet for billing and isolation.

> **Note:** The old `nwo.capital/webapp/api-key.php` PHP form is deprecated. Keys generated there are not recognized by this API in v2.0.

### Verify your key works

```bash
curl -H "X-API-Key: $YOUR_KEY" https://nwo-simulation-api.onrender.com/v1/whoami
```

Should return:
```json
{
  "wallet": "0xYOUR_GUARDIAN_WALLET",
  "key_id": "KEY-ABC123...",
  "key_name": "your key name",
  "is_test_key": false
}
```

If you get `401 Unauthorized`, the key is invalid or revoked. Generate a new one.

---

## 📡 API Endpoints

### Environments

#### Create
```http
POST /v1/environments
Content-Type: application/json
X-API-Key: your_key

{
  "name": "warehouse_training",
  "type": "indoor",
  "size": "480p",
  "objects": ["shelves", "boxes", "robots"],
  "prompt": "A warehouse with aisles and storage racks"
}
```

Response:
```json
{
  "id": "env_abc123",
  "name": "warehouse_training",
  "status": "pending",
  "created_at": "2026-05-04T08:00:00Z",
  "wallet": "0xYOUR_WALLET"
}
```

#### List (your wallet's only)
```http
GET /v1/environments
X-API-Key: your_key
```

Returns environments owned by the calling wallet only. v1's cross-wallet leak is fixed.

#### Get
```http
GET /v1/environments/{env_id}
X-API-Key: your_key
```

Returns 404 if the env exists but isn't yours (deliberately, to avoid leaking existence).

### Simulations

#### Create
```http
POST /v1/simulations
Content-Type: application/json
X-API-Key: your_key

{
  "environment_id": "env_abc123",
  "robot_config": {
    "type": "mobile_manipulator",
    "sensors": ["camera", "lidar"]
  },
  "task": "navigate to shelf A3 and pick up box",
  "duration_seconds": 60
}
```

The referenced environment must be owned by your wallet. Returns 404 otherwise.

#### List
```http
GET /v1/simulations
X-API-Key: your_key
```

Returns simulations owned by your wallet.

#### Status
```http
GET /v1/simulations/{sim_id}/status
X-API-Key: your_key
```

#### Results
```http
GET /v1/simulations/{sim_id}/results
X-API-Key: your_key
```

If the sim is not yet complete, returns:
```json
{
  "simulation_id": "sim_xyz789",
  "status": "running",
  "ready": false,
  "hint": "simulation still queued or running — poll again in 30-60s"
}
```

When ready (and once LingBot weights are loaded):
```json
{
  "simulation_id": "sim_xyz789",
  "status": "completed",
  "ready": true,
  "video_url": "https://storage.nwo.capital/simulations/sim_xyz789/output.mp4",
  "metrics": {
    "success_rate": 0.85,
    "completion_time": 45.2,
    "collisions": 2
  }
}
```

### Training

```http
POST /v1/training
GET  /v1/training/{job_id}/status
GET  /v1/training/{job_id}/model
```

Same wallet-scoping rules. All referenced environments must be owned by your wallet.

### Utility

```http
GET /health      # public, no auth
GET /v1/whoami   # auth required, returns your wallet identity
```

---

## 🤖 NWO Own Robot integration

As of runner v3.5 (May 2026), NWO Own Robot agents call this API automatically during their hourly reasoning cycles via the `request_simulation` action.

The flow:

```
[Agent reasoning emits request_simulation]
              │
              ▼
[NWO runner Worker decrypts guardian's NWO API key from KV]
              │
              ▼
[Worker POSTs to /v1/environments + /v1/simulations]
              │
              ▼
[This API queues the job, returns sim_id]
              │
              ▼
[Agent receives queued status in next reasoning cycle]
              │
              ▼
[Agent polls /v1/simulations/{sim_id}/results in subsequent cycles]
```

**For guardians:** to give your agent simulation capability, generate an API key and save it via the runner. Either at agent deploy time (the React app at [nwo.ciprianpater.workers.dev](https://nwo.ciprianpater.workers.dev) has a sim key field in Step 3) or after deploy via the dashboard's "+ ADD SIM KEY" button on each agent card.

**For runner operators:** see [RUNNER_V3.5_DEPLOY.md](https://github.com/RedCiprianPater/nwo-runner) for the integration details. Worker env vars required:

```bash
NWO_SIM_API_URL=https://nwo-simulation-api.onrender.com
```

---

## 🛠️ Quick Start

### Direct HTTP (recommended for v2)

```bash
export NWO_KEY="your_key_from_cpater-nwo-capital.hf.space"

# Create environment
curl -X POST https://nwo-simulation-api.onrender.com/v1/environments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $NWO_KEY" \
  -d '{"name": "warehouse", "prompt": "A warehouse with aisles", "size": "480p"}'

# Create simulation (use env_id from previous response)
curl -X POST https://nwo-simulation-api.onrender.com/v1/simulations \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $NWO_KEY" \
  -d '{
    "environment_id": "env_xxx",
    "robot_config": {"type": "mobile_manipulator"},
    "task": "pick up box",
    "duration_seconds": 60
  }'

# Poll for results
curl https://nwo-simulation-api.onrender.com/v1/simulations/sim_xxx/results \
  -H "X-API-Key: $NWO_KEY"
```

### Python requests

```python
import requests

API_URL = "https://nwo-simulation-api.onrender.com"
API_KEY = "your_key"  # from cpater-nwo-capital.hf.space

headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

# Verify your key first
r = requests.get(f"{API_URL}/v1/whoami", headers=headers)
print(r.json())  # should show your wallet

# Create environment
r = requests.post(
    f"{API_URL}/v1/environments",
    headers=headers,
    json={"name": "warehouse", "prompt": "A warehouse with aisles", "size": "480p"},
)
env_id = r.json()["id"]
print(f"Created environment: {env_id}")
```

### Legacy: `nwo-robotics-sim` Python package

The PyPI package [`nwo-robotics-sim`](https://pypi.org/project/nwo-robotics-sim/) and its CLI (`nwo sim ...`) were written for v1's hardcoded `test_key`. **As of v2.0 they may need updates to work with wallet-issued keys** — check the package version and its release notes before relying on it.

If you're using the package today and seeing 401 errors, it's likely sending the old `test_key`. Either update the package or use direct HTTP / Python requests as shown above.

---

## ⚙️ Configuration

Environment variables read by the API:

| Variable | Default | Description |
|---|---|---|
| `NWO_API_VALIDATE_URL` | `https://nwo-capital-api.onrender.com/api/api-keys/validate` | Where to validate API keys against the NWO registry |
| `NWO_ALLOW_TEST_KEY` | `false` | If `true`, the legacy hardcoded `test_key` works (use only in dev) |
| `NWO_MAX_PENDING_PER_WALLET` | `50` | Cap on pending simulations per guardian wallet |
| `REDIS_HOST` | `localhost` | Redis host for job queue (optional) |
| `REDIS_PORT` | `6379` | Redis port (optional) |
| `PORT` | `8000` | HTTP port |

---

## 🏗️ Tech Stack

- **FastAPI** — HTTP framework
- **httpx** — async HTTP client (used to call the NWO key validation registry)
- **Redis (optional)** — distributed task queue
- **Pydantic** — request/response models
- **Docker** — containerization
- **LingBot-World** — world model (weights loading is its own piece of work)

PostgreSQL deps are in `requirements.txt` for future migration off in-memory storage; not currently used.

---

## 🚀 Deployment

### Render (current production)

Auto-deploys from `main` branch. Environment variables set via the Render dashboard. The two new ones in v2.0:

```
NWO_API_VALIDATE_URL=https://nwo-capital-api.onrender.com/api/api-keys/validate
NWO_ALLOW_TEST_KEY=false
```

> **Cold start note:** Render's free tier sleeps after 15 minutes of inactivity. The first request after sleep takes 30+ seconds to respond. Subsequent requests are fast.

### Docker

```bash
# Build
docker build -t nwo-simulation-api .

# Run
docker run -p 8000:8000 \
  -e NWO_API_VALIDATE_URL=https://nwo-capital-api.onrender.com/api/api-keys/validate \
  -e NWO_ALLOW_TEST_KEY=false \
  nwo-simulation-api
```

### Local dev

```bash
pip install -r requirements.txt

# For local development, point at your own validate endpoint or enable test key
export NWO_ALLOW_TEST_KEY=true
export PORT=8000

uvicorn main:app --host 0.0.0.0 --port $PORT --reload

# Test with the legacy key (only works because NWO_ALLOW_TEST_KEY=true)
curl -H "X-API-Key: test_key" http://localhost:8000/v1/whoami
```

---

## 📚 Documentation

- API Docs (Swagger): https://nwo-simulation-api.onrender.com/docs
- API Docs (ReDoc): https://nwo-simulation-api.onrender.com/redoc
- This repo: https://github.com/RedCiprianPater/nwo-simulation-api
- Legacy Python package: https://pypi.org/project/nwo-robotics-sim/

---

## 🤝 Related projects

| Project | Role |
|---|---|
| [NWO Capital API](https://nwo-capital-api.onrender.com) | Issues and validates API keys (this API calls it for auth) |
| [NWO Runner](https://nwo-runner.ciprianpater.workers.dev) | Cloudflare Worker that executes agent reasoning + actions, calls this API |
| [NWO Own Robot](https://nwo.ciprianpater.workers.dev) | Guardian-facing UI for deploying agents and managing sim/Kimi keys |
| [nwo-robotics-cs](https://github.com/RedCiprianPater/nwo-robotics-cs) | HOI-PAGE perception + motion planning (the on-robot side) |
| [LingBot-World](https://github.com/robbyant/lingbot-world) | World model used for sim rendering (weights setup is upstream's piece) |

---

## 🐛 Troubleshooting

### `401: invalid API key`
Your key is wrong, expired, or revoked. Verify with `/v1/whoami`. If that also fails, generate a new key at [cpater-nwo-capital.hf.space](https://cpater-nwo-capital.hf.space) → API Keys.

### `503: auth service unavailable`
The NWO key registry on Render may be cold-starting (first request after sleep takes 30+ seconds). Try again in 30 seconds.

### `429: too many pending simulations`
Your wallet has hit `NWO_MAX_PENDING_PER_WALLET` (default 50). Wait for some to complete, or contact ops to raise the cap for your wallet.

### Sim queues but never produces a video
Expected for now. LingBot weights aren't loaded. The endpoint contract is ready; the rendering layer is the next piece of work.

### Sim worked yesterday, today my env_id returns 404
Render restarted the container. In-memory storage = data loss. We're aware; PostgreSQL migration is tracked.

---

## 📝 License

MIT — see `LICENSE`.

---

## 💬 Support

- Email: ciprian.pater@publicae.org
- Issues: https://github.com/RedCiprianPater/nwo-simulation-api/issues
- Discord: NWO Robotics Community
