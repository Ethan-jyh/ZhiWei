<div align="center">

# 「知 微」 (ZhiWei)
### Swarm Intelligence Public Opinion Evolution Sandtable & Future Deduction Engine

[English](./README.md) | [中文文档](./README-ZH.md)

</div>

## ⚡ Overview

**ZhiWei (知微)** is a next-generation public opinion evolution sandtable and future deduction engine powered by multi-agent social computing. Tailored for crisis public relations rehearsal in major breaking events and public policy assessment,依托媒体融合与传播国家重点实验室 (State Key Laboratory of Media Convergence and Communication), it extracts seed intelligence from real-world events, synthesizes heterogeneous agent populations, tracks dynamic temporal memories, and evaluates opinion trends under different intervention strategies — **rehearsing the future in a digital sandbox to empower decision-making through rigorous simulation**.

> **All you need**: Upload seed event materials (public opinion reports, policy drafts, or breaking intelligence) and define prediction requirements  
> **ZhiWei delivers**: A deeply interactive high-fidelity micro-evolution sandtable, controlled intervention comparisons, auditable cooling cycle metrics, and actionable evaluation reports

### 🛠️ Tech Stack
- **Core Frameworks**: Python, FastAPI, OASIS, Docker
- **Memory & Retrieval**: Zep Graph Memory, GraphRAG, Dynamic Temporal Knowledge Graph
- **Cognition & Models**: Ontology Profile Mapping, Multi-Agent Swarm Evolution
- **Frontend & UI**: Vue 3, Vite, D3.js, TailwindCSS

### 🌟 Key Architectures & Technical Implementations

- 🧬 **Heterogeneous Agent Generation & Micro-Ecosystem Construction**: Maps personality traits based on ontological knowledge graphs, extracts entity relationships from seed events, and generates hundreds of heterogeneous agents with distinct cognitive stances, socioeconomic attributes, and interaction preferences; integrates with OASIS to build social network topologies for swarm behavior deduction.
- 🧠 **Temporal Graph Memory & GraphRAG Cognitive Enhancement**: Integrates Zep Graph Memory to construct dynamic cross-round entity graphs and persist agent interaction events and opinion propagation topologies; retrieves historical intelligence on-demand via GraphRAG with an **89.6%** entity memory recall accuracy across rounds.
- 🎯 **Dynamic Variable Injection & Intervention Assessment**: Built a cross-process simulation IPC state machine coordinator supporting dynamic runtime injection of official statements and guidance bulletins; systematically evaluates opinion polarization shifts, heat dissipation, and auditable cooling durations across different intervention timings and strategies to provide quantitative sandtable evidence.
- 📊 **Deduction Analysis & Report Generation**: Powered by Report Agent, analyzes opinion flashpoints, polarization tipping points, and secondary risks from simulation snapshots, generating evolution tree diagrams, group sentiment topologies, and strategic mitigation plans.

## 🌐 Live Demo

Welcome to visit our online demo environment and experience a prediction simulation on trending public opinion events we've prepared for you: [mirofish-live-demo](https://666ghj.github.io/mirofish-demo/)

## 📸 Screenshots

<div align="center">
<table>
<tr>
<td><img src="./static/image/Screenshot/运行截图1.png" alt="Screenshot 1" width="100%"/></td>
<td><img src="./static/image/Screenshot/运行截图2.png" alt="Screenshot 2" width="100%"/></td>
</tr>
<tr>
<td><img src="./static/image/Screenshot/运行截图3.png" alt="Screenshot 3" width="100%"/></td>
<td><img src="./static/image/Screenshot/运行截图4.png" alt="Screenshot 4" width="100%"/></td>
</tr>
<tr>
<td><img src="./static/image/Screenshot/运行截图5.png" alt="Screenshot 5" width="100%"/></td>
<td><img src="./static/image/Screenshot/运行截图6.png" alt="Screenshot 6" width="100%"/></td>
</tr>
</table>
</div>

## 🎬 Demo Videos

### 1. Wuhan University Public Opinion Simulation + MiroFish Project Introduction

<div align="center">
<a href="https://www.bilibili.com/video/BV1VYBsBHEMY/" target="_blank"><img src="./static/image/武大模拟演示封面.png" alt="MiroFish Demo Video" width="75%"/></a>

Click the image to watch the complete demo video for prediction using BettaFish-generated "Wuhan University Public Opinion Report"
</div>

### 2. Dream of the Red Chamber Lost Ending Simulation

<div align="center">
<a href="https://www.bilibili.com/video/BV1cPk3BBExq" target="_blank"><img src="./static/image/红楼梦模拟推演封面.jpg" alt="MiroFish Demo Video" width="75%"/></a>

Click the image to watch MiroFish's deep prediction of the lost ending based on hundreds of thousands of words from the first 80 chapters of "Dream of the Red Chamber"
</div>

> **Financial Prediction**, **Political News Prediction** and more examples coming soon...

## 🔄 Workflow

1. **Graph Building**: Seed extraction & Individual/collective memory injection & GraphRAG construction
2. **Environment Setup**: Entity relationship extraction & Persona generation & Agent configuration injection
3. **Simulation**: Dual-platform parallel simulation & Auto-parse prediction requirements & Dynamic temporal memory updates
4. **Report Generation**: ReportAgent with rich toolset for deep interaction with post-simulation environment
5. **Deep Interaction**: Chat with any agent in the simulated world & Interact with ReportAgent

## 🚀 Quick Start

### Option 1: Source Code Deployment (Recommended)

#### Prerequisites

| Tool | Version | Description | Check Installation |
|------|---------|-------------|-------------------|
| **Node.js** | 18+ | Frontend runtime, includes npm | `node -v` |
| **Python** | ≥3.11, ≤3.12 | Backend runtime | `python --version` |
| **uv** | Latest | Python package manager | `uv --version` |

#### 1. Configure Environment Variables

```bash
# Copy the example configuration file
cp .env.example .env

# Edit the .env file and fill in the required API keys
```

**Required Environment Variables:**

```env
# LLM API Configuration (supports any LLM API with OpenAI SDK format)
# Recommended: Alibaba Qwen-plus model via Bailian Platform: https://bailian.console.aliyun.com/
# High consumption, try simulations with fewer than 40 rounds first
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus

# Zep Cloud Configuration
# Free monthly quota is sufficient for simple usage: https://app.getzep.com/
ZEP_API_KEY=your_zep_api_key
```

#### 2. Install Dependencies

```bash
# One-click installation of all dependencies (root + frontend + backend)
npm run setup:all
```

Or install step by step:

```bash
# Install Node dependencies (root + frontend)
npm run setup

# Install Python dependencies (backend, auto-creates virtual environment)
npm run setup:backend
```

#### 3. Start Services

```bash
# Start both frontend and backend (run from project root)
npm run dev
```

**Service URLs:**
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:5001`

**Start Individually:**

```bash
npm run backend   # Start backend only
npm run frontend  # Start frontend only
```

### Option 2: Docker Deployment

```bash
# 1. Configure environment variables (same as source deployment)
cp .env.example .env

# 2. Pull image and start
docker compose up -d
```

Reads `.env` from root directory by default, maps ports `3000 (frontend) / 5001 (backend)`

> Mirror address for faster pulling is provided as comments in `docker-compose.yml`, replace if needed.

## 📬 Join the Conversation

<div align="center">
<img src="./static/image/QQ群.png" alt="QQ Group" width="60%"/>
</div>

&nbsp;

The MiroFish team is recruiting full-time/internship positions. If you're interested in multi-agent simulation and LLM applications, feel free to send your resume to: **mirofish@shanda.com**

## 📄 Acknowledgments

**MiroFish has received strategic support and incubation from Shanda Group!**

MiroFish's simulation engine is powered by **[OASIS (Open Agent Social Interaction Simulations)](https://github.com/camel-ai/oasis)**, We sincerely thank the CAMEL-AI team for their open-source contributions!

## 📈 Project Statistics

<a href="https://github.com/666ghj/MiroFish">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="static/image/star-history-dark.svg" />
   <source media="(prefers-color-scheme: light)" srcset="static/image/star-history-light.svg" />
   <img alt="666ghj/MiroFish Star History Chart" src="static/image/star-history-light.svg" />
 </picture>
</a>
