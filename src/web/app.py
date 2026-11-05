"""FastAPI web service for Hypothesis simulation studio."""

import asyncio
import base64
import io
import json
import logging
import os
import urllib.error
import urllib.request
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from .jobs import JOBS
from .presets import CASE_STUDIES, PRESETS, run_preset_simulation

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Hypothesis Simulation API",
    description="Backend API powering the Hypothesis autonomous multi-agent feedback & interaction simulation studio",
    version="1.0.0",
)

# Configure CORS (supports local development and deployed frontend e.g. Vercel)
cors_origins_env = os.environ.get("CORS_ORIGINS", "")
allowed_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
if not allowed_origins:
    allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000", "*"]
else:
    for default_origin in ["http://localhost:3000", "http://127.0.0.1:3000"]:
        if default_origin not in allowed_origins and "*" not in allowed_origins:
            allowed_origins.append(default_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AlignmentRequest(BaseModel):
    hypothesis: str = Field(min_length=1, description="High-level goal or research hypothesis")
    num_turns: int = Field(default=5, ge=1, le=50)
    num_agents: int = Field(default=3, ge=1, le=10)
    turn_description: str = Field(min_length=1, description="What sequence of actions happens in 1 round")
    constraints: str = ""
    agent_prompts: str = ""
    supporting_documents: list[dict[str, Any]] = Field(default_factory=list)


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(min_length=1, description="Visual description of the simulation schematic")


class RunSimulationRequest(BaseModel):
    kind: str = Field(default="preset")  # "preset" | "custom"
    scenario_id: str = Field(default="supplychain")
    parameters: dict[str, Any] = Field(default_factory=dict)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "status": "online",
        "service": "hypothesis-simulation-api",
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": "hypothesis-simulation-api"}


def generate_muse_image(prompt: str) -> str:
    """Invokes Meta Muse Image API (muse-image-1.0) to generate a high-resolution simulation schematic."""
    from components.gateways.settings import LiveModelSettings
    settings = LiveModelSettings.load()
    api_key = settings.api_key.get_secret_value()

    url = "https://api.meta.ai/v1/images/generations"
    payload = {
        "model": "muse-image-1.0",
        "prompt": prompt,
        "size": "1024x1024",
        "response_format": "b64_json",
    }
    http_req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(http_req, timeout=45) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        if "data" in data and len(data["data"]) > 0:
            item = data["data"][0]
            if "b64_json" in item:
                return f"data:image/png;base64,{item['b64_json']}"
            if "url" in item:
                return str(item["url"])
    raise ValueError("Muse Image provider did not return image data.")


def process_uploaded_document(doc: dict[str, Any]) -> dict[str, Any]:
    """Extracts text from PDF or metadata/dimensions from images for meta-model consumption."""
    name = str(doc.get("name", "document"))
    mime_type = str(doc.get("type", "")).lower()
    raw_b64 = str(doc.get("data_base64", ""))
    if "," in raw_b64:
        raw_b64 = raw_b64.split(",", 1)[1]

    try:
        data_bytes = base64.b64decode(raw_b64)
    except (ValueError, TypeError) as err:
        return {"filename": name, "mime_type": mime_type, "error": f"PDF parsing is faulty: Unable to decode base64 file data ({err})."}

    if "pdf" in mime_type or name.lower().endswith(".pdf"):
        if not data_bytes or len(data_bytes) < 10:
            return {
                "filename": name,
                "mime_type": "application/pdf",
                "error": "PDF parsing is faulty: Uploaded file is empty or corrupted (insufficient byte stream).",
            }
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(data_bytes))
            if len(reader.pages) == 0:
                return {
                    "filename": name,
                    "mime_type": "application/pdf",
                    "error": "PDF parsing is faulty: PDF document contains zero readable pages.",
                }
            pages_text = []
            for i, page in enumerate(reader.pages[:20]):
                text = page.extract_text() or ""
                if text.strip():
                    pages_text.append(f"--- Page {i + 1} ---\n{text[:4000]}")
            if not pages_text:
                return {
                    "filename": name,
                    "mime_type": "application/pdf",
                    "error": "PDF parsing is faulty: No extractable text found in PDF document (pages may be blank or scanned images).",
                }
            extracted = "\n\n".join(pages_text)
            return {
                "filename": name,
                "mime_type": "application/pdf",
                "extracted_text": extracted[:20000],
                "pages_count": len(reader.pages),
            }
        except Exception as err:
            return {"filename": name, "mime_type": "application/pdf", "error": f"PDF parsing is faulty: {err}"}

    elif "jpeg" in mime_type or "jpg" in mime_type or "png" in mime_type or name.lower().endswith((".png", ".jpg", ".jpeg")):
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(data_bytes))
            return {
                "filename": name,
                "mime_type": mime_type or f"image/{img.format.lower() if img.format else 'png'}",
                "dimensions": f"{img.width}x{img.height}",
                "format": img.format or "IMAGE",
            }
        except (ValueError, TypeError, OSError) as err:
            return {"filename": name, "mime_type": mime_type, "error": f"Image parse error: {err}"}

    elif name.lower().endswith((".md", ".markdown")) or "markdown" in mime_type:
        try:
            text_str = data_bytes.decode("utf-8", errors="replace")
            return {
                "filename": name,
                "mime_type": "text/markdown",
                "extracted_text": text_str[:25000],
                "char_count": len(text_str),
            }
        except Exception as err:
            return {"filename": name, "mime_type": "text/markdown", "error": f"Markdown parse error: {err}"}

    return {"filename": name, "mime_type": mime_type, "content": "Unsupported format"}


@app.post("/api/simulations/generate-image")
def api_generate_image(req: ImageGenerationRequest) -> dict[str, Any]:
    """Generates a simulation visual schematic using Muse Image (muse-image-1.0)."""
    try:
        image_url = generate_muse_image(req.prompt)
        return {
            "status": "success",
            "model": "muse-image-1.0",
            "prompt": req.prompt,
            "image_url": image_url,
        }
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError, KeyError, OSError, RuntimeError) as err:
        logger.error("Muse Image generation failed: %s", err)
        raise HTTPException(
            status_code=500,
            detail=f"Muse Image generation failed: {err}",
        ) from err


@app.get("/api/presets")
def list_presets() -> list[dict[str, Any]]:
    return list(PRESETS.values())


@app.get("/api/presets/{preset_id}")
def get_preset(preset_id: str) -> dict[str, Any]:
    if preset_id not in PRESETS:
        raise HTTPException(status_code=404, detail="Preset not found")
    return PRESETS[preset_id]


@app.get("/api/case-studies")
def list_case_studies() -> list[dict[str, Any]]:
    return CASE_STUDIES


@app.get("/api/case-studies/{case_id}")
def get_case_study(case_id: str) -> dict[str, Any]:
    for cs in CASE_STUDIES:
        if cs["id"] == case_id:
            return cs
    raise HTTPException(status_code=404, detail="Case study not found")


@app.post("/api/simulations/align")
async def align_simulation(req: AlignmentRequest) -> dict[str, Any]:
    """Invokes Muse Coding Agent via live API to synthesize a domain-neutral mechanism blueprint."""
    blueprint = await synthesize_mechanism_blueprint(req)

    schematic_prompt = (
        f"Clear, informative architectural diagram illustrating a multi-agent simulation for '{req.hypothesis}'. "
        f"{req.num_agents} distinct participant actors arranged in an intuitive feedback layout. "
        f"Accurately representing the interaction protocol: '{req.turn_description}'. "
        f"Domain context: {blueprint.get('domain_archetype', 'general')}. "
        "Includes callout labels displaying participant actions and thought rationales. "
        "Clean, professional infographic aesthetic with balanced contrast and high readability, accurately communicating the user's simulation flow."
    )
    contradictions = blueprint.get("contradictions", [])
    return {
        "readback": blueprint.get("summary_readback", f"**Hypothesis**: {req.hypothesis}"),
        "assumptions": blueprint.get("assumptions", [
            f"Horizon is discretely bounded to exactly {req.num_turns} rounds.",
            f"Information visibility between {req.num_agents} actors is strictly partitioned.",
        ]),
        "feasibility_rules": blueprint.get("feasibility_rules", [
            "Actions must satisfy physical/economic non-negativity bounds.",
            "Runtime fallback trapping is armed to prevent simulation halts.",
        ]),
        "contradictions": contradictions,
        "has_contradictions": len(contradictions) > 0,
        "schematic_image_prompt": schematic_prompt,
        "blueprint": blueprint,
        "structured_request": {
            "hypothesis": req.hypothesis,
            "horizon": req.num_turns,
            "num_agents": req.num_agents,
            "turn_protocol": req.turn_description,
            "constraints": req.constraints,
        },
    }


@app.post("/api/sandbox/prepare")
def prepare_sandbox() -> dict[str, Any]:
    """Pre-warms the Muse Coding Agent sandbox and verifies live API connectivity."""
    try:
        from components.gateways.live import configured_gateway
        from simulation_core.model_gateway import GatewayError
        model_name, gateway = configured_gateway()
        if gateway is None or model_name is None:
            return {
                "status": "warning",
                "agent": "muse_coding_agent",
                "model": None,
                "sandbox_armed": False,
                "message": "No active API credentials found. Please set API_KEY in .env.",
            }
        return {
            "status": "ready",
            "agent": "muse_coding_agent",
            "model": model_name,
            "sandbox_armed": True,
            "message": f"Muse Code Agent armed with model '{model_name}'. Sandbox environment active and awaiting query.",
        }
    except (GatewayError, ValueError, KeyError, OSError, RuntimeError) as err:
        return {
            "status": "error",
            "agent": "muse_coding_agent",
            "model": None,
            "sandbox_armed": False,
            "message": str(err),
        }


async def synthesize_mechanism_blueprint(req: AlignmentRequest) -> dict[str, Any]:
    """Muse Coding Agent synthesis routine with live LLM model and high-fidelity fallback."""
    loop = asyncio.get_running_loop()

    try:
        from components.gateways.live import configured_gateway
        from simulation_core.model_gateway import GatewayError, ModelRequest
        model_name, gateway = configured_gateway()
    except (GatewayError, ValueError, KeyError, OSError, RuntimeError):
        model_name, gateway = None, None

    processed_docs = (
        [process_uploaded_document(d) for d in req.supporting_documents]
        if req.supporting_documents
        else []
    )

    req_data = {
        "hypothesis": req.hypothesis,
        "turn_description": req.turn_description,
        "num_turns": req.num_turns,
        "num_agents": req.num_agents,
        "constraints": req.constraints,
        "agent_prompts": req.agent_prompts,
        "supporting_documents": processed_docs,
    }

    schema = {
        "type": "object",
        "properties": {
            "domain_archetype": {"type": "string"},
            "summary_readback": {"type": "string"},
            "assumptions": {"type": "array", "items": {"type": "string"}},
            "feasibility_rules": {"type": "array", "items": {"type": "string"}},
            "action_schema": {
                "type": "object",
                "properties": {
                    "action_kind": {"type": "string"},
                    "primary_field": {"type": "string"},
                    "unit": {"type": "string"},
                },
                "required": ["action_kind", "primary_field", "unit"],
            },
            "actors": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "role": {"type": "string"},
                        "persona": {"type": "string"},
                        "cost_basis": {"type": "number", "description": "Optional marginal cost or production cost. ONLY for microeconomic/trading scenarios."},
                        "quality_index": {"type": "number", "description": "Optional quality score or taste preference factor."},
                        "criteria": {"type": "string", "description": "Qualitative evaluation criteria, background, or perspective of this actor."},
                    },
                    "required": ["id", "role", "persona"],
                },
            },
            "clearing_rule": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "description": "The interaction, synthesis, or clearing rule type (e.g., 'independent_feedback', 'qualitative_review', 'rating_aggregation', 'deliberation', 'consensus_voting', 'logit_choice', 'auction', 'cournot', 'market_clearing')."},
                    "description": {"type": "string", "description": "Detailed explanation of how agent actions, ratings, or decisions interact or are aggregated."},
                },
                "required": ["type", "description"],
            },
            "contradictions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of any material contradictions, logical inconsistencies, or conflicting constraints detected between the hypothesis, turn protocol, and actor personas. Return empty list if none exist.",
            },
        },
        "required": ["domain_archetype", "summary_readback", "assumptions", "feasibility_rules", "action_schema", "actors", "clearing_rule", "contradictions"],
    }

    instructions = (
        "You are the Muse Coding Agent for Hypothesis, an advanced multi-agent feedback and interaction simulation studio. "
        "Hypothesis simulates agentic interaction loops across diverse domains—including creative critique and reader reception, "
        "organizational deliberation, peer review, user research, strategic games, and microeconomics. "
        "Analyze the research hypothesis/goal, turn protocol, constraints, actor personas, and any supporting documents (manuscripts, papers, empirical data, guidelines). "
        "IMPORTANT DOMAIN FRAMING PRINCIPLE: Do NOT force-fit economic concepts (such as cost basis, pricing, marginal cost, profit, market clearing, or buyer/seller undercutting) onto non-economic or feedback-oriented scenarios. "
        "If the scenario is about gathering feedback on a creative piece (e.g., short story, manuscript, design, article), evaluating reader opinions, social voting, or peer review: "
        "- Define actors with authentic qualitative personas, perspectives, and critical criteria (do NOT give them a cost basis or prices). "
        "- Set 'action_schema' to reflect the domain's natural output (e.g., action_kind: 'review' or 'critique', primary_field: 'score' or 'rating', unit: 'points_out_of_10' or 'stars' or 'points'). "
        "- Set 'clearing_rule' to a feedback aggregation rule (e.g., type: 'independent_feedback' or 'rating_aggregation', description: 'Independent review collection and descriptive score synthesis'). "
        "- Formulate explicit assumptions and feasibility rules appropriate to creative/qualitative evaluation (e.g. fixed manuscript, uninfluenced evaluation, score bounds). "
        "Only use economic concepts, cost basis, and market clearing when the scenario is genuinely microeconomic (e.g. auctions, duopoly pricing, supply chain capacity, commodity trading). "
        "Critically evaluate whether any material contradictions, logical impossibilities, or conflicting requirements exist. "
        "If material contradictions exist, detail each contradiction explicitly in the 'contradictions' array. "
        "If there are no contradictions, return an empty array [] for 'contradictions'. "
        "Output valid JSON conforming to the schema."
    )

    if gateway is None or model_name is None:
        raise HTTPException(
            status_code=503,
            detail="Unable to connect to the LLM: No active API credentials configured. Please verify your API key or view completed simulations in the Featured Showcase.",
        )

    try:
        model_req = ModelRequest(
            actor_id="muse_coding_agent",
            model=model_name,
            instructions=instructions,
            input_json=json.dumps(req_data),
            response_schema=schema,
            max_output_tokens=16384,
        )
        res = await loop.run_in_executor(None, gateway.complete, model_req)
        blueprint = json.loads(res.text)
        if isinstance(blueprint, dict) and "domain_archetype" in blueprint:
            blueprint["processed_documents"] = processed_docs
            return blueprint
        raise ValueError("Model response did not contain a valid domain blueprint schema.")
    except Exception as err:
        logger.error("Live blueprint synthesis failed: %s", err)
        raise HTTPException(
            status_code=503,
            detail=f"Unable to connect to the LLM: {err}. Please check your connection or explore completed simulations in the Featured Showcase.",
        ) from err


@app.post("/api/simulations/run")
def run_simulation(req: RunSimulationRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Launches a simulation run (preset or custom) and returns a streaming handle."""
    scenario_id = req.scenario_id
    if req.kind == "preset" and scenario_id not in PRESETS:
        raise HTTPException(status_code=400, detail=f"Unknown preset: {scenario_id}")

    # Enforce contradictions check
    unresolved = req.parameters.get("contradictions", [])
    if isinstance(unresolved, list) and len(unresolved) > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot execute simulation with {len(unresolved)} unresolved contradiction(s). Please resolve them before proceeding.",
        )

    # Validate and extract custom manuscript PDF if supplied
    if "manuscript_pdf" in req.parameters and req.parameters["manuscript_pdf"]:
        pdf_doc = req.parameters["manuscript_pdf"]
        if isinstance(pdf_doc, dict):
            processed = process_uploaded_document(pdf_doc)
            if "error" in processed:
                raise HTTPException(
                    status_code=400,
                    detail=f"PDF parsing error: {processed['error']} Please provide a valid, readable PDF manuscript.",
                )
            req.parameters["processed_manuscript"] = processed.get("extracted_text", "")
            req.parameters["manuscript_filename"] = processed.get("filename", "custom_manuscript.pdf")

    job = JOBS.create_job(kind=req.kind, scenario_id=scenario_id, parameters=req.parameters)

    # Launch simulation task
    background_tasks.add_task(run_preset_simulation, job)

    return {
        "job_id": job.job_id,
        "status": "pending",
        "stream_url": f"/api/simulations/{job.job_id}/stream",
        "results_url": f"/api/simulations/{job.job_id}/results",
    }


@app.get("/api/simulations/{job_id}")
def get_simulation_status(job_id: str) -> dict[str, Any]:
    job = JOBS.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Simulation job not found")
    return {
        "job_id": job.job_id,
        "kind": job.kind,
        "scenario_id": job.scenario_id,
        "status": job.status,
        "created_at": job.created_at,
        "events_count": len(job.events),
        "decisions_count": len(job.decisions),
        "payoffs": job.payoffs,
        "metrics": job.metrics,
        "error": job.error,
    }


@app.get("/api/simulations/{job_id}/stream")
async def stream_simulation(job_id: str) -> StreamingResponse:
    job = JOBS.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Simulation job not found")

    queue: asyncio.Queue[str | None] = asyncio.Queue()
    job.listeners.append(queue)

    async def event_generator() -> AsyncGenerator[str]:
        # Emit initial status
        init_data = {
            "type": "init",
            "job_id": job.job_id,
            "scenario_id": job.scenario_id,
            "status": job.status,
        }
        yield f"data: {json.dumps(init_data)}\n\n"

        # Stream replayed past events if already running/done
        for d in job.decisions:
            yield f"data: {json.dumps({'type': 'decision', **d})}\n\n"
        for e in job.events:
            yield f"data: {json.dumps({'type': 'metric_tick', 'data': e})}\n\n"

        # Stream live events
        try:
            while True:
                msg = await queue.get()
                if msg is None:
                    break
                yield msg
        finally:
            if queue in job.listeners:
                job.listeners.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.get("/api/simulations/{job_id}/results")
def get_simulation_results(job_id: str) -> dict[str, Any]:
    job = JOBS.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Simulation job not found")

    return {
        "job_id": job.job_id,
        "scenario_id": job.scenario_id,
        "status": job.status,
        "parameters": job.parameters,
        "payoffs": job.payoffs,
        "metrics": job.metrics,
        "events": job.events,
        "decisions": job.decisions,
        "notebook_data": job.notebook_data,
        "error": job.error,
        "downloads": {
            "notebook": f"/api/simulations/{job.job_id}/download/notebook",
            "events": f"/api/simulations/{job.job_id}/download/events",
        },
    }


@app.get("/api/simulations/{job_id}/download/{fmt}")
def download_artifact(job_id: str, fmt: str) -> Any:
    job = JOBS.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Simulation job not found")

    if fmt == "events":
        lines = [json.dumps(e) for e in job.events]
        return PlainTextResponse(
            content="\n".join(lines),
            media_type="application/x-ndjson",
            headers={"Content-Disposition": f"attachment; filename={job_id}_events.jsonl"},
        )
    elif fmt == "notebook":
        if job.notebook_data:
            nb = job.notebook_data
        else:
            from .presets import build_complete_experiment_notebook
            nb = build_complete_experiment_notebook(job)
            job.notebook_data = nb
        return JSONResponse(
            content=nb,
            headers={"Content-Disposition": f"attachment; filename={job_id}_results.ipynb"},
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid format requested")
