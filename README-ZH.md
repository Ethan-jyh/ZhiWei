<div align="center">

# 「知 微」 (ZhiWei)
### 群体智能舆论演化沙盘与未来推演引擎
*Swarm Intelligence Public Opinion Evolution Sandtable & Future Deduction Engine*

[English](./README.md) | [中文文档](./README-ZH.md)

</div>

## ⚡ 项目概述

**「知 微」 (ZhiWei)** 是一款基于多智能体社会计算的舆论演化沙盘与未来推演引擎。面向重大突发事件公关演练与公共政策评估场景，依托媒体融合与传播国家重点实验室，构建基于多智能体社会计算的舆论仿真沙盘，支持从现实事件提取种子情报、生成异构 Agent、记录时序记忆，并比较不同干预策略下的舆态演进——**让未来在数字沙盘中预演，助决策在百战模拟后胜出**。

> **你只需**：上传现实种子情报（舆情分析报告、政策草案或突发事件材料），并设定推演与评估需求  
> **知微 将呈现**：深度交互的高保真微观演化沙盘、可控干预策略对比、平复降温周期指标以及详尽的推演评估报告

### 🛠️ 技术栈
- **核心框架**：Python、FastAPI、OASIS、Docker
- **记忆与检索**：Zep Graph Memory、GraphRAG、动态时序知识图谱
- **模型与认知**：本体知识图谱（Ontology）映射、多智能体交互演进
- **前端与可视化**：Vue 3、Vite、D3.js、TailwindCSS

### 🌟 核心能力与技术实现

- 🧬 **异构 Agent 生成与微观生态构建**：基于本体知识图谱（Ontology）的人物特征映射，从现实种子事件抽取实体关系，生成数百个具备不同认知立场、阶层属性与互动偏好的异构 Agent；结合 OASIS 搭建社交网络拓扑，支撑群体行为推演。
- 🧠 **时序图谱记忆与 GraphRAG 认知增强**：集成 Zep Graph Memory，构建跨回合动态实体图谱并持久化 Agent 交互事件与观点传播拓扑；通过 GraphRAG 按需检索历史信息，支持跨轮次推演，实体记忆召回准确率达 **89.6%**。
- 🎯 **动态变量注入与干预评估**：负责跨进程仿真 IPC 状态机调度器，支持在推演过程中注入辟谣声明、引导通报等干预变量；系统化比较不同干预时机和策略下的舆论极化变化与平复降温周期，为危机应对方案提供沙盘评估依据。
- 📊 **推演结果分析与报告输出**：构建 Report Agent，分析沙盘快照中的舆论引爆点、极化拐点与次生风险，输出态势演进树、群体情绪演化图谱和应对建议。

## 📸 系统截图

<div align="center">
<table>
<tr>
<td><img src="./static/image/Screenshot/运行截图1.png" alt="截图1" width="100%"/></td>
<td><img src="./static/image/Screenshot/运行截图2.png" alt="截图2" width="100%"/></td>
</tr>
<tr>
<td><img src="./static/image/Screenshot/运行截图3.png" alt="截图3" width="100%"/></td>
<td><img src="./static/image/Screenshot/运行截图4.png" alt="截图4" width="100%"/></td>
</tr>
<tr>
<td><img src="./static/image/Screenshot/运行截图5.png" alt="截图5" width="100%"/></td>
<td><img src="./static/image/Screenshot/运行截图6.png" alt="截图6" width="100%"/></td>
</tr>
</table>
</div>

## 🔄 工作流程

1. **图谱构建**：现实种子提取 & 个体与群体记忆注入 & GraphRAG构建
2. **环境搭建**：实体关系抽取 & 人设生成 & 环境配置Agent注入仿真参数
3. **开始模拟**：双平台并行模拟 & 自动解析预测需求 & 动态更新时序记忆
4. **报告生成**：ReportAgent拥有丰富的工具集与模拟后环境进行深度交互
5. **深度互动**：与模拟世界中的任意一位进行对话 & 与ReportAgent进行对话

## 🚀 快速开始

### 一、源码部署（推荐）

#### 前置要求

| 工具 | 版本要求 | 说明 | 安装检查 |
|------|---------|------|---------|
| **Node.js** | 18+ | 前端运行环境，包含 npm | `node -v` |
| **Python** | ≥3.11, ≤3.12 | 后端运行环境 | `python --version` |
| **uv** | 最新版 | Python 包管理器 | `uv --version` |

#### 1. 配置环境变量

```bash
# 复制示例配置文件
cp .env.example .env

# 编辑 .env 文件，填入必要的 API 密钥
```

**必需的环境变量：**

```env
# LLM API配置（支持 OpenAI SDK 格式的任意 LLM API）
# 推荐使用阿里百炼平台qwen-plus模型：https://bailian.console.aliyun.com/
# 注意消耗较大，可先进行小于40轮的模拟尝试
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus

# Zep Cloud 配置
# 每月免费额度即可支撑简单使用：https://app.getzep.com/
ZEP_API_KEY=your_zep_api_key
```

#### 2. 安装依赖

```bash
# 一键安装所有依赖（根目录 + 前端 + 后端）
npm run setup:all
```

或者分步安装：

```bash
# 安装 Node 依赖（根目录 + 前端）
npm run setup

# 安装 Python 依赖（后端，自动创建虚拟环境）
npm run setup:backend
```

#### 3. 启动服务

```bash
# 同时启动前后端（在项目根目录执行）
npm run dev
```

**服务地址：**
- 前端：`http://localhost:3000`
- 后端 API：`http://localhost:5001`

**单独启动：**

```bash
npm run backend   # 仅启动后端
npm run frontend  # 仅启动前端
```

### 二、Docker 部署

```bash
# 1. 配置环境变量（同源码部署）
cp .env.example .env

# 2. 拉取镜像并启动
docker compose up -d
```

默认会读取根目录下的 `.env`，并映射端口 `3000（前端）/5001（后端）`

> 在 `docker-compose.yml` 中已通过注释提供加速镜像地址，可按需替换

## 📄 致谢与开源声明 (Acknowledgements & Attribution)

本项目 **「知微」 (ZhiWei)** 基于开源项目 [MiroFish](https://github.com/666ghj/MiroFish)（由原作者 [666ghj](https://github.com/666ghj) 发起）进行深度二次研发与架构扩展。

在此基础上，本项目针对重大突发事件演练与公共政策评估场景，研发并扩展了：
- **跨进程仿真 IPC 状态机调度器** 与 **运行时声明干预系统**（即时/排期辟谣与引导通报）
- **舆论讨论热度聚合** 与 **达标降温窗口可审计计算引擎**
- **场景冻结机制** 与 **受控对比实验系统**（Control / Early / Late 变体对比与局限性声明）
- **本体知识图谱（Ontology）人物特征映射** 与 **Report Agent** 态势演化分析

衷心感谢原作者团队与 CAMEL-AI [OASIS](https://github.com/camel-ai/oasis) 社区的卓越工作与开源贡献！
