# Hypothesis

## Description
Simulate your market before stepping into it. 

If your problem can be reframed as a turn-based game, Hypothesis is for you. Built as an alternative to traditional methods of gathering market feedback or conducting economic research (which are often time-consuming and costly), Hypothesis is fundamentally a custom simulator – so long as users have a clear understanding of what one turn in the simulation looks like, Hypothesis can construct it. 

These simulations, curated by Muse Code and powered by Muse Spark 1.3 agents, have implications across a variety of use cases across microeconomics, advertising, operations and more. 
- Should a premium grocery retailer enter a certain new market? 
- Should a brand wondering if it should proceed with a bold advertisement – would be lauded for its creativity or lambasted for its insensitivities?
- Under what conditions algorithmic collusion between LLMs might be possible? (and more.)

Tech Stack: 
- Models: Muse Code (Coding Agent), Muse Spark 1.3 (simulation agents, user-clarification), Muse Image 1.0
- Frameworks: Pydantic, FastAPI, Next.js
- Technologies: Docker, Render, Vercel

## Set-up 

### 1. Prerequisites

Ensure the following tools are installed on your workstation:
* **Python 3.13+**
* [**uv**](https://docs.astral.sh/uv/) (Astral's fast Python package & project manager):
  ```sh
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
* **Node.js 18+ & npm** (required to run the Next.js web application)
* **Docker** (required if executing isolated extension-worker simulations via `hypothesis-worker`)

---

### 2. Core Python Installation & Verification

Clone the repository and install all dependencies into the project virtual environment using `uv`:

```sh
# Clone repository
git clone https://github.com/averagebonsai/hypothesis.git
cd hypothesis

# Install locked dependencies and pre-commit packages
uv sync

# Run code style, type checking, and unit test suites
uv run ruff check src tests
uv run mypy src
uv run pytest
```

---

### 3. Environment Variables & API Credentials

To run simulations with live LLM policies (Meta Muse or OpenAI):

1. Copy the example environment template:
   ```sh
   cp .env.example .env
   ```
2. Configure your credentials inside `.env`:
   ```ini
   # Primary LLM API key (Meta / OpenAI)
   API_KEY=your_actual_api_key_here

   # (Optional) Leased concurrent actor keys for high-throughput simulations
   # API_KEY_2=second_api_key_here
   # API_KEY_3=third_api_key_here

   # Simulation actor policy model
   MODEL=muse-spark-1.3-contributor

   # Autonomous extension coding agent model (maximum reasoning)
   MODEL_CODING=muse-spark-1.3
   ```
   > **Note**: Credential values are kept strictly private on the host and are never leaked into job manifests, event ledgers, prompts, or Jupyter notebooks.

---

### 4. Running Simulation Benchmarks (CLI & Notebooks)

#### Run Command-Line Examples
```sh
# Run deterministic normal-form payoff matrix
uv run python -m examples.payoff_matrix

# Run continuous Bertrand pricing competition
uv run python -m examples.bertrand

# Run two-stage sequential Stackelberg leadership game
uv run python -m examples.stackelberg

# Run LLM-driven game with live/offline policy toggle
uv run python -m examples.llm_payoff_matrix
```

#### Interactive Jupyter Notebooks
Launch Jupyter using the project `.venv` kernel:
```sh
uv run jupyter lab
```
Open any pre-computed notebook in `visualisations/`:
* `visualisations/purestrategy.ipynb` — Discrete normal-form coordination & Prisoner's Dilemma.
* `visualisations/bertrand.ipynb` — Homogeneous Bertrand pricing vs. analytical zero-profit Nash equilibrium.
* `visualisations/differentiated_bertrand.ipynb` — Multi-segment logit choice pricing with numerical Nash search.
* `visualisations/stackelberg.ipynb` — Sequential leader-follower output commitment vs. backward induction.

*(Each notebook includes an offline toggle `USE_LIVE_API = False` for deterministic dry-runs without billing).*

---

### 5. Launching the Hypothesis Web Suite (Full Stack Local)

The Hypothesis Autonomous Simulation Studio includes a Next.js 14 frontend and a FastAPI backend with live Server-Sent Events (SSE) streaming telemetry.

#### Option A: Quickstart Launch Script
Start both the backend API and Next.js frontend concurrently with a single command:
```sh
chmod +x scripts/dev.sh
./scripts/dev.sh
```

#### Option B: Manual Service Startup
If you prefer running services in separate terminal sessions:

* **Terminal 1 — FastAPI Backend (`:8000`)**:
  ```sh
  uv run uvicorn web.app:app --host 127.0.0.1 --port 8000 --reload
  ```
  * Interactive API Docs (Swagger): [http://localhost:8000/docs](http://localhost:8000/docs)
  * Health Check: [http://localhost:8000/api/health](http://localhost:8000/api/health)

* **Terminal 2 — Next.js Frontend (`:3000`)**:
  ```sh
  cd web
  npm install
  npm run dev
  ```
  * Open [http://localhost:3000](http://localhost:3000) in your browser.

---

### 6. Cloud Deployment (Render + Vercel)

* **Backend on Render (Docker Web Service)**:
  - Connect the repository to [Render](https://dashboard.render.com).
  - Select runtime **Docker** (`Dockerfile`).
  - Add environment variables: `PORT=8000`, `API_KEY=<key>`, `CORS_ORIGINS=*`.
  - Health check path: `/api/health`.
  - Render provides your live backend URL (e.g., `https://hypothesis-5nid.onrender.com`).
* **Frontend on Vercel (Next.js)**:
  - Connect the repository to [Vercel](https://vercel.com).
  - Set **Root Directory** to `web`.
  - Add environment variable `NEXT_PUBLIC_API_URL=https://<your-render-service>.onrender.com`.
  - Deploy. See [`docs/deployment_guide.md`](docs/deployment_guide.md) for full production deployment instructions.