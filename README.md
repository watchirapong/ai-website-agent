# AI Website Agent

> Prompt it. Build it. Test it. Deploy it. — All automatic, all local.

An AI-powered agent with a **web dashboard** that takes a single text prompt, generates a complete **Next.js** website, automatically tests it for quality, and deploys it to production — with a self-healing retry loop that fixes issues until the site passes all checks.

```
Open http://localhost:3001 → type your prompt → get a live website
```

---

## Table of Contents

- [How It Works](#how-it-works)
- [Web Dashboard](#web-dashboard)
- [Architecture](#architecture)
- [CrewAI Agents](#crewai-agents)
- [API Endpoints](#api-endpoints)
- [Tech Stack](#tech-stack)
- [Generated Output](#generated-output)
- [Testing & Scoring](#testing--scoring)
- [Retry Loop](#retry-loop)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Roadmap](#roadmap)

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                     WEB DASHBOARD                               │
│         User types: "build a coffee shop site"                  │
│                  http://localhost:3001                           │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│  STEP 1: PLAN                                                 │
│  Planner Agent parses prompt → structured site plan           │
│  (pages, features, color scheme, layout)                      │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│  STEP 2: GENERATE                                             │
│  Developer Agent generates complete Next.js app               │
│  (pages, components, layout, Tailwind styling)                │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│  STEP 3: BUILD & SERVE                                        │
│  npm install → next build → next start                        │
│  Fix TypeScript/build errors automatically                    │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│  STEP 4: TEST                                                 │
│  Playwright screenshots (desktop/tablet/mobile)               │
│  Lighthouse audit (performance/a11y/SEO/best practices)       │
│  Link validation, console error check, load time              │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│  STEP 5: REVIEW                                               │
│  Reviewer Agent evaluates test results                        │
│  PASS → proceed to deploy                                     │
│  FAIL → send fix instructions back to Developer (max 3x)     │
└───────────────────────────────┬───────────────────────────────┘
                                │ (pass)
                                ▼
┌───────────────────────────────────────────────────────────────┐
│  STEP 6: DEPLOY                                               │
│  Deployer Agent runs: vercel --prod                           │
│  Returns live URL + final report to dashboard                 │
└───────────────────────────────────────────────────────────────┘
```

---

## Web Dashboard

A Next.js web UI to manage and prompt the agent from the browser.

### Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  AI Website Agent                                    [Settings] │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  What website do you want to build?                        │ │
│  │                                                            │ │
│  │  "Build a coffee shop site with menu and contact page"     │ │
│  │                                                            │ │
│  │                                        [ Generate ]        │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                 │
│  -- Active Build ──────────────────────────────────────────── │
│                                                                 │
│  Status: Building... (Attempt 2/3)                              │
│                                                                 │
│  [done]  Planner     Parsed: 3 pages, warm theme      2s       │
│  [done]  Developer   Generated 12 files, 18KB         8s       │
│  [done]  Build       next build passed                12s      │
│  [done]  Server      Running on localhost:3000         1s      │
│  [run]   Tester      Running Lighthouse...                     │
│  [wait]  Reviewer    Waiting...                                 │
│  [wait]  Deployer    Waiting...                                 │
│                                                                 │
│  -- Screenshots ──────────────────────────────────────────── │
│                                                                 │
│  ┌──────────┐  ┌────────┐  ┌──────┐                            │
│  │ Desktop  │  │ Tablet │  │Mobile│                            │
│  │ 1920px   │  │ 768px  │  │375px │                            │
│  │          │  │        │  │      │                            │
│  └──────────┘  └────────┘  └──────┘                            │
│                                                                 │
│  -- Scores ───────────────────────────────────────────────── │
│                                                                 │
│  Performance ████████░░ 82    Accessibility █████████░ 95      │
│  Best Pract. █████████░ 92    SEO           █████████░ 90      │
│                                                                 │
│  -- Past Projects ────────────────────────────────────────── │
│                                                                 │
│  Coffee Shop   │ 95/100 │ vercel.app/coffee  │ 10 min ago      │
│  Portfolio     │ 88/100 │ vercel.app/port    │ 1 hour ago      │
│  Restaurant    │ 91/100 │ vercel.app/rest    │ yesterday       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Dashboard Features

| Feature | Description |
|---------|-------------|
| **Prompt Input** | Text area to describe the website you want |
| **Live Progress** | Real-time step-by-step status via SSE |
| **Screenshots** | Desktop, tablet, mobile previews |
| **Score Cards** | Lighthouse scores with visual progress bars |
| **Project History** | List of all past generated sites |
| **Deploy Status** | Live URL shown when deployment completes |

### Dashboard Pages

| Route | Page | Purpose |
|-------|------|---------|
| `/` | Home | Prompt input + active build progress |
| `/projects` | Project List | All past projects with scores |
| `/projects/[id]` | Project Detail | Screenshots, report, deployed URL |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      WEB DASHBOARD                           │
│                  Next.js (port 3001)                          │
│                                                              │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌────────────┐ │
│  │ Prompt   │  │ Live      │  │ Results  │  │ Project    │ │
│  │ Input    │  │ Progress  │  │ Viewer   │  │ History    │ │
│  │ Form     │  │ (SSE)     │  │ Scores   │  │ List       │ │
│  └────┬─────┘  └─────▲─────┘  └──────────┘  └────────────┘ │
│       │               │                                      │
└───────┼───────────────┼──────────────────────────────────────┘
        │ POST          │ SSE (Server-Sent Events)
        │ /api/generate │ /api/status/stream
        ▼               │
┌───────────────────────┼──────────────────────────────────────┐
│              PYTHON BACKEND (FastAPI)                         │
│                   port 8000                                   │
│                                                              │
│  ┌────────────┐  ┌─────────────┐  ┌────────────────────┐    │
│  │ REST API   │  │ SSE Stream  │  │ SQLite DB          │    │
│  │            │  │ real-time   │  │ project history    │    │
│  │ /generate  │  │ progress    │  │ scores, URLs       │    │
│  │ /projects  │  │ updates     │  │                    │    │
│  │ /status    │  │             │  │                    │    │
│  └─────┬──────┘  └──────┬──────┘  └────────────────────┘    │
│        │                │                                    │
│        ▼                │                                    │
│  ┌──────────────────────┴──┐                                 │
│  │      CrewAI Pipeline       │                              │
│  │                            │                              │
│  │  Planner ──► Developer ────┼── progress events            │
│  │                 ▼          │                               │
│  │  Tester  ──► Reviewer      │                              │
│  │                 │          │                               │
│  │              Deployer      │                              │
│  └────────────────────────────┘                              │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│  ┌──────────┐  ┌──────────┐                                 │
│  │Playwright│  │Lighthouse│                                 │
│  │ Chromium │  │ CLI      │                                 │
│  └──────────┘  └──────────┘                                 │
└──────────────────────────────────────────────────────────────┘
```

### Data Flow

```
Browser (user on localhost:3001)
    │
    │  POST /api/generate
    │  { "prompt": "build a coffee shop site" }
    │
    ▼
FastAPI Backend (localhost:8000)
    │
    ├── Save project to SQLite (status: "started")
    │
    ├── Start CrewAI pipeline (background task)
    │     │
    │     ├── Planner   → emit("planner_done", plan)
    │     ├── Developer → emit("developer_done", files)
    │     ├── Build     → emit("build_done")
    │     ├── Tester    → emit("tester_done", report)
    │     ├── Reviewer  → emit("reviewer_done", pass/fail)
    │     │     └── if fail → emit("retry", attempt)
    │     └── Deployer  → emit("deployer_done", url)
    │
    ├── SSE stream pushes each event to browser in real-time
    │
    └── Update SQLite with final result
            │
            ▼
Browser receives real-time updates
    │
    ├── Progress steps update live
    ├── Screenshots appear
    ├── Scores animate in
    └── Final deployed URL displayed
```

---

## CrewAI Agents

The system uses **5 specialized agents**, each with a single responsibility:

```
┌─────────────────────────────────────────────────────────────┐
│                        THE CREW                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Agent 1: PLANNER        Role: "Website Architect"          │
│  ─────────────────────────────────────────────────          │
│  Parse user prompt into a structured site plan.             │
│  Input:  user prompt (string)                               │
│  Output: site plan (pages, features, style, layout)         │
│                                                             │
│  Agent 2: DEVELOPER      Role: "Next.js Developer"          │
│  ─────────────────────────────────────────────────          │
│  Generate complete Next.js app from site plan.              │
│  Input:  site plan + fix instructions (on retry)            │
│  Output: Next.js project files (.tsx, .css, configs)        │
│                                                             │
│  Agent 3: TESTER         Role: "QA Engineer"                │
│  ─────────────────────────────────────────────────          │
│  Run automated tests on the built site.                     │
│  Input:  running site URL (localhost:3000)                   │
│  Output: test report (scores, screenshots, errors)          │
│  Tools:  Playwright, Lighthouse CLI                         │
│                                                             │
│  Agent 4: REVIEWER       Role: "Tech Lead"                  │
│  ─────────────────────────────────────────────────          │
│  Evaluate test results against quality thresholds.          │
│  Input:  test report + screenshots                          │
│  Output: PASS/FAIL decision + fix instructions              │
│                                                             │
│  Agent 5: DEPLOYER       Role: "DevOps Engineer"            │
│  ─────────────────────────────────────────────────          │
│  Deploy approved site to Vercel.                            │
│  Input:  approved project directory                         │
│  Output: live production URL                                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Agent Flow

```
User Prompt (from Dashboard)
    │
    ▼
┌──────────┐  site_plan  ┌──────────┐   code   ┌──────────┐
│ PLANNER  │────────────►│DEVELOPER │────────►│ TESTER   │
│ Agent 1  │             │ Agent 2  │         │ Agent 3  │
└──────────┘             └────▲─────┘         └────┬─────┘
                              │                     │
                         fix_instructions      test_report
                              │                     │
                         ┌────┴─────┐          ┌────▼─────┐
                         │  FAIL    │◄─────────│ REVIEWER │
                         │  retry   │          │ Agent 4  │
                         └──────────┘          └────┬─────┘
                                                    │ PASS
                                                    ▼
                                              ┌──────────┐
                                              │ DEPLOYER │
                                              │ Agent 5  │
                                              └────┬─────┘
                                                   │
                                                   ▼
                                          Live URL → Dashboard
```

---

## API Endpoints

The FastAPI backend exposes these endpoints for the dashboard:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/generate` | Start new website generation |
| `GET` | `/api/status/:id` | Get current project status |
| `GET` | `/api/status/:id/stream` | SSE real-time progress stream |
| `GET` | `/api/projects` | List all past projects |
| `GET` | `/api/projects/:id` | Get single project details |
| `DELETE` | `/api/projects/:id` | Delete a project |
| `GET` | `/api/screenshots/:id` | Get screenshots for a project |
| `GET` | `/api/report/:id` | Get test report for a project |

### Request / Response Examples

**Start generation:**

```bash
POST /api/generate
Content-Type: application/json

{
  "prompt": "build a coffee shop site with menu and contact page",
  "model": "llama3",
  "max_retries": 3
}
```

```json
{
  "project_id": "proj_abc123",
  "status": "started",
  "stream_url": "/api/status/proj_abc123/stream"
}
```

**SSE stream events:**

```
event: planner_done
data: {"step": "planner", "status": "done", "detail": "3 pages, warm theme"}

event: developer_done
data: {"step": "developer", "status": "done", "detail": "12 files, 18KB"}

event: tester_done
data: {"step": "tester", "status": "done", "scores": {"perf": 88, "a11y": 95}}

event: deployer_done
data: {"step": "deployer", "status": "done", "url": "https://coffee.vercel.app"}
```

---

## Tech Stack

| Component | Tool | Purpose |
|-----------|------|---------|
| **Dashboard** | Next.js 14 + Tailwind CSS | Web UI for prompting and management |
| **Backend API** | FastAPI + Uvicorn | REST API + SSE real-time events |
| **Database** | SQLite | Project history, scores, URLs |
| **Agent Framework** | CrewAI | Orchestrates multi-agent pipeline |
| **Language** | Python 3.11+ | Agent and backend runtime |
| **LLM** | Anthropic Claude | Cloud AI via API |
| **Website Output** | Next.js 14 + React 18 | Generated website framework |
| **Styling** | Tailwind CSS | Utility-first CSS for generated sites |
| **Type Safety** | TypeScript | Catches errors at build time |
| **Browser Testing** | Playwright + Chromium | Screenshots, DOM checks, link validation |
| **Performance Audit** | Lighthouse CLI | Performance, a11y, SEO, best practices |
| **HTML Validation** | BeautifulSoup4 | Parse and validate HTML structure |
| **Deployment** | Vercel CLI | Native Next.js hosting |

### Why These Choices

- **Next.js Dashboard** — Same framework as the generated sites, fast to build, great DX
- **FastAPI** — Async Python, native SSE support, lightweight, fast
- **SQLite** — Zero-config database, no extra server needed, local-first
- **CrewAI** — Clean agent-per-role design, built-in task chaining
- **Next.js Output** — AI generates small focused components instead of one giant HTML file
- **Tailwind** — AI writes utility classes instead of inventing CSS (fewer bugs)
- **TypeScript** — Build step catches errors before the site ever runs
- **Vercel** — Zero-config deploy, built specifically for Next.js

### Ports

| Port | Service |
|------|---------|
| `3000` | Generated website preview (next start) |
| `3001` | Dashboard web UI (Next.js) |
| `8000` | Backend API (FastAPI) |

---

## Generated Output

The AI generates a complete Next.js project:

```
output/
├── package.json               # Dependencies
├── next.config.js             # Next.js config
├── tailwind.config.js         # Tailwind config
├── tsconfig.json              # TypeScript config
├── public/
│   └── favicon.ico
├── app/
│   ├── layout.tsx             # Root layout (fonts, metadata)
│   ├── page.tsx               # Home page
│   ├── globals.css            # Tailwind imports + global styles
│   ├── menu/
│   │   └── page.tsx           # Menu page
│   └── contact/
│       └── page.tsx           # Contact page
└── components/
    ├── Navbar.tsx              # Navigation bar
    ├── Hero.tsx                # Hero section
    ├── Footer.tsx              # Footer
    └── ContactForm.tsx         # Contact form component
```

---

## Testing & Scoring

### Test Suites

| Suite | Tool | Checks |
|-------|------|--------|
| **Visual** | Playwright | Screenshots at 1920px, 768px, 375px |
| **Functional** | Playwright | Console errors, broken links, page load time |
| **Performance** | Lighthouse | Performance score |
| **Accessibility** | Lighthouse | Accessibility score |
| **Best Practices** | Lighthouse | Best practices score |
| **SEO** | Lighthouse | SEO score |
| **Validation** | BeautifulSoup | HTML structure, meta tags, alt attributes |

### Pass/Fail Thresholds

```
Performance      >= 80
Accessibility    >= 90
Best Practices   >= 80
SEO              >= 80
Console Errors   = 0
Broken Links     = 0
Load Time        <= 3000ms
```

**PASS** = all thresholds met → deploy

**FAIL** = any threshold missed → retry with fix instructions

### Test Report Output

```json
{
  "lighthouse": {
    "performance": 88,
    "accessibility": 95,
    "best_practices": 92,
    "seo": 90
  },
  "screenshots": ["desktop.png", "tablet.png", "mobile.png"],
  "console_errors": [],
  "broken_links": [],
  "load_time_ms": 450,
  "html_valid": true
}
```

---

## Retry Loop

The agent automatically fixes issues and retries up to 3 times:

```
Attempt 1 → Generate → Build → Test → Review → FAIL
                                                  │
            "Fix: add alt tags, increase          │
             contrast, fix mobile nav"            │
                        ┌─────────────────────────┘
                        ▼
Attempt 2 → Re-generate with fixes → Test → Review → FAIL
                                                       │
            "Fix: mobile nav still overflows"          │
                        ┌──────────────────────────────┘
                        ▼
Attempt 3 → Re-generate with fixes → Test → Review → PASS → Deploy
```

### Best Version Tracking

```
overall_score = avg(performance, accessibility, best_practices, seo)

After each attempt:
    if overall_score > best_score:
        best_score = overall_score
        save output as best_version

After max 3 retries:
    deploy best_version (even if not perfect)
```

---

## Project Structure

```
ai-website-agent/
│
├── dashboard/                       # Web UI (Next.js on port 3001)
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   ├── app/
│   │   ├── layout.tsx               # Root layout
│   │   ├── page.tsx                 # Home — prompt input + live progress
│   │   ├── globals.css              # Global styles
│   │   └── projects/
│   │       └── [id]/
│   │           └── page.tsx         # Project detail view
│   └── components/
│       ├── PromptInput.tsx          # Prompt text area + submit button
│       ├── ProgressTracker.tsx      # Live step-by-step status (SSE)
│       ├── ScoreCards.tsx           # Lighthouse score progress bars
│       ├── ScreenshotGrid.tsx       # Desktop/tablet/mobile screenshots
│       └── ProjectList.tsx          # Past projects table
│
├── backend/                         # API server (FastAPI on port 8000)
│   ├── main.py                      # FastAPI app, routes, CORS
│   ├── models.py                    # SQLite models (Project, Report)
│   ├── database.py                  # DB connection + init
│   └── events.py                    # SSE event emitter for real-time updates
│
├── agent/                           # CrewAI pipeline
│   ├── config.py                    # Thresholds, model, ports, max retries
│   ├── crew.py                      # CrewAI crew definition (agents + tasks)
│   ├── planner.py                   # Agent 1: Parse prompt → site plan
│   ├── generator.py                 # Agent 2: Site plan → Next.js code
│   ├── validator.py                 # Build validation (npm install, next build)
│   ├── server.py                    # Start/stop Next.js preview server
│   ├── tester.py                    # Agent 3: Playwright + Lighthouse tests
│   ├── reviewer.py                  # Agent 4: Evaluate results → pass/fail
│   └── deployer.py                  # Agent 5: Deploy to Vercel
│
├── prompts/                         # LLM system prompts
│   ├── system_planner.txt           # System prompt for Planner Agent
│   ├── system_generator.txt         # System prompt for Developer Agent
│   └── system_reviewer.txt          # System prompt for Reviewer Agent
│
├── output/                          # Generated Next.js sites (gitignored)
├── reports/                         # Test reports + screenshots
│   ├── test_report.json
│   ├── lighthouse.json
│   └── screenshots/
│       ├── desktop.png
│       ├── tablet.png
│       └── mobile.png
│
├── requirements.txt                 # Python dependencies
└── README.md                        # This file
```

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Agent + backend runtime |
| Node.js | 18+ | Next.js dashboard + Lighthouse |
| npm | 9+ | Package management |

---

## Installation

### 1. Clone the project

```bash
cd ai-website-agent
```

### 2. Install Node.js tools

```bash
npm install -g vercel lighthouse
```

### 3. Install Python dependencies

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Install Playwright browser

```bash
playwright install chromium
```

### 5. Install Dashboard dependencies

```bash
cd dashboard
npm install
cd ..
```

### Python Dependencies (`requirements.txt`)

```
crewai>=0.80.0
crewai-tools>=0.14.0
playwright>=1.49.1
beautifulsoup4>=4.12.3
requests>=2.32.3
Pillow>=11.1.0
fastapi>=0.115.0
uvicorn>=0.34.0
aiosqlite>=0.20.0
sse-starlette>=2.1.0
```

---

## Usage

### Recommended (clean start every time)

```powershell
.\scripts\dev-reset.ps1
```

This script kills stale listeners and restarts:
- Backend on `:8011` (isolated to avoid stale `:8000` listeners)
- Dashboard on `:3001`

### Generate and wait for final status (no manual polling)

```powershell
.\scripts\generate-and-wait.ps1 -Prompt "Create a modern agency landing page"
```

Optional:

```powershell
.\scripts\generate-and-wait.ps1 -ApiBase "http://127.0.0.1:8020"
```

### Start the system (2 terminals)

```bash
# Terminal 1 — Backend API
cd backend
uvicorn main:app --port 8000 --reload

# Terminal 2 — Dashboard UI
cd dashboard
npm run dev -- --port 3001
```

### Open the dashboard

```
http://localhost:3001
```

1. Type your prompt: *"build a coffee shop site with menu and contact page"*
2. Click **Generate**
3. Watch live progress as each agent completes its step
4. View screenshots and scores when testing finishes
5. Get the deployed URL when complete

### CLI mode (alternative)

```bash
python main.py "build a coffee shop site with menu and contact page"
```

```bash
# Skip deployment (local preview only)
python main.py "build a portfolio site" --no-deploy

# Set max retry attempts
python main.py "build a restaurant site" --max-retries 5

```

### Example CLI Output

```
$ python main.py "build a coffee shop site with menu and contact page"

Starting AI Website Agent...
Prompt: "build a coffee shop site with menu and contact page"

--- Attempt 1/3 -------------------------------------------
[Planner]   Parsed: 3 pages, 4 components, warm color scheme
[Developer] Generated Next.js app (12 files, 18.4KB)
[Build]     npm install... done (8.2s)
[Build]     next build... done (12.1s)
[Server]    Started on http://localhost:3000
[Tester]    Screenshots: desktop, tablet, mobile
[Tester]    Lighthouse: perf=72 a11y=85 bp=90 seo=88
[Tester]    Console errors: 0 | Broken links: 0
[Reviewer]  FAIL — Performance 72 < 80, Accessibility 85 < 90
[Reviewer]  Fix: optimize images, add aria-labels, improve contrast

--- Attempt 2/3 -------------------------------------------
[Developer] Re-generated with fixes (12 files, 19.1KB)
[Build]     next build... done (11.8s)
[Tester]    Lighthouse: perf=88 a11y=95 bp=92 seo=90
[Reviewer]  PASS

[Deployer]  Deploying to Vercel...
[Deployer]  Live: https://coffee-shop-abc123.vercel.app

--- Report ------------------------------------------------
  Attempts:       2/3
  Final scores:   perf=88 a11y=95 bp=92 seo=90
  Live URL:       https://coffee-shop-abc123.vercel.app
  Screenshots:    ./reports/screenshots/
  Full report:    ./reports/test_report.json
  Time:           1m 42s
```

---

## Configuration

Edit `agent/config.py` to customize:

```python
# LLM
LLM_MODEL = "claude-haiku-4-20250414"
ANTHROPIC_API_KEY = "your-api-key"

# Ports
DASHBOARD_PORT = 3001
BACKEND_PORT = 8000
PREVIEW_PORT = 3000

# Retry
MAX_RETRIES = 3

# Thresholds (Lighthouse scores)
THRESHOLD_PERFORMANCE = 80
THRESHOLD_ACCESSIBILITY = 90
THRESHOLD_BEST_PRACTICES = 80
THRESHOLD_SEO = 80

# Functional
MAX_CONSOLE_ERRORS = 0
MAX_BROKEN_LINKS = 0
MAX_LOAD_TIME_MS = 3000

# Screenshots
VIEWPORTS = {
    "desktop": {"width": 1920, "height": 1080},
    "tablet":  {"width": 768,  "height": 1024},
    "mobile":  {"width": 375,  "height": 667},
}

# Database
DATABASE_PATH = "projects.db"
```

---

## Roadmap

- [x] Define architecture and agent roles
- [x] Choose tech stack
- [x] Design web dashboard UI
- [x] Design API endpoints
- [ ] Set up FastAPI backend with SQLite
- [ ] Set up Next.js dashboard project
- [ ] Implement PromptInput component
- [ ] Implement ProgressTracker with SSE
- [ ] Implement ScoreCards component
- [ ] Implement ScreenshotGrid component
- [ ] Implement ProjectList component
- [ ] Implement SSE event emitter
- [ ] Implement Planner Agent
- [ ] Implement Developer Agent (Next.js generation)
- [ ] Implement build validation (npm install + next build)
- [ ] Implement local server management
- [ ] Implement Tester Agent (Playwright + Lighthouse)
- [ ] Implement Reviewer Agent (pass/fail logic)
- [ ] Implement retry loop with fix instructions
- [ ] Implement Deployer Agent (Vercel CLI)
- [ ] CLI interface with options
- [ ] End-to-end testing

---

## License

MIT
