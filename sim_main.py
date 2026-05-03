"""
NWO Simulation API — main.py
============================

FastAPI service that runs LingBot-World simulations for NWO Robotics agents.

WHAT CHANGED (v2.0)
-------------------
1. Real authentication: API keys are validated against the NWO API key
   registry at https://nwo-capital-api.onrender.com/api/api-keys/validate.
   Each request resolves to a guardian wallet, and that wallet is recorded
   on every environment / simulation / training job.

2. Wallet scoping: list/get endpoints only return records owned by the
   caller's wallet. This fixes a cross-wallet data leak in v1.

3. Both header schemes accepted:
     - Authorization: Bearer <api_key>  (the original code's scheme)
     - X-API-Key: <api_key>             (the README's scheme)
   Whichever the client sends, we accept.

4. Backward compat: the legacy hardcoded "test_key" still works if you
   set NWO_ALLOW_TEST_KEY=true in the environment. Off by default.

KNOWN LIMITATIONS (READ BEFORE DEPLOYING)
-----------------------------------------
* Storage is still in-memory Python dicts. Anything created is lost
  when the Render container restarts. The PostgreSQL deps in
  requirements.txt are unused. This is a known issue inherited from
  v1; fixing it requires a separate migration to SQLAlchemy + Postgres
  (Render PostgreSQL is a paid add-on).

* LingBot-World weights are NOT loaded by the worker yet (per the
  nwo-robotics-sim README: "scaffolded but requires manual setup of
  the world model weights"). Simulations queue successfully but the
  worker does not actually generate video output. The runner action
  on the Cloudflare side handles this gracefully — it surfaces the
  queued status to the agent's reasoning context.

* No rate limiting at this layer. Render's edge handles abusive load,
  but a guardian could exhaust their own credits very fast if their
  agent has a bug. The NWO_MAX_PENDING_PER_WALLET env var caps how
  many pending sims one wallet can have queued at once (default 50).

DEPLOY
------
1. Set environment variables on Render:
     NWO_API_VALIDATE_URL  https://nwo-capital-api.onrender.com/api/api-keys/validate
     NWO_ALLOW_TEST_KEY    false                (true ONLY for development)
     NWO_MAX_PENDING_PER_WALLET  50

2. Push to main, Render auto-deploys.

3. Verify with:
     curl -H "X-API-Key: $YOUR_KEY" https://nwo-simulation-api.onrender.com/v1/whoami
     # Should return {"wallet": "0x...", "key_id": "KEY-..."}
"""

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import uuid
import os
import json
import logging
from datetime import datetime
import httpx

# Redis is optional — if not configured, jobs queue in-memory.
# Production should use redis-py with the queue. For now we keep the
# original behavior to avoid breaking anything.
try:
    import redis
    redis_client = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"),
                               port=int(os.getenv("REDIS_PORT", "6379")),
                               db=0, socket_connect_timeout=2)
    redis_client.ping()
    REDIS_OK = True
except Exception:
    redis_client = None
    REDIS_OK = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("nwo-sim-api")

app = FastAPI(title="NWO Simulation API", version="2.0.0")

# ─── Configuration via env vars ────────────────────────────────────────
NWO_API_VALIDATE_URL = os.getenv(
    "NWO_API_VALIDATE_URL",
    "https://nwo-capital-api.onrender.com/api/api-keys/validate"
)
NWO_ALLOW_TEST_KEY = os.getenv("NWO_ALLOW_TEST_KEY", "false").lower() in ("true", "1", "yes")
NWO_MAX_PENDING_PER_WALLET = int(os.getenv("NWO_MAX_PENDING_PER_WALLET", "50"))

# In-memory storage. SEE WARNING IN MODULE DOCSTRING.
environments = {}  # env_id -> dict (now includes 'wallet' field)
simulations = {}   # sim_id -> dict (now includes 'wallet' field)
training_jobs = {} # job_id -> dict (now includes 'wallet' field)


# ─── Pydantic models ───────────────────────────────────────────────────

class EnvironmentCreate(BaseModel):
    name: str
    type: str = "indoor"
    size: str = "480p"
    objects: List[str] = []
    prompt: str

class Environment(BaseModel):
    id: str
    name: str
    type: str
    size: str
    status: str
    created_at: datetime
    prompt: str
    wallet: str  # NEW in v2

class SimulationCreate(BaseModel):
    environment_id: str
    robot_config: dict
    task: str
    duration_seconds: int = 60

class Simulation(BaseModel):
    id: str
    environment_id: str
    status: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cost_estimate: float
    wallet: str  # NEW in v2

class TrainingCreate(BaseModel):
    environment_ids: List[str]
    robot_type: str
    task: str
    episodes: int = 1000
    algorithm: str = "PPO"

class TrainingJob(BaseModel):
    id: str
    status: str
    episodes_completed: int
    total_episodes: int
    created_at: datetime
    cost_estimate: float
    wallet: str  # NEW in v2


# ─── Authentication dependency ─────────────────────────────────────────
#
# Accepts API key from EITHER header:
#   1. Authorization: Bearer <key>
#   2. X-API-Key: <key>
#
# Validates against the NWO API key registry. Returns a context dict
# with the verified guardian wallet, key_id, and key name. Endpoints
# use this to scope all reads/writes to the caller's wallet.

def _extract_api_key(request: Request) -> Optional[str]:
    """Pull the raw API key out of either supported header. Returns None if neither."""
    # Try Authorization: Bearer first (the original code's scheme)
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    # Fall back to X-API-Key (the README's scheme)
    x_api = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
    if x_api:
        return x_api.strip()
    return None


async def get_caller(request: Request) -> dict:
    """Resolve the caller's identity from headers. Raises 401 on failure.

    Returns:
        {
            "wallet":  "0x...",     (lowercase)
            "key_id":  "KEY-...",
            "key_name": "...",
            "is_test": bool,        (true if used legacy test_key)
        }
    """
    raw_key = _extract_api_key(request)
    if not raw_key:
        raise HTTPException(
            status_code=401,
            detail="missing API key — send Authorization: Bearer <key> or X-API-Key: <key>"
        )

    # Backward compat: legacy test_key, only if explicitly enabled
    if NWO_ALLOW_TEST_KEY and raw_key == "test_key":
        return {
            "wallet": "0x0000000000000000000000000000000000000000",
            "key_id": "LEGACY-TEST-KEY",
            "key_name": "legacy test key",
            "is_test": True,
        }

    # Validate against the NWO API key registry
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                NWO_API_VALIDATE_URL,
                json={"key": raw_key},
                headers={"Content-Type": "application/json"},
            )
            data = resp.json()
    except httpx.HTTPError as e:
        log.error(f"validate endpoint unreachable: {e}")
        raise HTTPException(
            status_code=503,
            detail="auth service unavailable — try again in a moment"
        )
    except Exception as e:
        log.error(f"unexpected validate error: {e}")
        raise HTTPException(status_code=500, detail="auth check failed")

    if not data.get("valid"):
        err = data.get("error", "invalid")
        raise HTTPException(status_code=401, detail=f"invalid API key ({err})")

    return {
        "wallet": (data.get("wallet") or "").lower(),
        "key_id": data.get("key_id"),
        "key_name": data.get("name"),
        "is_test": False,
    }


# ─── Helpers ───────────────────────────────────────────────────────────

def _check_pending_quota(wallet: str):
    """Block guardians from queuing more than NWO_MAX_PENDING_PER_WALLET sims."""
    if not wallet:
        return
    pending = sum(1 for s in simulations.values()
                  if s.get("wallet") == wallet
                  and s.get("status") in ("pending", "running"))
    if pending >= NWO_MAX_PENDING_PER_WALLET:
        raise HTTPException(
            status_code=429,
            detail=f"too many pending simulations ({pending} ≥ {NWO_MAX_PENDING_PER_WALLET}). "
                   "Wait for some to complete or contact support."
        )


# ─── Public (unauthenticated) endpoints ────────────────────────────────

@app.get("/health")
async def health_check():
    """Public health check — no auth required."""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "auth": "render-key-validation",
        "validate_url": NWO_API_VALIDATE_URL,
        "test_key_allowed": NWO_ALLOW_TEST_KEY,
        "redis_connected": REDIS_OK,
        "max_pending_per_wallet": NWO_MAX_PENDING_PER_WALLET,
        "warnings": [
            "in-memory storage: data lost on restart",
            "lingbot weights not loaded — sims queue but don't render",
        ] if not REDIS_OK else [
            "in-memory storage: data lost on restart",
        ],
    }


@app.get("/v1/whoami")
async def whoami(caller: dict = Depends(get_caller)):
    """Return the wallet your API key resolves to. Useful for clients to verify auth."""
    return {
        "wallet": caller["wallet"],
        "key_id": caller["key_id"],
        "key_name": caller["key_name"],
        "is_test_key": caller["is_test"],
    }


# ─── Environments ──────────────────────────────────────────────────────

@app.post("/v1/environments", response_model=Environment)
async def create_environment(
    env: EnvironmentCreate,
    background_tasks: BackgroundTasks,
    caller: dict = Depends(get_caller),
):
    """Create a virtual environment scoped to the caller's wallet."""
    env_id = f"env_{uuid.uuid4().hex[:8]}"
    new_env = Environment(
        id=env_id,
        name=env.name,
        type=env.type,
        size=env.size,
        status="pending",
        created_at=datetime.utcnow(),
        prompt=env.prompt,
        wallet=caller["wallet"],
    )
    environments[env_id] = new_env.dict()

    # Queue environment generation job (best-effort if Redis is up)
    if REDIS_OK:
        try:
            redis_client.lpush("simulation_queue", json.dumps({
                "type": "environment",
                "env_id": env_id,
                "wallet": caller["wallet"],
                "config": env.dict(),
            }))
        except Exception as e:
            log.warning(f"redis enqueue failed: {e}")

    log.info(f"env created: {env_id} (wallet={caller['wallet']})")
    return new_env


@app.get("/v1/environments", response_model=List[Environment])
async def list_environments(caller: dict = Depends(get_caller)):
    """List environments owned by the caller's wallet only."""
    return [
        Environment(**env) for env in environments.values()
        if env.get("wallet") == caller["wallet"]
    ]


@app.get("/v1/environments/{env_id}", response_model=Environment)
async def get_environment(env_id: str, caller: dict = Depends(get_caller)):
    """Get environment details (only if caller owns it)."""
    if env_id not in environments:
        raise HTTPException(status_code=404, detail="Environment not found")
    env = environments[env_id]
    if env.get("wallet") != caller["wallet"]:
        # Return 404 not 403 to avoid leaking existence
        raise HTTPException(status_code=404, detail="Environment not found")
    return Environment(**env)


# ─── Simulations ───────────────────────────────────────────────────────

@app.post("/v1/simulations", response_model=Simulation)
async def create_simulation(
    sim: SimulationCreate,
    caller: dict = Depends(get_caller),
):
    """Create and queue a simulation, scoped to caller's wallet.

    The referenced environment must also be owned by the caller's wallet.
    """
    if sim.environment_id not in environments:
        raise HTTPException(status_code=404, detail="Environment not found")
    env = environments[sim.environment_id]
    if env.get("wallet") != caller["wallet"]:
        raise HTTPException(status_code=404, detail="Environment not found")

    _check_pending_quota(caller["wallet"])

    sim_id = f"sim_{uuid.uuid4().hex[:8]}"
    cost = sim.duration_seconds * 0.01

    new_sim = Simulation(
        id=sim_id,
        environment_id=sim.environment_id,
        status="pending",
        created_at=datetime.utcnow(),
        cost_estimate=cost,
        wallet=caller["wallet"],
    )
    simulations[sim_id] = new_sim.dict()

    if REDIS_OK:
        try:
            redis_client.lpush("simulation_queue", json.dumps({
                "type": "simulation",
                "sim_id": sim_id,
                "wallet": caller["wallet"],
                "config": sim.dict(),
            }))
        except Exception as e:
            log.warning(f"redis enqueue failed: {e}")

    log.info(f"sim created: {sim_id} (wallet={caller['wallet']}, cost=${cost:.2f})")
    return new_sim


@app.get("/v1/simulations")
async def list_simulations(caller: dict = Depends(get_caller)):
    """List sims owned by caller. (Was missing in v1 — added for completeness.)"""
    return [s for s in simulations.values() if s.get("wallet") == caller["wallet"]]


@app.get("/v1/simulations/{sim_id}/status")
async def get_simulation_status(sim_id: str, caller: dict = Depends(get_caller)):
    """Get sim status (only if caller owns it)."""
    if sim_id not in simulations:
        raise HTTPException(status_code=404, detail="Simulation not found")
    sim = simulations[sim_id]
    if sim.get("wallet") != caller["wallet"]:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return sim


@app.get("/v1/simulations/{sim_id}/results")
async def get_simulation_results(sim_id: str, caller: dict = Depends(get_caller)):
    """Get sim results (only if caller owns it)."""
    if sim_id not in simulations:
        raise HTTPException(status_code=404, detail="Simulation not found")
    sim = simulations[sim_id]
    if sim.get("wallet") != caller["wallet"]:
        raise HTTPException(status_code=404, detail="Simulation not found")

    if sim["status"] != "completed":
        # Return current status with a hint, instead of erroring out — agents
        # poll this endpoint and need a clean signal "not yet, try again later"
        return {
            "simulation_id": sim_id,
            "status": sim["status"],
            "ready": False,
            "hint": "simulation still queued or running — poll again in 30-60s",
        }

    return {
        "simulation_id": sim_id,
        "status": "completed",
        "ready": True,
        "video_url": f"https://storage.nwo.capital/simulations/{sim_id}/output.mp4",
        "metrics": {
            "success_rate": 0.85,
            "completion_time": 45.2,
            "collisions": 2,
        },
    }


# ─── Training ──────────────────────────────────────────────────────────

@app.post("/v1/training", response_model=TrainingJob)
async def create_training_job(
    training: TrainingCreate,
    caller: dict = Depends(get_caller),
):
    """Create a training job. All referenced environments must be owned by caller."""
    for env_id in training.environment_ids:
        if env_id not in environments:
            raise HTTPException(status_code=404, detail=f"Environment {env_id} not found")
        if environments[env_id].get("wallet") != caller["wallet"]:
            raise HTTPException(status_code=404, detail=f"Environment {env_id} not found")

    job_id = f"train_{uuid.uuid4().hex[:8]}"
    cost = training.episodes * 0.50

    new_job = TrainingJob(
        id=job_id,
        status="pending",
        episodes_completed=0,
        total_episodes=training.episodes,
        created_at=datetime.utcnow(),
        cost_estimate=cost,
        wallet=caller["wallet"],
    )
    training_jobs[job_id] = new_job.dict()

    if REDIS_OK:
        try:
            redis_client.lpush("training_queue", json.dumps({
                "type": "training",
                "job_id": job_id,
                "wallet": caller["wallet"],
                "config": training.dict(),
            }))
        except Exception as e:
            log.warning(f"redis enqueue failed: {e}")

    log.info(f"training created: {job_id} (wallet={caller['wallet']}, cost=${cost:.2f})")
    return new_job


@app.get("/v1/training/{job_id}/status")
async def get_training_status(job_id: str, caller: dict = Depends(get_caller)):
    """Get training job status (only if caller owns it)."""
    if job_id not in training_jobs:
        raise HTTPException(status_code=404, detail="Training job not found")
    job = training_jobs[job_id]
    if job.get("wallet") != caller["wallet"]:
        raise HTTPException(status_code=404, detail="Training job not found")
    return job


@app.get("/v1/training/{job_id}/model")
async def download_model(job_id: str, caller: dict = Depends(get_caller)):
    """Download trained model URL (only if caller owns the job)."""
    if job_id not in training_jobs:
        raise HTTPException(status_code=404, detail="Training job not found")
    job = training_jobs[job_id]
    if job.get("wallet") != caller["wallet"]:
        raise HTTPException(status_code=404, detail="Training job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Training not completed")
    return {
        "download_url": f"https://storage.nwo.capital/models/{job_id}/robot_model.pt",
        "format": "pytorch",
        "size_mb": 250,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
