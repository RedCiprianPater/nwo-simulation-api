# NWO Simulation API

Cloud-based simulation service for NWO Robotics using LingBot-World.

## Overview

This FastAPI service provides remote access to LingBot-World simulation capabilities without requiring users to have 8 GPUs locally.

## Features

- Generate virtual training environments
- Simulate robot actions
- Train robots in virtual worlds
- Queue-based job processing
- Pay-per-use billing

## API Endpoints

### Authentication
All endpoints require API key in header: `X-API-Key: your_key`

### Environments

#### Create Environment
```
POST /v1/environments
{
  "name": "warehouse_training",
  "type": "indoor",
  "size": "480p",
  "objects": ["shelves", "boxes", "robots"],
  "prompt": "A warehouse with aisles and storage racks"
}
```

#### List Environments
```
GET /v1/environments
```

#### Get Environment
```
GET /v1/environments/{env_id}
```

### Simulation

#### Run Simulation
```
POST /v1/simulations
{
  "environment_id": "env_123",
  "robot_config": {
    "type": "mobile_manipulator",
    "sensors": ["camera", "lidar"]
  },
  "task": "navigate to shelf A3 and pick up box",
  "duration_seconds": 60
}
```

#### Get Simulation Status
```
GET /v1/simulations/{sim_id}/status
```

#### Get Simulation Results
```
GET /v1/simulations/{sim_id}/results
```

### Training

#### Start Training Job
```
POST /v1/training
{
  "environment_ids": ["env_123", "env_124"],
  "robot_type": "mobile_manipulator",
  "task": "warehouse_navigation",
  "episodes": 1000,
  "algorithm": "PPO"
}
```

#### Get Training Status
```
GET /v1/training/{job_id}/status
```

#### Download Model
```
GET /v1/training/{job_id}/model
```

## Billing

- Environment generation: $0.10 per environment
- Simulation: $0.01 per second
- Training: $0.50 per episode

## Quick Start

```bash
# Install client
pip install nwo-robotics

# Set API key
export NWO_API_KEY="your_key"

# Create environment
nwo sim env create --name "warehouse" --prompt "A warehouse with aisles"

# Run simulation
nwo sim run --env "warehouse" --task "navigate to point A"
```

## Tech Stack

- FastAPI
- Celery + Redis (job queue)
- LingBot-World (GPU workers)
- PostgreSQL (job tracking)
- Docker + Kubernetes

## License

MIT