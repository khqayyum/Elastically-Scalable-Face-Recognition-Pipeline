# Elatically Scalable Face Recognition Pipeline — AWS IaaS

A multi-tier, elastically scalable face recognition application built on AWS IaaS — using EC2, SQS, S3, DynamoDB, and a custom autoscaling controller to handle concurrent recognition requests with low latency.

---

## What This Project Does

Users upload face images via HTTP. The system identifies the person in the image using a deep learning model and returns the result. Under load, the application automatically scales from 0 to 15 EC2 instances to handle concurrent requests — and scales back to 0 when idle.

**Key Results:**
- ✅ 100% classification accuracy across 100 concurrent requests
- ⚡ 0.87s average latency under full load
- 🚀 0.32s average latency on warm cache (DynamoDB hit)
- 📉 Scaled back to 0 instances in 0.11 seconds after workload completion

---

## Architecture

```
                        ┌─────────────┐
         Images         │             │        Results
    ──────────────────► │  Web Tier   │ ◄──────────────────
                        │  (EC2)      │
                        │  server.py  │
                        │  controller │
                        └──────┬──────┘
                               │
               ┌───────────────┼───────────────┐
               │               │               │
        ┌──────▼──────┐ ┌──────▼──────┐ ┌─────▼──────────┐
        │ SQS Request │ │ SQS Response│ │   S3 Input     │
        │   Queue     │ │   Queue     │ │   Bucket       │
        └──────┬──────┘ └──────▲──────┘ └─────┬──────────┘
               │               │               │
        ┌──────▼───────────────┴───────────────▼──────────┐
        │              Application Tier                    │
        │    app-tier-instance-0 ... app-tier-instance-14  │
        │              (EC2, auto-scaled)                  │
        │                 backend.py                       │
        │    PyTorch Face Recognition Model                │
        └──────────────────────┬───────────────────────────┘
                               │
                        ┌──────▼──────┐
                        │  DynamoDB   │
                        │  (Results   │
                        │   Cache)    │
                        └─────────────┘
```

**Request flow:**
1. User POSTs an image to the web tier
2. Web tier stores image in S3 and sends request ID to SQS request queue
3. App tier instance picks up request, fetches image from S3, runs face recognition
4. Result stored in DynamoDB and pushed to SQS response queue
5. Web tier polls response queue and returns result to user
6. On repeat requests, DynamoDB cache is hit directly — no re-inference needed

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Web Tier | Python (Flask), AWS EC2 |
| App Tier | Python, PyTorch (Deep Learning) |
| Messaging | AWS SQS (Request + Response Queues) |
| Storage | AWS S3 (input images) |
| Database | AWS DynamoDB (result cache) |
| Autoscaling | Custom controller (SQS-depth based) |
| Language | Python |

---

## Key Design Decisions

### Why Custom Autoscaling Instead of AWS Auto Scaling?
AWS Auto Scaling works on CPU/memory metrics with a delay. This project implements a **queue-depth-based controller** — the number of running instances directly mirrors the number of pending SQS messages. This gives much tighter, more responsive scaling:
- 0 messages → 0 instances
- N messages → N instances (up to 15)
- Instances pre-warmed in "stopped" state to minimize startup latency

### Why SQS Instead of Direct HTTP to App Tier?
SQS decouples the web tier from the app tier entirely. The web tier never needs to know which app instance is handling a request — it just polls the response queue. This makes the system resilient to app instance failures and makes autoscaling seamless.

### Why DynamoDB for Caching?
Face recognition inference is expensive. If the same image filename is seen again, the result is fetched directly from DynamoDB without re-running the model — dropping average latency from 0.87s to 0.32s.

---

## Results

| Metric | Value |
|--------|-------|
| Classification accuracy | 100% (100/100 requests) |
| Average latency (cold) | 0.87 seconds |
| Average latency (warm cache) | 0.32 seconds |
| Max instances scaled out | 15 |
| Scale-in time after workload | 0.11 seconds |
| Total requests processed | 100 concurrent |

**Autoscaling behavior:**
```
Requests → 0   | Instances → 0   (idle)
Requests → 56  | Instances → 5   (scaling out)
Requests → 100 | Instances → 15  (peak load)
Requests → 0   | Instances → 0   (scaled back in 0.11s)
```

---

## Project Structure

```
face-recognition-iaas/
│
├── web-tier/
│   ├── server.py          # HTTP server — receives requests, manages S3 + SQS
│   └── controller.py      # Custom autoscaling controller
│
├── app-tier/
│   └── backend.py         # Face recognition inference + DynamoDB caching
│
└── README.md
```

---

## Setup Overview

> ⚠️ This project requires an AWS account with EC2, SQS, S3, DynamoDB access in `us-west-2`.

### 1. Create AWS Resources
```bash
# S3 input bucket
aws s3 mb s3://<ID>-in-bucket --region us-west-2

# SQS queues (max message size 1KB)
aws sqs create-queue --queue-name <ID>-req-queue \
  --attributes MaximumMessageSize=1024 --region us-west-2
aws sqs create-queue --queue-name <ID>-resp-queue --region us-west-2

# DynamoDB table
aws dynamodb create-table \
  --table-name <ID>-dynamoDB \
  --attribute-definitions AttributeName=filename,AttributeType=S \
  --key-schema AttributeName=filename,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-west-2
```

### 2. Create App Tier AMI
Launch a base EC2 instance, install dependencies, copy the deep learning model, and create an AMI:
```bash
pip3 install torch torchvision torchaudio \
  --index-url https://download.pytorch.org/whl/cpu
```

### 3. Launch Web Tier
Launch an EC2 instance named `web-instance`, assign an Elastic IP, and run:
```bash
python3 server.py &
python3 controller.py &
```

### 4. Send Requests
```bash
curl -X POST http://<web-instance-ip>:8000/ \
  -F "inputFile=@test_image.jpg"
# Response: "test_image:Paul"
```

---

## Key Concepts

**Queue-Depth Autoscaling:** The controller monitors the SQS request queue depth every second. It starts stopped EC2 instances when queue depth increases and stops them when it drops to 0 — no AWS Auto Scaling service used.

**Warm Cache:** DynamoDB stores `filename → result` mappings. On repeated requests for the same image, the app tier skips inference entirely and returns the cached result, dramatically reducing latency.

**Decoupled Architecture:** Web and app tiers communicate only through SQS queues. Neither tier needs direct knowledge of the other, making the system horizontally scalable and fault-tolerant.
