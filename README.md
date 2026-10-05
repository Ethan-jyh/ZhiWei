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

## 📄 Acknowledgments & Attribution

This project, **「知微」 (ZhiWei)**, is developed based on and extended from the open-source project [MiroFish](https://github.com/666ghj/MiroFish) created by [666ghj](https://github.com/666ghj).

Building upon this foundation, ZhiWei is tailored for public relations rehearsals in breaking events and policy evaluations, introducing major innovations:
- **Cross-Process Simulation IPC State Machine Coordinator** & **Runtime Statement Intervention System** (immediate and scheduled announcements/bulletins)
- **Discussion Heat Aggregation** & **Auditable Cooling Duration Calculation Engine**
- **Simulation Scene Freeze** & **Controlled Experiment Comparison Engine** (Control, Early, and Late variant comparisons with uncertainty limitation declarations)
- **Ontological Knowledge Graph (Ontology) Profile Mapping** & **Report Agent** multi-dimensional situation evolution analysis

We express our gratitude to the original authors and the CAMEL-AI [OASIS](https://github.com/camel-ai/oasis) community for their inspiring work and open-source contributions!
