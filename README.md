# NWO Simulation API

[![FastAPI](https://img.shields.io/badge/FastAPI-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-live-success.svg)](https://nwo-simulation-api.onrender.com)

Cloud-based simulation service for NWO Robotics using LingBot-World world models.

**🌐 Live API:** https://nwo-simulation-api.onrender.com

---

## 🚀 Overview

This FastAPI service provides remote access to LingBot-World simulation capabilities without requiring users to have 8 GPUs locally. Perfect for robotics training, testing, and development at scale.

## ✨ Features

- 🌍 **Virtual Environment Generation** - Create diverse training scenarios
- 🤖 **Robot Simulation** - Test actions in realistic virtual worlds
- 🧠 **RL Training Jobs** - Train robots using reinforcement learning
- ⚡ **Queue-Based Processing** - Handle multiple jobs efficiently
- 💳 **Pay-Per-Use Billing** - Only pay for what you use

## 💰 Pricing

| Service | Price | Description |
|---------|-------|-------------|
| **Environment Creation** | $0.10 | One-time fee per environment |
| **Simulation** | $0.01/sec | Billed by actual runtime |
| **Training** | $0.50/episode | Per training episode |

## 🔑 Authentication

All API endpoints require an API key in the header:

```
X-API-Key: your_api_key_here
```

Get your API key at: https://nwo.capital/webapp/api-key.php

## 📡 API Endpoints

### Environments

#### Create Environment
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

**Response:**
```json
{
  "id": "env_abc123",
  "name": "warehouse_training",
  "status": "pending",
  "created_at": "2026-04-18T08:00:00Z"
}
```

#### List Environments
```http
GET /v1/environments
X-API-Key: your_key
```

#### Get Environment
```http
GET /v1/environments/{env_id}
X-API-Key: your_key
```

### Simulations

#### Run Simulation
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

#### Get Simulation Status
```http
GET /v1/simulations/{sim_id}/status
X-API-Key: your_key
```

#### Get Simulation Results
```http
GET /v1/simulations/{sim_id}/results
X-API-Key: your_key
```

**Response:**
```json
{
  "simulation_id": "sim_xyz789",
  "status": "completed",
  "video_url": "https://storage.nwo.capital/simulations/sim_xyz789/output.mp4",
  "metrics": {
    "success_rate": 0.85,
    "completion_time": 45.2,
    "collisions": 2
  }
}
```

### Training

#### Start Training Job
```http
POST /v1/training
Content-Type: application/json
X-API-Key: your_key

{
  "environment_ids": ["env_abc123", "env_def456"],
  "robot_type": "mobile_manipulator",
  "task": "warehouse_navigation",
  "episodes": 1000,
  "algorithm": "PPO"
}
```

#### Get Training Status
```http
GET /v1/training/{job_id}/status
X-API-Key: your_key
```

#### Download Trained Model
```http
GET /v1/training/{job_id}/model
X-API-Key: your_key
```

## 🛠️ Quick Start

### Option 1: Using Python Client

```bash
# Install client
pip install nwo-robotics-sim

# Set API key
export NWO_API_KEY="your_key"

# Create environment
nwo sim env create --name "warehouse" --prompt "A warehouse with aisles"

# Run simulation
nwo sim run --env "warehouse" --robot mobile_manipulator --task "pick up box"
```

### Option 2: Using cURL

```bash
# Set your API key
export API_KEY="your_key"

# Create environment
curl -X POST https://nwo-simulation-api.onrender.com/v1/environments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "name": "test_env",
    "prompt": "A simple room",
    "size": "480p"
  }'

# Check health
curl https://nwo-simulation-api.onrender.com/health
```

### Option 3: Using Python Requests

```python
import requests

API_URL = "https://nwo-simulation-api.onrender.com"
API_KEY = "your_key"

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

# Create environment
response = requests.post(
    f"{API_URL}/v1/environments",
    headers=headers,
    json={
        "name": "warehouse",
        "prompt": "A warehouse with aisles",
        "size": "480p"
    }
)

env_id = response.json()["id"]
print(f"Created environment: {env_id}")
```

## 🔗 Integration Options

| Method | Best For | Documentation |
|--------|----------|---------------|
| **Local Package** | Development, testing | [`nwo-robotics-sim`](https://pypi.org/project/nwo-robotics-sim/) |
| **Cloud API** | Production, scale | This API |
| **Direct HTTP** | Custom integrations | See endpoints above |

## 🏗️ Tech Stack

- **FastAPI** - High-performance web framework
- **Celery + Redis** - Distributed task queue
- **LingBot-World** - World model for simulation
- **PostgreSQL** - Job tracking and metadata
- **Docker** - Containerization

## 🚀 Deployment

### Docker

```bash
# Build
docker build -t nwo-simulation-api .

# Run
docker run -p 8000:8000 nwo-simulation-api
```

### Render (Current)

Deployed at: https://nwo-simulation-api.onrender.com

Auto-deploys from GitHub on every push to `main`.

## 📚 Documentation

- **API Docs (Swagger UI):** https://nwo-simulation-api.onrender.com/docs
- **API Docs (ReDoc):** https://nwo-simulation-api.onrender.com/redoc
- **GitHub:** https://github.com/RedCiprianPater/nwo-simulation-api
- **PyPI Package:** https://pypi.org/project/nwo-robotics-sim/

## 🤝 Related Projects

- **NWO Robotics CLI:** https://github.com/nwocapital/nwo-robotics
- **Local Simulation Package:** https://pypi.org/project/nwo-robotics-sim/
- **LingBot-World:** https://github.com/robbyant/lingbot-world

## 📝 License

MIT License - See [LICENSE](LICENSE) for details.

## 💬 Support

- **Email:** ciprian.pater@publicae.org
- **Issues:** https://github.com/RedCiprianPater/nwo-simulation-api/issues
- **Discord:** NWO Robotics Community

---

**Built with ❤️ by the NWO Robotics Team**