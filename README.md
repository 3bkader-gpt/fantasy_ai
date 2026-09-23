<div align="center">

# ⚽ FPL Autonomous AI Manager (`fantasy_ai`)

### Autonomous Fantasy Premier League Squad Manager Powered by Gemini AI & Mathematical Optimization

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Google Gemini](https://img.shields.io/badge/AI-Gemini%20Flash%20Reasoning-4285F4.svg?logo=google&logoColor=white)](https://ai.google.dev/)
[![Optimization](https://img.shields.io/badge/Optimization-MILP%20%26%20PuLP-red.svg)](https://coin-or.github.io/pulp/)
[![OR-Tools](https://img.shields.io/badge/Solver-Google%20OR--Tools-blue.svg)](https://developers.google.com/optimization)
[![Playwright](https://img.shields.io/badge/Playwright-Headless%20Execution-45BA4B.svg?logo=playwright&logoColor=white)](https://playwright.dev/)
[![Cloudflare](https://img.shields.io/badge/Sentinel-Cloudflare%20Workers-F38020.svg?logo=cloudflare&logoColor=white)](https://workers.cloudflare.com/)
[![Telegram](https://img.shields.io/badge/Alerts-Telegram%20Bot-26A5E4.svg?logo=telegram&logoColor=white)](https://telegram.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Linear Programming Solver • Multi-Horizon xP Decay • Press Conference NLP • Autonomous FPL Live Submissions**

[System Architecture](#-system-architecture) • [Core Capabilities](#-core-capabilities) • [Mathematical Optimization](#-mathematical-solver--xp-engine) • [Quick Start](#-installation--quick-start)

</div>

---

## 🎯 Overview

**FPL Autonomous AI Manager** is an end-to-end intelligent squad management system engineered to automate decision-making in Fantasy Premier League (FPL).

By combining **Mixed Integer Linear Programming (MILP)** with **Google Gemini Large Language Models**, the platform eliminates human emotional bias. It solves mathematical team knapsacks over multi-gameweek horizons, synthesizes press conference injury reports via NLP, optimizes captaincy picks, and automatically executes optimal transfers and starting lineups directly onto the official FPL platform via headless automation.

---

## 🏗 System Architecture

```mermaid
flowchart TD
    FPLAPI["🌐 Official Premier League API<br/>(Fixtures, Rosters, Price Changes)"]
    NewsSources["📰 Press Conferences & Injury Feeds"]
    
    subgraph Data & Telemetry Tier
        DataRepo["📥 Automated Data Repository"]
        NLPAnalyzer["🤖 Gemini Press Conference & Injury NLP Analyst"]
    end
    
    subgraph Optimization & Intelligence Tier
        xPEngine["⚡ Multi-Horizon xP Engine (Time-Decay Weights)"]
        MILPSolver["🧮 MILP Solver (PuLP & Google OR-Tools)"]
        GeminiAdvisor["🧠 Gemini Strategic Advisor & Rationale Generator"]
    end
    
    subgraph Automated Operations Tier
        Scheduler["⏰ Deadline Watchdog & Scheduler"]
        PlaywrightExecutor["🎭 Playwright Headless Submitter (Live / Dry-Run)"]
        TelegramNotifier["📱 Telegram Bot Dispatcher"]
        CloudflareSentinel["🛡️ Cloudflare Worker Edge Sentinel"]
    end

    FPLAPI --> DataRepo
    NewsSources --> NLPAnalyzer
    NLPAnalyzer --> xPEngine
    DataRepo --> xPEngine
    
    xPEngine --> MILPSolver
    MILPSolver --> GeminiAdvisor
    
    Scheduler --> MILPSolver
    GeminiAdvisor --> PlaywrightExecutor
    GeminiAdvisor --> TelegramNotifier
    CloudflareSentinel -.->|Health & Edge Failover| Scheduler
    PlaywrightExecutor -->|Submit Lineup & Transfers| FPLAPI
```

---

## 🌟 Core Capabilities

- 🤖 **Fully Autonomous Squad Management:** Automatically ingests gameweek fixture difficulty (FDR), player injury status, historical home/away performance, and market price changes without manual inputs.
- 🧮 **Mixed-Integer Linear Programming (MILP):** Formulates squad selection as a constrained knapsack problem (100.0M budget, max 3 players per club, valid formations 3-5-2, 3-4-3, 4-3-3, 4-4-2).
- 📈 **Multi-Horizon Expected Points (xP):** Evaluates player utility across a rolling 3-to-5 gameweek window utilizing geometric decay multipliers to prioritize immediate returns while preserving structural squad longevity.
- 🔍 **Press Conference NLP Analysis:** Leverages **Google Gemini** to extract sentiment, press conference quotes, rotation risks, and subtle injury signals that standard statistics miss.
- 🎭 **Headless Live / Dry-Run Execution:** Supports dry-run simulation mode for safety, or full headless Playwright execution to automatically log in, submit transfers, and adjust starting 11 before deadlines.
- 📱 **Real-Time Telegram Intelligence:** Dispatches rich gameweek briefing reports, tactical transfer justifications, captaincy recommendations, and chip timing directly to Telegram.

---

## 🧮 Mathematical Solver & xP Engine

The mathematical solver maximizes total expected points ($xP$) subject to official FPL constraints:

$$\max \sum_{i \in \text{Players}} \sum_{w=1}^{H} \gamma^{w-1} \cdot xP_{i,w} \cdot x_{i,w} - \text{Cost}(\text{Hits})$$

Where:
- $H$ is the planning horizon (e.g., 3 weeks).
- $\gamma$ is the time-decay factor (default: $0.85$).
- Constraints enforce team budget $\le 100.0\text{M}$, exactly 15 squad members (2 GK, 5 DEF, 5 MID, 3 FWD), and $\le 3$ players per Premier League club.

---

## 💻 Installation & Quick Start

### 1. Prerequisites
- **Python 3.10+**
- Google Gemini API Key

### 2. Setup Environment
```bash
# Clone the repository
git clone https://github.com/3bkader-gpt/fantasy_ai.git
cd fantasy_ai

# Setup virtual environment
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration (`.env`)
Create a `.env` file based on `.env.example`:
```ini
# Google Gemini API
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.0-flash

# Fantasy Premier League Credentials
FPL_EMAIL=your_email@example.com
FPL_PASSWORD=your_password
FPL_TEAM_ID=123456

# Operational Mode
DRY_RUN=True
HORIZON_WEEKS=3

# Telegram Notifications
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 4. Running the Optimization
```bash
# Execute single-gameweek tactical analysis
python main.py

# Run pure AI evaluation
python run_pure_ai.py

# Run test suite
pytest tests/ -v
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
