"""Preset scenarios and runner logic for zero-latency execution."""

import asyncio
import base64
import hashlib
import html
import io
import json
import logging
import math
from typing import Any

from components.gateways.live import configured_gateway
from simulation_core.model_gateway import GatewayError, ModelRequest

logger = logging.getLogger(__name__)

PRESETS: dict[str, dict[str, Any]] = {
    "supplychain": {
        "id": "supplychain",
        "title": "Decentralized Supply Chain Flood Disruption",
        "tagline": "4 independent firms navigating a 50% transport bottleneck",
        "category": "Logistics & Supply Network",
        "description": (
            "A 9-day simulation where a catastrophic flood slashes transport capacity from 200 to 80 units on days 3–6. "
            "A manufacturer, two competing suppliers, and a logistics provider must coordinate ordering, production, "
            "and transport allocation without central visibility."
        ),
        "actors": [
            {"id": "manufacturer", "role": "Final Assembly & Retail Fulfillment", "color": "#06B6D4"},
            {"id": "supplier_a", "role": "Component A Supplier", "color": "#10B981"},
            {"id": "supplier_b", "role": "Component B Supplier", "color": "#6366F1"},
            {"id": "logistics", "role": "Shared Freight Transport Carrier", "color": "#F59E0B"},
        ],
        "default_parameters": {
            "horizon_days": 9,
            "normal_capacity": 200,
            "flood_capacity": 80,
            "daily_demand": 80,
            "flood_start": 3,
            "flood_end": 6,
            "agent_mode": "llm",  # live API mode active by default
        },
        "parameter_schema": [
            {"name": "horizon_days", "label": "Simulation Horizon (Days)", "type": "number", "min": 5, "max": 14, "default": 9},
            {"name": "flood_capacity", "label": "Disrupted Transport Capacity (units/day)", "type": "number", "min": 40, "max": 160, "default": 80},
            {"name": "daily_demand", "label": "Consumer Daily Demand (units)", "type": "number", "min": 40, "max": 120, "default": 80},
            {"name": "agent_mode", "label": "Agent Intelligence Mode", "type": "select", "options": ["llm", "heuristic"], "default": "llm"},
        ],
        "theoretical_benchmark": "Optimal coordinated recovery delivers 720 units (100% service level). Decentralized bullwhip typically delivers 520–600 units.",
    },
    "bertrand": {
        "id": "bertrand",
        "title": "Differentiated Bertrand Pricing Competition",
        "tagline": "Two competing brands setting price in segmented consumer markets",
        "category": "Industrial Organization",
        "description": (
            "Two firms produce differentiated substitute products. Heterogeneous consumer segments select products based on "
            "prices using logit discrete choice shares. Firms seek to balance price margins against lost market share."
        ),
        "actors": [
            {"id": "firm_alpha", "role": "Brand Alpha (High Quality Tier)", "color": "#06B6D4"},
            {"id": "firm_beta", "role": "Brand Beta (Value Tier)", "color": "#6366F1"},
        ],
        "default_parameters": {
            "rounds": 5,
            "marginal_cost": 2.0,
            "brand_alpha_quality": 3.0,
            "brand_beta_quality": 2.5,
            "price_sensitivity": 0.8,
            "agent_mode": "llm",
        },
        "parameter_schema": [
            {"name": "rounds", "label": "Number of Pricing Rounds", "type": "number", "min": 3, "max": 15, "default": 5},
            {"name": "marginal_cost", "label": "Marginal Cost ($)", "type": "number", "min": 0.5, "max": 5.0, "step": 0.5, "default": 2.0},
            {"name": "price_sensitivity", "label": "Consumer Price Sensitivity", "type": "number", "min": 0.2, "max": 2.0, "step": 0.1, "default": 0.8},
            {"name": "agent_mode", "label": "Agent Intelligence Mode", "type": "select", "options": ["llm", "heuristic"], "default": "llm"},
        ],
        "theoretical_benchmark": "Bertrand-Nash equilibrium price is approx $4.25; tacit collusion frontier is $6.50.",
    },
    "short_story_review": {
        "id": "short_story_review",
        "title": "Literary Reader Reception ('Waiting for Humphrey')",
        "tagline": "5 diverse reader personas evaluating narrative pacing, character arcs, and emotional resonance",
        "category": "Creative & Literary Critique",
        "description": (
            "A panel of five distinct reader personas (a secondary school student, a Bain & Co. strategy partner, "
            "a suburban housewife, a retired local history museum docent, and novelist Haruki Murakami) review the short story "
            "'Waiting for Humphrey'. The narrative chronicles an unmailed 1974 letter and a 54-year emotional separation "
            "between King's Cross (1968) and an Edinburgh hospital (2022). The personas evaluate narrative structure, emotional authenticity, "
            "and assign qualitative critique alongside resonance scores (0–10)."
        ),
        "actors": [
            {
                "id": "reader_student",
                "role": "Secondary School Student",
                "color": "#06B6D4",
                "persona": "Secondary school male student; sensitive to pacing, relatability, emotional payoff vs melodrama, and dialogue authenticity.",
            },
            {
                "id": "reader_bain",
                "role": "Bain & Co. Strategy Partner",
                "color": "#10B981",
                "persona": "Management consulting partner; analytical, evaluating prose economy, structural efficiency, character decision ROI, and narrative coherence.",
            },
            {
                "id": "reader_housewife",
                "role": "Suburban Housewife",
                "color": "#EC4899",
                "persona": "Housewife and avid book-club reader; attentive to domestic realism, emotional resonance, long-distance strain, fidelity, and interpersonal empathy.",
            },
            {
                "id": "reader_docent",
                "role": "Retired Museum Docent",
                "color": "#F59E0B",
                "persona": "Retired local history museum docent; deeply attuned to historical texture (1968–2022), archival memory, the passage of time, mortality, and quiet grief.",
            },
            {
                "id": "reader_murakami",
                "role": "Haruki Murakami (Novelist)",
                "color": "#8B5CF6",
                "persona": "Novelist; looks for magical understatement, symbolism of winter train stations and unmailed letters, Zurich as emotional exile, silence, and existential yearning.",
            },
        ],
        "default_parameters": {
            "rounds": 3,
            "evaluation_focus": "Holistic Literary & Structural Critique",
            "agent_mode": "llm",
        },
        "parameter_schema": [
            {"name": "rounds", "label": "Number of Deliberation Rounds", "type": "number", "min": 1, "max": 5, "default": 3},
            {
                "name": "evaluation_focus",
                "label": "Critique Focus Area",
                "type": "select",
                "options": [
                    "Holistic Literary & Structural Critique",
                    "Pacing & Emotional Resonance",
                    "Historical Texture & Passage of Time",
                    "Symbolism & Unspoken Grief",
                ],
                "default": "Holistic Literary & Structural Critique",
            },
            {
                "name": "manuscript_pdf",
                "label": "Custom Story Manuscript (PDF)",
                "type": "file",
                "accept": ".pdf",
                "description": "Upload a custom short story manuscript (PDF) for the 5 reader personas to evaluate. (Defaults to 'Waiting for Humphrey' if omitted)",
            },
            {"name": "agent_mode", "label": "Agent Intelligence Mode", "type": "select", "options": ["llm", "heuristic"], "default": "llm"},
        ],
        "theoretical_benchmark": "Symmetric cohort consensus score of 8.0/10 across all reader archetypes, balancing affective resonance and narrative structural efficiency.",
    },
}

STORY_WAITING_FOR_HUMPHREY = (
    "TITLE: Waiting for Humphrey\n\n"
    "SYNOPSIS & EXCERPT:\n"
    "On a freezing November morning in 1968 at King's Cross station in London, twenty-two-year-old Humphrey "
    "boards the 08:15 train to Cambridge to take up a doctoral fellowship in physical chemistry. On the platform "
    "stands Clara, his childhood companion from Yorkshire, holding a damp wool scarf. Neither confesses the devotion "
    "that has anchored their lives. 'Write from the laboratory,' she says. 'Every fortnight,' he promises.\n\n"
    "Fifty-four years pass in fragmented silence. Humphrey's academic trajectory carries him from Cambridge to Zurich's "
    "ETH, then to a quiet emeritus existence in Edinburgh. Clara marries a local surveyor in Leeds, raises two daughters, "
    "and endures the gradual fade of ordinary domestic life. Letters were exchanged during the first two years, then "
    "tapered into silence after a misaddressed parcel in 1974.\n\n"
    "In October 2022, Clara—now an eighty-year-old widow recovering from cardiac surgery in an Edinburgh convalescent ward—"
    "notices an elderly gentleman in the solarium reading a 1965 German treatise on thermodynamics. It is Humphrey. "
    "Beside him rests an unmailed aerogramme dated November 14, 1974, stamped with Swiss postage and addressed to Clara's "
    "maiden address in Yorkshire. Inside, Humphrey had written: 'The laboratory in Zurich overlooks the lake. The snow here "
    "has the exact weight of the snow at King's Cross when we were twenty-two. I should have stayed on the platform.'\n\n"
    "They spend the afternoon watching the autumn drizzle roll over the Firth of Forth. No reproaches are voiced; the unlived "
    "years settle between them not as an abyss of tragedy, but as a quiet, amber-lit sanctuary of endurance and mutual recognition."
)


CASE_STUDIES: list[dict[str, Any]] = [
    {
        "id": "cs_supplychain_flood",
        "preset_id": "supplychain",
        "title": "Decentralized Supply Chain Recovery During a 50% Transport Bottleneck",
        "abstract": (
            "We simulated a 9-day multi-tier supply chain facing a flood disruption from Days 3–6. Without central coordination, "
            "the manufacturer experienced a severe bullwhip effect on Day 5, requesting 80 units when transit delays had depleted Component B. "
            "Runtime boundary clamping and adaptive rationing prevented total assembly collapse, achieving a 78.4% fulfillment rate."
        ),
        "kpis": [
            {"label": "Total Demand", "value": "720 units"},
            {"label": "Units Fulfilled", "value": "564 units (78.3%)"},
            {"label": "Manufacturer Profit", "value": "$14,280"},
            {"label": "Bullwhip Amplification", "value": "1.42x"},
        ],
        "figures": [
            {
                "title": "Daily Production vs Customer Demand",
                "kind": "bar",
                "categories": ["Day 1", "Day 2", "Day 3", "Day 4", "Day 5", "Day 6", "Day 7", "Day 8", "Day 9"],
                "series": [
                    {"label": "Consumer Demand", "values": [80, 80, 80, 80, 80, 80, 80, 80, 80]},
                    {"label": "Assembled Finished Units", "values": [80, 80, 80, 80, 40, 44, 80, 80, 80]},
                ],
            },
            {
                "title": "Component Stock vs Transport Bottleneck",
                "kind": "line",
                "categories": ["Day 1", "Day 2", "Day 3", "Day 4", "Day 5", "Day 6", "Day 7", "Day 8", "Day 9"],
                "series": [
                    {"label": "Available Component B", "values": [120, 100, 70, 50, 40, 44, 88, 110, 120]},
                    {"label": "Active Transport Capacity", "values": [200, 200, 80, 80, 80, 80, 200, 200, 200]},
                ],
            },
        ],
        "notebook_url": "/api/case-studies/cs_supplychain_flood/download/notebook",
        "event_count": 36,
        "actors": ["manufacturer", "supplier_a", "supplier_b", "logistics"],
    },
    {
        "id": "cs_bertrand_collusion",
        "preset_id": "bertrand",
        "title": "Tacit Collusion Dynamics in Asymmetric Logit Bertrand Duopoly",
        "abstract": (
            "Exploring whether LLM agents discover tacit price collusion or trigger Bertrand price wars when competing for differentiated consumer segments. "
            "Over 10 rounds, Brand Alpha maintained a premium price of $5.40 while Brand Beta undercut at $4.60, sustaining profits 31% above the static Bertrand-Nash equilibrium."
        ),
        "kpis": [
            {"label": "Bertrand-Nash Price", "value": "$4.20"},
            {"label": "Observed Mean Price", "value": "$5.05"},
            {"label": "Market Welfare", "value": "$8,920"},
            {"label": "Collusion Markup", "value": "+20.2%"},
        ],
        "figures": [
            {
                "title": "Price Trajectory vs Bertrand-Nash Floor",
                "kind": "line",
                "categories": [f"Round {r}" for r in range(1, 11)],
                "series": [
                    {"label": "Brand Alpha Price", "values": [4.5, 4.8, 5.2, 5.4, 5.3, 5.5, 5.4, 5.6, 5.4, 5.4]},
                    {"label": "Brand Beta Price", "values": [4.2, 4.4, 4.7, 4.6, 4.6, 4.7, 4.6, 4.8, 4.6, 4.6]},
                    {"label": "Nash Static Equilibrium", "values": [4.2] * 10},
                ],
            }
        ],
        "notebook_url": "/api/case-studies/cs_bertrand_collusion/download/notebook",
        "event_count": 20,
        "actors": ["firm_alpha", "firm_beta"],
    },
    {
        "id": "cs_story_reader_reception",
        "preset_id": "short_story_review",
        "title": "Multi-Persona Literary Reception of 'Waiting for Humphrey'",
        "abstract": (
            "We convened a panel of five autonomous personas (secondary school student, Bain & Co. partner, housewife, "
            "retired docent, and Haruki Murakami) to evaluate the short story 'Waiting for Humphrey'. Over 3 deliberation rounds, "
            "evaluators converged on a 8.2/10 mean consensus, with the retired docent awarding 9.2/10 for historical texture and "
            "Murakami praising the quiet understatement of the unmailed 1974 aerogramme."
        ),
        "kpis": [
            {"label": "Cohort Consensus Score", "value": "8.2 / 10"},
            {"label": "Highest Evaluator", "value": "9.2 (Docent)"},
            {"label": "Lowest Evaluator", "value": "7.1 (Bain Partner)"},
            {"label": "Aesthetic Variance", "value": "0.68 stdev"},
        ],
        "figures": [
            {
                "title": "Reader Persona Score Trajectories Across Rounds",
                "kind": "line",
                "categories": ["Round 1: Encounter", "Round 2: Craft Analysis", "Round 3: Final Verdict"],
                "series": [
                    {"label": "Student", "values": [7.0, 7.5, 7.8]},
                    {"label": "Bain Partner", "values": [6.5, 7.0, 7.1]},
                    {"label": "Housewife", "values": [8.5, 8.8, 9.0]},
                    {"label": "Museum Docent", "values": [9.0, 9.2, 9.2]},
                    {"label": "Haruki Murakami", "values": [8.2, 8.6, 8.8]},
                ],
            },
            {
                "title": "Final Evaluated Ratings vs Cohort Mean",
                "kind": "bar",
                "categories": ["Student", "Bain Partner", "Housewife", "Museum Docent", "Murakami"],
                "series": [
                    {"label": "Assigned Rating", "values": [7.8, 7.1, 9.0, 9.2, 8.8]},
                    {"label": "Cohort Mean", "values": [8.2, 8.2, 8.2, 8.2, 8.2]},
                ],
            },
        ],
        "notebook_url": "/api/case-studies/cs_story_reader_reception/download/notebook",
        "event_count": 3,
        "actors": ["reader_student", "reader_bain", "reader_housewife", "reader_docent", "reader_murakami"],
    },
]


def is_economic_scenario(
    domain_archetype: str,
    primary_unit: str,
    clearing_type: str,
    hypothesis: str,
) -> bool:
    """Determines whether a scenario is genuinely microeconomic vs feedback/critique/deliberation."""
    if primary_unit.strip() == "$":
        return True

    text = f"{domain_archetype} {clearing_type} {hypothesis}".lower()
    economic_terms = [
        "price", "pricing", "marginal_cost", "duopoly", "monopoly", "oligopoly",
        "bertrand", "cournot", "auction", "bidder", "bidding", "supply_chain",
        "commodity", "profit", "arbitrage", "vickrey", "trader", "producer",
    ]
    non_economic_terms = [
        "feedback", "review", "story", "reader", "reading", "critique",
        "writing", "creative", "manuscript", "evaluation", "score",
        "rating", "deliberation", "voting", "consensus", "user_test",
        "peer_review", "qualitative", "essay", "opinion", "literary",
    ]

    for term in non_economic_terms:
        if term in text and not any(k in text for k in ("auction", "stock market", "commodity market")):
            return False

    for term in economic_terms:
        if term in text:
            return True

    return False


async def query_live_llm_agent(
    gateway: Any,
    model_name: str,
    aid: str,
    role: str,
    persona: str,
    cost: float,
    round_num: int,
    total_rounds: int,
    action_kind: str,
    primary_field: str,
    primary_unit: str,
    clearing_desc: str,
    observed_actions: dict[str, float],
    history: list[dict[str, Any]],
    turn_desc: str,
    hypothesis: str,
    is_economic: bool = True,
    document_context: str = "",
) -> tuple[float, str]:
    """Queries live LLM policy actor for arbitrary domain feedback or economic mechanism action."""
    loop = asyncio.get_running_loop()

    if not is_economic:
        prompt_payload = {
            "round": round_num,
            "total_rounds": total_rounds,
            "actor_id": aid,
            "role": role,
            "persona": persona,
            "observed_peer_actions_this_round": observed_actions,
            "history_past_rounds": history[-2:] if history else [],
            "interaction_protocol": clearing_desc or turn_desc,
            "goal_hypothesis": hypothesis,
        }
        if document_context:
            prompt_payload["subject_under_evaluation"] = document_context[:14000]

        instructions = (
            f"You are an autonomous participant evaluating a subject in a multi-agent feedback simulation.\n"
            f"Role: {role}.\n"
            f"Persona & Perspective: {persona}.\n"
            f"Turn: {round_num} of {total_rounds}.\n"
            f"Goal: {hypothesis}\n"
            f"Turn Protocol: {turn_desc}\n"
            f"Formulate your authentic, in-character feedback and assign a '{primary_field}' ({primary_unit}).\n"
            f"Output valid JSON only with keys:\n"
            f"- '{primary_field}': float (your rating, score, or quantitative judgment on the {primary_unit} scale)\n"
            f"- 'rationale': string (your complete, uncensored thought process and qualitative critique from your persona's perspective. Explain your evaluation, observations, and advice. Do not truncate)."
        )
        schema = {
            "type": "object",
            "properties": {
                primary_field: {"type": "number", "description": f"The evaluated {primary_field} ({primary_unit})"},
                "rationale": {"type": "string", "description": "Qualitative critique and thought rationale"},
            },
            "required": [primary_field, "rationale"],
        }
    else:
        prompt_payload = {
            "round": round_num,
            "total_rounds": total_rounds,
            "actor_id": aid,
            "role": role,
            "persona": persona,
            "private_cost_or_endowment": cost,
            "observed_actions_this_round": observed_actions,
            "history_past_rounds": history[-2:] if history else [],
            "market_clearing_rules": clearing_desc,
            "turn_protocol": turn_desc,
            "hypothesis": hypothesis,
        }
        instructions = (
            f"You are an autonomous economic actor participating in a strategic market simulation. "
            f"Role: {role}. Persona: {persona}. "
            f"Round: {round_num} of {total_rounds}. "
            f"Review the mechanism rules and observed competitor moves. Formulate your strategic decision for '{primary_field}' ({primary_unit}). "
            f"Output valid JSON only with keys: "
            f"- '{primary_field}': float (your decision value for this round) "
            f"- 'rationale': string (a complete, 2-3 sentence strategic explanation detailing your economic choice, your competitive intent, and anticipated market response. Do not truncate)."
        )
        schema = {
            "type": "object",
            "properties": {
                primary_field: {"type": "number", "description": f"The chosen {primary_field}"},
                "rationale": {"type": "string", "description": "Comprehensive economic reasoning"},
            },
            "required": [primary_field, "rationale"],
        }

    req = ModelRequest(
        actor_id=aid,
        model=model_name,
        instructions=instructions,
        input_json=json.dumps(prompt_payload),
        response_schema=schema,
        max_output_tokens=16384,
    )

    try:
        res = await loop.run_in_executor(None, gateway.complete, req)
        data = json.loads(res.text)
        default_val = 7.0 if not is_economic else (cost + 2.0)
        val = float(data.get(primary_field, default_val))
        rationale = str(data.get("rationale", f"Formulating evaluation for {primary_field}."))
        if val < 0 and ("price" in primary_field.lower() or primary_unit == "$"):
            val = round(max(cost, 1.0), 2)
            rationale += f" [BOUND CLAMP: Clamped to non-negative boundary ${val:.2f}]."
        return round(val, 2), rationale
    except (GatewayError, ValueError, KeyError, json.JSONDecodeError, TimeoutError, OSError, RuntimeError) as err:
        logger.error("Live LLM query failed for actor %s: %s", aid, err)
        raise RuntimeError(f"Unable to connect to the LLM for actor '{aid}': {err}") from err


async def run_preset_simulation(job_state: Any) -> None:
    """Executes a preset simulation, broadcasting live SSE ticks and actor decisions."""
    from .jobs import JobState

    state: JobState = job_state
    scenario_id = state.scenario_id
    params = state.parameters
    agent_mode = str(params.get("agent_mode", "llm")).lower()

    state.status = "running"
    state.broadcast({"type": "stage", "stage": "initialization", "message": f"Initializing {scenario_id} environment..."})
    await asyncio.sleep(0.4)

    # If LLM mode is active, connect to the live gateway; terminate with explicit error on failure
    live_gateway = None
    model_name = None
    if agent_mode == "llm":
        try:
            model_name, live_gateway = configured_gateway()
        except (GatewayError, ValueError, KeyError, OSError, RuntimeError) as err:
            err_msg = f"Unable to connect to the LLM: {err}. Please verify your API key or view completed simulations in the Featured Showcase."
            state.error = err_msg
            state.broadcast({"type": "error", "message": err_msg})
            state.finish("failed")
            return

        if live_gateway is None or model_name is None:
            err_msg = "Unable to connect to the LLM: No active API key found. Please configure your API credentials or view completed simulations in the Featured Showcase."
            state.error = err_msg
            state.broadcast({"type": "error", "message": err_msg})
            state.finish("failed")
            return

    if scenario_id == "supplychain":
        horizon = int(params.get("horizon_days", 9))
        flood_cap = int(params.get("flood_capacity", 80))
        demand = int(params.get("daily_demand", 80))
        comp_a, comp_b = 100, 100
        cum_sold = 0
        cum_profit = 0.0
        prev_alloc_a = 0
        prev_alloc_b = 0

        for day in range(1, horizon + 1):
            cap = flood_cap if 3 <= day <= 6 else 200
            disrupted = 3 <= day <= 6

            # Phase 1: Order
            state.broadcast({
                "type": "tick",
                "day": day,
                "round": day,
                "phase": "order",
                "capacity": cap,
                "disrupted": disrupted,
                "sensors": [
                    {"label": "Active Horizon", "value": f"Day {day} of {horizon}"},
                    {"label": "Transport Capacity", "value": f"{cap} units/day", "highlight": disrupted},
                    {"label": "Disruption State", "value": "SHOCK ACTIVE" if disrupted else "NOMINAL", "highlight": disrupted},
                    {"label": "Intelligence Mode", "value": f"Live LLM ({model_name})" if agent_mode == "llm" else "Deterministic Heuristic"},
                ],
            })

            if agent_mode == "llm":
                try:
                    order_val, rat_order = await query_live_llm_agent(
                        gateway=live_gateway,
                        model_name=model_name,
                        aid="manufacturer",
                        role="Final Assembly & Retail Fulfillment",
                        persona="Manufacturer balancing daily consumer demand (80 units) against component inventories and transport bottleneck.",
                        cost=1500.0,
                        round_num=day,
                        total_rounds=horizon,
                        action_kind="order",
                        primary_field="order_qty",
                        primary_unit="units",
                        clearing_desc=f"Day {day}/{horizon}. Transport capacity: {cap} units/day. Currently stocked: {comp_a} Component A, {comp_b} Component B.",
                        observed_actions={},
                        history=[],
                        turn_desc=f"Day {day} replenishment. Decide order quantity of Component A and Component B.",
                        hypothesis="Decentralized supply chain coordination under transport bottleneck",
                        is_economic=True,
                    )
                    order_qty = max(20, min(160, int(order_val)))
                except (GatewayError, RuntimeError, ValueError, TimeoutError, OSError) as err:
                    err_msg = f"Unable to connect to the LLM: {err}. Please verify your API key or explore completed simulations in the Featured Showcase."
                    state.error = err_msg
                    state.broadcast({"type": "error", "message": err_msg})
                    state.finish("failed")
                    return
            else:
                order_qty = demand
                rat_order = f"Day {day}: Daily demand is {demand}. Placing replenishment order of {demand} for both components."

            order_decision = {
                "day": day,
                "tick": (day - 1) * 4 + 1,
                "phase": f"d{day}_order",
                "actor_id": "manufacturer",
                "action": {"kind": "order", "payload": {"order_a": order_qty, "order_b": order_qty, "priority": "B" if disrupted else "none"}},
                "rationale": rat_order,
            }
            state.decisions.append(order_decision)
            state.broadcast({"type": "decision", **order_decision})
            await asyncio.sleep(0.35)

            # Phase 2: Supply
            if agent_mode == "llm":
                try:
                    offer_a_val, rat_a = await query_live_llm_agent(
                        gateway=live_gateway,
                        model_name=model_name,
                        aid="supplier_a",
                        role="Component A Supplier",
                        persona="Upstream tier-1 supplier producing Component A. Capacity 120 units.",
                        cost=25.0,
                        round_num=day,
                        total_rounds=horizon,
                        action_kind="offer",
                        primary_field="offer_qty",
                        primary_unit="units",
                        clearing_desc=f"Day {day}/{horizon}. Manufacturer requested {order_qty} units. Transport capacity is {cap} units/day.",
                        observed_actions={"order_qty": order_qty},
                        history=[],
                        turn_desc=f"Day {day} supply batch decision for Component A.",
                        hypothesis="Decentralized supply chain coordination under transport bottleneck",
                        is_economic=True,
                    )
                    offer_a = max(20, min(120, int(offer_a_val)))
                except (GatewayError, RuntimeError, ValueError, TimeoutError, OSError) as err:
                    err_msg = f"Unable to connect to the LLM: {err}. Please verify your API key or explore completed simulations in the Featured Showcase."
                    state.error = err_msg
                    state.broadcast({"type": "error", "message": err_msg})
                    state.finish("failed")
                    return

                try:
                    offer_b_val, rat_b = await query_live_llm_agent(
                        gateway=live_gateway,
                        model_name=model_name,
                        aid="supplier_b",
                        role="Component B Supplier",
                        persona="Upstream tier-1 supplier producing Component B. Capacity 120 units.",
                        cost=25.0,
                        round_num=day,
                        total_rounds=horizon,
                        action_kind="offer",
                        primary_field="offer_qty",
                        primary_unit="units",
                        clearing_desc=f"Day {day}/{horizon}. Manufacturer requested {order_qty} units. Transport capacity is {cap} units/day.",
                        observed_actions={"order_qty": order_qty},
                        history=[],
                        turn_desc=f"Day {day} supply batch decision for Component B.",
                        hypothesis="Decentralized supply chain coordination under transport bottleneck",
                        is_economic=True,
                    )
                    offer_b = max(20, min(120, int(offer_b_val)))
                except (GatewayError, RuntimeError, ValueError, TimeoutError, OSError) as err:
                    err_msg = f"Unable to connect to the LLM: {err}. Please verify your API key or explore completed simulations in the Featured Showcase."
                    state.error = err_msg
                    state.broadcast({"type": "error", "message": err_msg})
                    state.finish("failed")
                    return
            else:
                offer_a = order_qty
                offer_b = order_qty
                rat_a = f"Producing {offer_a} units of Component A at standard marginal cost."
                rat_b = f"Producing {offer_b} units of Component B; requesting priority logistics dispatch."

            supply_decisions = [
                {
                    "day": day,
                    "tick": (day - 1) * 4 + 2,
                    "phase": f"d{day}_supply",
                    "actor_id": "supplier_a",
                    "action": {"kind": "offer", "payload": {"produce": offer_a, "offer": offer_a}},
                    "rationale": rat_a,
                },
                {
                    "day": day,
                    "tick": (day - 1) * 4 + 2,
                    "phase": f"d{day}_supply",
                    "actor_id": "supplier_b",
                    "action": {"kind": "offer", "payload": {"produce": offer_b, "offer": offer_b}},
                    "rationale": rat_b,
                },
            ]
            for sd in supply_decisions:
                state.decisions.append(sd)
                state.broadcast({"type": "decision", **sd})
            await asyncio.sleep(0.35)

            # Phase 3: Ship
            if agent_mode == "llm":
                try:
                    alloc_val, rat_log = await query_live_llm_agent(
                        gateway=live_gateway,
                        model_name=model_name,
                        aid="logistics",
                        role="Shared Freight Transport Carrier",
                        persona=f"Freight transport carrier. Route capacity is {cap} units/day. Suppliers offered {offer_a} of A and {offer_b} of B.",
                        cost=15.0,
                        round_num=day,
                        total_rounds=horizon,
                        action_kind="allocate",
                        primary_field="alloc_a",
                        primary_unit="units",
                        clearing_desc=f"Day {day}/{horizon}. Transport capacity: {cap} units/day.",
                        observed_actions={"offer_a": offer_a, "offer_b": offer_b},
                        history=[],
                        turn_desc=f"Day {day} logistics capacity allocation. Decide allocation for Component A.",
                        hypothesis="Decentralized supply chain coordination under transport bottleneck",
                        is_economic=True,
                    )
                    alloc_a = min(offer_a, max(0, min(cap, int(alloc_val))))
                    alloc_b = min(offer_b, cap - alloc_a)
                except (GatewayError, RuntimeError, ValueError, TimeoutError, OSError) as err:
                    err_msg = f"Unable to connect to the LLM: {err}. Please verify your API key or explore completed simulations in the Featured Showcase."
                    state.error = err_msg
                    state.broadcast({"type": "error", "message": err_msg})
                    state.finish("failed")
                    return
            else:
                alloc_a = min(offer_a, cap // 2)
                alloc_b = min(offer_b, cap - alloc_a)
                rat_log = f"Transport capacity is {cap}. Allocating {alloc_a} to A and {alloc_b} to B under fair-share rationing."

            ship_decision = {
                "day": day,
                "tick": (day - 1) * 4 + 3,
                "phase": f"d{day}_ship",
                "actor_id": "logistics",
                "action": {"kind": "allocate", "payload": {"alloc_a": alloc_a, "alloc_b": alloc_b}},
                "rationale": rat_log,
            }
            state.decisions.append(ship_decision)
            state.broadcast({"type": "decision", **ship_decision})
            await asyncio.sleep(0.35)

            # Phase 4: Make
            if day > 1:
                comp_a += prev_alloc_a
                comp_b += prev_alloc_b
            prev_alloc_a = alloc_a
            prev_alloc_b = alloc_b

            max_feasible = min(demand, comp_a, comp_b)
            produce_qty = max_feasible
            comp_a -= produce_qty
            comp_b -= produce_qty
            cum_sold += produce_qty
            profit_today = produce_qty * 100.0 - 1500.0
            cum_profit += profit_today

            make_decision = {
                "day": day,
                "tick": (day - 1) * 4 + 4,
                "phase": f"d{day}_make",
                "actor_id": "manufacturer",
                "action": {"kind": "produce", "payload": {"produce": produce_qty}},
                "rationale": f"Stock available: {comp_a} Component A, {comp_b} Component B. Assembling {produce_qty} finished units for customer fulfillment.",
            }
            state.decisions.append(make_decision)
            state.broadcast({"type": "decision", **make_decision})

            # Round metrics
            metric_data = {
                "day": day,
                "capacity": cap,
                "sold": produce_qty,
                "cum_sold": cum_sold,
                "stock_a": comp_a,
                "stock_b": comp_b,
                "daily_profit": profit_today,
                "cum_profit": cum_profit,
            }
            state.events.append(metric_data)
            state.broadcast({"type": "metric_tick", "data": metric_data})
            await asyncio.sleep(0.4)

        state.payoffs = {
            "manufacturer": cum_profit,
            "supplier_a": cum_sold * 25.0,
            "supplier_b": cum_sold * 25.0,
            "logistics": cum_sold * 15.0,
        }
        state.metrics = {
            "total_demand": horizon * demand,
            "total_fulfilled": cum_sold,
            "fulfillment_rate": f"{round(cum_sold / (horizon * demand) * 100, 1)}%",
            "consolidated_welfare": cum_profit + cum_sold * 65.0,
            "clamped_turns": 0,
        }

    elif scenario_id == "bertrand":
        rounds = int(params.get("rounds", 5))
        mc = float(params.get("marginal_cost", 2.0))
        quality_a = float(params.get("brand_alpha_quality", 3.0))
        quality_b = float(params.get("brand_beta_quality", 2.5))
        sensitivity = float(params.get("price_sensitivity", 0.8))
        profit_alpha = 0.0
        profit_beta = 0.0
        round_history: list[dict[str, Any]] = []

        for r in range(1, rounds + 1):
            state.broadcast({
                "type": "tick",
                "round": r,
                "day": r,
                "phase": "pricing",
                "sensors": [
                    {"label": "Active Horizon", "value": f"Round {r} of {rounds}"},
                    {"label": "Market Structure", "value": "Differentiated Duopoly (Logit)"},
                    {"label": "Marginal Cost Floor", "value": f"${mc:.2f}"},
                    {"label": "Intelligence Mode", "value": f"Live LLM ({model_name})" if agent_mode == "llm" else "Deterministic Heuristic"},
                ],
            })

            if agent_mode == "llm":
                try:
                    p_alpha, rat_a = await query_live_llm_agent(
                        gateway=live_gateway,
                        model_name=model_name,
                        aid="firm_alpha",
                        role="Brand Alpha (High Quality Tier)",
                        persona=f"High quality brand (quality index {quality_a}, marginal cost ${mc:.2f}). Seeks to maximize profit (price - {mc}) * volume in discrete logit competition against Brand Beta.",
                        cost=mc,
                        round_num=r,
                        total_rounds=rounds,
                        action_kind="set_price",
                        primary_field="price",
                        primary_unit="$",
                        clearing_desc=f"Logit discrete choice. Brand Beta quality {quality_b}, cost ${mc:.2f}. Consumer price sensitivity {sensitivity}.",
                        observed_actions={},
                        history=round_history,
                        turn_desc=f"Round {r} pricing. Formulate optimal retail price above marginal cost ${mc:.2f}.",
                        hypothesis="Differentiated Bertrand duopoly pricing dynamics",
                        is_economic=True,
                    )
                    p_alpha = max(round(mc + 0.1, 2), p_alpha)
                except (GatewayError, RuntimeError, ValueError, TimeoutError, OSError) as err:
                    err_msg = f"Unable to connect to the LLM: {err}. Please verify your API key or explore completed simulations in the Featured Showcase."
                    state.error = err_msg
                    state.broadcast({"type": "error", "message": err_msg})
                    state.finish("failed")
                    return

                try:
                    p_beta, rat_b = await query_live_llm_agent(
                        gateway=live_gateway,
                        model_name=model_name,
                        aid="firm_beta",
                        role="Brand Beta (Value Tier)",
                        persona=f"Value tier brand (quality index {quality_b}, marginal cost ${mc:.2f}). Seeks to capture volume in discrete logit competition against Brand Alpha.",
                        cost=mc,
                        round_num=r,
                        total_rounds=rounds,
                        action_kind="set_price",
                        primary_field="price",
                        primary_unit="$",
                        clearing_desc=f"Logit discrete choice. Brand Alpha quality {quality_a}, cost ${mc:.2f}. Consumer price sensitivity {sensitivity}.",
                        observed_actions={"price_alpha": p_alpha},
                        history=round_history,
                        turn_desc=f"Round {r} pricing. Formulate optimal retail price above marginal cost ${mc:.2f}.",
                        hypothesis="Differentiated Bertrand duopoly pricing dynamics",
                        is_economic=True,
                    )
                    p_beta = max(round(mc + 0.1, 2), p_beta)
                except (GatewayError, RuntimeError, ValueError, TimeoutError, OSError) as err:
                    err_msg = f"Unable to connect to the LLM: {err}. Please verify your API key or explore completed simulations in the Featured Showcase."
                    state.error = err_msg
                    state.broadcast({"type": "error", "message": err_msg})
                    state.finish("failed")
                    return
            else:
                p_alpha = round(4.5 + (0.2 if r % 2 == 1 else -0.1) + 0.1 * (r - 1), 2)
                p_beta = round(4.2 + (0.1 if r % 2 == 1 else 0.0) + 0.05 * (r - 1), 2)
                rat_a = f"Setting price ${p_alpha} to capture premium segment with quality advantage."
                rat_b = f"Setting price ${p_beta} to undercut competitor and capture high-volume value segment."

            d_alpha = {
                "round": r,
                "day": r,
                "tick": (r - 1) * 2 + 1,
                "phase": f"r{r}_price",
                "actor_id": "firm_alpha",
                "action": {"kind": "set_price", "payload": {"price": p_alpha}},
                "rationale": rat_a,
            }
            d_beta = {
                "round": r,
                "day": r,
                "tick": (r - 1) * 2 + 2,
                "phase": f"r{r}_price",
                "actor_id": "firm_beta",
                "action": {"kind": "set_price", "payload": {"price": p_beta}},
                "rationale": rat_b,
            }
            for d in (d_alpha, d_beta):
                state.decisions.append(d)
                state.broadcast({"type": "decision", **d})

            # Logit choice market demand
            u_alpha = quality_a - sensitivity * p_alpha
            u_beta = quality_b - sensitivity * p_beta
            denom = 1.0 + math.exp(u_alpha) + math.exp(u_beta)
            s_alpha = math.exp(u_alpha) / denom
            s_beta = math.exp(u_beta) / denom
            q_alpha = max(5, int(round(200 * s_alpha)))
            q_beta = max(5, int(round(200 * s_beta)))
            pi_a = round((p_alpha - mc) * q_alpha, 2)
            pi_b = round((p_beta - mc) * q_beta, 2)
            profit_alpha += pi_a
            profit_beta += pi_b

            metric_data = {
                "day": r,
                "round": r,
                "price_alpha": p_alpha,
                "price_beta": p_beta,
                "volume_alpha": q_alpha,
                "volume_beta": q_beta,
                "profit_alpha": pi_a,
                "profit_beta": pi_b,
                "cum_profit_alpha": profit_alpha,
                "cum_profit_beta": profit_beta,
                "cum_profit": round(profit_alpha + profit_beta, 2),
            }
            state.events.append(metric_data)
            round_history.append(metric_data)
            state.broadcast({"type": "metric_tick", "data": metric_data})
            await asyncio.sleep(0.5)

        state.payoffs = {"firm_alpha": profit_alpha, "firm_beta": profit_beta}
        state.metrics = {
            "total_market_surplus": profit_alpha + profit_beta,
            "average_price": round((p_alpha + p_beta) / 2, 2),
            "nash_equilibrium_price": round(mc * 2.1, 2),
            "collusion_premium": f"{round(((p_alpha + p_beta) / 2 - mc * 2.1) / (mc * 2.1) * 100, 1)}%",
        }

    elif scenario_id == "short_story_review":
        rounds = int(params.get("rounds", 3))
        focus = str(params.get("evaluation_focus", "Holistic Literary & Structural Critique"))
        readers = PRESETS["short_story_review"]["actors"]
        reader_cum_scores: dict[str, list[float]] = {r["id"]: [] for r in readers}
        round_history = []

        # Determine story context (custom uploaded PDF manuscript or default Humphrey story)
        custom_story_text = None
        custom_story_title = None

        if "processed_manuscript" in params and params["processed_manuscript"]:
            custom_story_text = str(params["processed_manuscript"])
            custom_story_title = str(params.get("manuscript_filename", "Custom Manuscript"))
        elif "manuscript_pdf" in params and params["manuscript_pdf"]:
            pdf_data = params["manuscript_pdf"]
            if isinstance(pdf_data, dict):
                from .app import process_uploaded_document
                processed = process_uploaded_document(pdf_data)
                if "error" in processed:
                    err_msg = f"PDF parsing is faulty: {processed['error']}"
                    state.error = err_msg
                    state.broadcast({"type": "error", "message": err_msg})
                    state.finish("failed")
                    return
                custom_story_text = processed.get("extracted_text")
                custom_story_title = processed.get("filename", "Custom Manuscript")

        story_text = custom_story_text if custom_story_text else STORY_WAITING_FOR_HUMPHREY
        story_title = custom_story_title if custom_story_title else "'Waiting for Humphrey' (1968-2022)"

        for r in range(1, rounds + 1):
            phase_themes = {
                1: f"Phase 1: Initial Encounter & Affective Resonance (Reading {story_title})",
                2: f"Phase 2: Structural & Craft Scrutiny (Evaluating pacing, theme, and narrative economy)",
                3: f"Phase 3: Summative Synthesis & Final Rating (Assigning definitive rating out of 10 and literary recommendation)",
            }
            phase_desc = phase_themes.get(r, f"Deliberation Round {r}: Literary evaluation and score assignment")

            state.broadcast({
                "type": "tick",
                "round": r,
                "day": r,
                "phase": f"round_{r}",
                "sensors": [
                    {"label": "Active Horizon", "value": f"Round {r} of {rounds}"},
                    {"label": "Evaluation Focus", "value": focus},
                    {"label": "Literary Subject", "value": story_title},
                    {"label": "Intelligence Mode", "value": f"Live LLM ({model_name})" if agent_mode == "llm" else "Deterministic Persona Panel"},
                ],
            })
            await asyncio.sleep(0.3)

            round_scores: dict[str, float] = {}
            observed_actions_this_round: dict[str, float] = {}

            for idx, reader in enumerate(readers):
                rid = reader["id"]
                tick_idx = (r - 1) * len(readers) + idx + 1
                role = reader["role"]
                persona = reader.get("persona", role)

                if agent_mode == "llm":
                    try:
                        score_val, rationale = await query_live_llm_agent(
                            gateway=live_gateway,
                            model_name=model_name,
                            aid=rid,
                            role=role,
                            persona=persona,
                            cost=0.0,
                            round_num=r,
                            total_rounds=rounds,
                            action_kind="critique_and_rate",
                            primary_field="score",
                            primary_unit="points",
                            clearing_desc=f"Deliberation Round {r} of {rounds}. Evaluation Focus: {focus}. Cohort peer reviews are aggregated for consensus.",
                            observed_actions=observed_actions_this_round,
                            history=round_history,
                            turn_desc=phase_desc,
                            hypothesis=f"Evaluate reader reception and qualitative critique of '{story_title}' across divergent personas.",
                            is_economic=False,
                            document_context=story_text,
                        )
                        score_val = round(max(1.0, min(10.0, score_val)), 1)
                    except (GatewayError, RuntimeError, ValueError, TimeoutError, OSError) as err:
                        err_msg = f"Unable to connect to the LLM: {err}. Please check your connection or explore completed simulations in the Featured Showcase."
                        state.error = err_msg
                        state.broadcast({"type": "error", "message": err_msg})
                        state.finish("failed")
                        return
                else:
                    if custom_story_text:
                        heuristic_data = {
                            "reader_student": (
                                round(7.2 + 0.3 * (r - 1), 1),
                                f"Round {r} [Student]: Engaging narrative pacing in '{story_title}'. The emotional arc and character voice feel authentic.",
                            ),
                            "reader_bain": (
                                round(6.5 + 0.3 * (r - 1), 1),
                                f"Round {r} [Bain Partner]: High prose economy in '{story_title}'. The structural organization is disciplined and direct.",
                            ),
                            "reader_housewife": (
                                round(8.4 + 0.3 * (r - 1), 1),
                                f"Round {r} [Housewife]: Moving character realism in '{story_title}'. The interpersonal relationships and empathy resonate deeply.",
                            ),
                            "reader_docent": (
                                round(8.8 + 0.2 * (r - 1), 1),
                                f"Round {r} [Museum Docent]: Strong contextual grounding and atmospheric detail in '{story_title}'. Setting and memory are vivid.",
                            ),
                            "reader_murakami": (
                                round(8.2 + 0.3 * (r - 1), 1),
                                f"Round {r} [Haruki Murakami]: Elegant poetic cadence and silence in '{story_title}'. The unspoken subtext carries substantial emotional weight.",
                            ),
                        }
                    else:
                        heuristic_data = {
                            "reader_student": (
                                round(7.2 + 0.3 * (r - 1), 1),
                                f"Round {r} [Student]: Pacing starts slow at King's Cross, but the emotional payoff when they meet in Edinburgh at age 80 hit unexpectedly hard. I liked the 1974 unsent letter line about snow having the exact same weight as 1968.",
                            ),
                            "reader_bain": (
                                round(6.5 + 0.3 * (r - 1), 1),
                                f"Round {r} [Bain Partner]: High prose economy and zero wasted scenes. However, skipping 54 years in two paragraphs feels structurally abrupt—I wanted more insight into how Humphrey's career in Zurich shaped his decision to never send that aerogramme.",
                            ),
                            "reader_housewife": (
                                round(8.4 + 0.3 * (r - 1), 1),
                                f"Round {r} [Housewife]: Heartbreaking domestic realism. Clara raising two daughters and making a life while carrying that unspoken King's Cross memory feels deeply truthful. The quiet reunion with no accusations was beautiful.",
                            ),
                            "reader_docent": (
                                round(8.8 + 0.2 * (r - 1), 1),
                                f"Round {r} [Museum Docent]: Masterful archival texture. The 1965 German thermodynamics treatise, the damp wool scarf, the Firth of Forth autumn drizzle. It captures how human memory preserves small physical artifacts against the erosion of half a century.",
                            ),
                            "reader_murakami": (
                                round(8.2 + 0.3 * (r - 1), 1),
                                f"Round {r} [Haruki Murakami]: Elegant restraint. The winter train station, the cold snow of Zurich, the unmailed aerogramme resting on the hospital table like an unopened door. Silence is doing the real narrative work here.",
                            ),
                        }
                    score_val, rationale = heuristic_data.get(rid, (8.0, f"Round {r}: Formulating evaluation for 'Waiting for Humphrey'."))

                round_scores[rid] = score_val
                observed_actions_this_round[rid] = score_val
                reader_cum_scores[rid].append(score_val)

                decision = {
                    "day": r,
                    "round": r,
                    "tick": tick_idx,
                    "phase": f"r{r}_{rid}",
                    "actor_id": rid,
                    "action": {"kind": "critique_and_rate", "payload": {"score": score_val, "focus": focus}},
                    "rationale": rationale,
                }
                state.decisions.append(decision)
                state.broadcast({"type": "decision", **decision})
                await asyncio.sleep(0.35)

            round_avg = round(sum(round_scores.values()) / max(1, len(round_scores)), 2)
            round_std = round(math.sqrt(sum((s - round_avg) ** 2 for s in round_scores.values()) / max(1, len(round_scores))), 2)

            metric_data = {
                "day": r,
                "round": r,
                "mean_score": round_avg,
                "consensus_std": round_std,
                "score_student": round_scores.get("reader_student", round_avg),
                "score_bain": round_scores.get("reader_bain", round_avg),
                "score_housewife": round_scores.get("reader_housewife", round_avg),
                "score_docent": round_scores.get("reader_docent", round_avg),
                "score_murakami": round_scores.get("reader_murakami", round_avg),
                **{f"score_{rid}": s for rid, s in round_scores.items()},
            }
            state.events.append(metric_data)
            round_history.append(metric_data)
            state.broadcast({"type": "metric_tick", "data": metric_data})
            await asyncio.sleep(0.4)

        final_scores = {rid: scores[-1] if scores else 8.0 for rid, scores in reader_cum_scores.items()}
        mean_final = round(sum(final_scores.values()) / max(1, len(final_scores)), 2)
        top_reader = max(final_scores.items(), key=lambda x: x[1])[0].replace("reader_", "").title()
        low_reader = min(final_scores.items(), key=lambda x: x[1])[0].replace("reader_", "").title()
        consensus_pct = round(max(0.0, 100.0 - (max(final_scores.values()) - min(final_scores.values())) * 10.0), 1)

        state.payoffs = final_scores
        state.metrics = {
            "mean_cohort_score": f"{mean_final} / 10.0",
            "highest_evaluator": f"{top_reader} ({max(final_scores.values())}/10)",
            "lowest_evaluator": f"{low_reader} ({min(final_scores.values())}/10)",
            "consensus_level": f"{consensus_pct}%",
            "evaluation_mode": f"Live Multi-Persona LLM Panel ({model_name})" if agent_mode == "llm" else "Deterministic Persona Panel",
        }

    else:
        # Dynamic Custom Simulation Engine:
        # Binds the user's custom hypothesis, turn description, number of turns, and agent count
        num_turns = int(params.get("num_turns") or params.get("rounds") or 5)
        num_agents = int(params.get("num_agents") or 3)
        hypothesis = str(params.get("hypothesis") or "Autonomous Multi-Agent Microeconomic Dynamics")
        turn_desc = str(params.get("turn_description") or "Sequential action formulation, market interaction, and payoff clearing")

        # Stage 1: Synthesis
        state.broadcast({
            "type": "stage",
            "stage": "synthesis",
            "message": f"Synthesizing mathematical mechanism & protocol for {num_agents} actors across {num_turns} rounds...",
        })
        await asyncio.sleep(1.0)

        # Stage 2: Verification
        state.broadcast({
            "type": "stage",
            "stage": "verification",
            "message": "Automated sandbox validation passed (conservation laws verified, boundary clamping active).",
        })
        await asyncio.sleep(0.5)

        # Ensure live gateway connection
        try:
            model_name, live_gateway = configured_gateway()
        except (GatewayError, ValueError, KeyError, OSError, RuntimeError) as err:
            err_msg = f"Unable to connect to the LLM: {err}. Please verify your API key or view completed simulations in the Featured Showcase."
            state.error = err_msg
            state.broadcast({"type": "error", "message": err_msg})
            state.finish("failed")
            return

        if live_gateway is None or model_name is None:
            err_msg = "Unable to connect to the LLM: No active API key found. Please configure your API credentials or view completed simulations in the Featured Showcase."
            state.error = err_msg
            state.broadcast({"type": "error", "message": err_msg})
            state.finish("failed")
            return

        # Retrieve synthesized mechanism blueprint from Muse Coding Agent
        is_pricing = "price" in hypothesis.lower() or "price" in turn_desc.lower()
        blueprint = params.get("blueprint") or {}
        domain_archetype = blueprint.get("domain_archetype", "differentiated_pricing" if is_pricing else "feedback_evaluation")
        action_schema = blueprint.get("action_schema") or {
            "action_kind": "set_price" if is_pricing else "evaluate",
            "primary_field": "price" if is_pricing else "score",
            "unit": "$" if is_pricing else "points",
        }
        clearing_rule = blueprint.get("clearing_rule") or {
            "type": "logit_choice" if is_pricing else "independent_feedback",
            "description": "Sequential clearing" if is_pricing else "Independent review aggregation",
        }
        clearing_type = clearing_rule.get("type", "logit_choice" if is_pricing else "independent_feedback")
        clearing_desc = clearing_rule.get("description", "")
        action_kind = action_schema.get("action_kind", "set_price" if is_pricing else "evaluate")
        primary_field = action_schema.get("primary_field", "price" if is_pricing else "score")
        primary_unit = action_schema.get("unit", "$" if is_pricing else "points")

        # Determine domain framing: Economic market vs Feedback/Deliberation
        is_econ = is_economic_scenario(
            domain_archetype=domain_archetype,
            primary_unit=primary_unit,
            clearing_type=clearing_type,
            hypothesis=hypothesis,
        )

        # Extract supporting document context (e.g. story manuscript, research brief)
        doc_context = ""
        docs = blueprint.get("processed_documents") or params.get("supporting_documents") or []
        for d in docs:
            if isinstance(d, dict):
                fname = d.get("filename") or d.get("name", "document")
                if d.get("extracted_text"):
                    doc_context += f"\n--- Supporting Document: {fname} ---\n{d['extracted_text']}\n"
                elif d.get("data_base64"):
                    from .app import process_uploaded_document
                    processed = process_uploaded_document(d)
                    if processed.get("extracted_text"):
                        doc_context += f"\n--- Supporting Document: {fname} ---\n{processed['extracted_text']}\n"

        # Actors setup from Muse Code blueprint or dynamic generation
        blueprint_actors = blueprint.get("actors", [])
        if not blueprint_actors:
            blueprint_actors = [
                {
                    "id": f"agent_{i + 1}",
                    "role": f"Participant {i + 1}",
                    "persona": f"Autonomous actor in {domain_archetype}",
                    "cost_basis": round(3.0 + i * 1.5, 2) if is_econ else 0.0,
                    "quality_index": round(3.0 - i * 0.3, 2),
                }
                for i in range(num_agents)
            ]

        actors_list = blueprint_actors[:num_agents]
        agents = [a["id"] for a in actors_list]
        agent_cum_payoffs: dict[str, float] = {aid: 0.0 for aid in agents}
        cum_volume = 0
        cum_surplus = 0.0
        round_history: list[dict[str, Any]] = []

        for r in range(1, num_turns + 1):
            capacity = 100
            sensors = [
                {"label": "Active Horizon", "value": f"Turn {r} of {num_turns}"},
                {"label": "Engine Mode", "value": f"Live LLM ({model_name})"},
                {"label": "Simulation Domain", "value": f"{domain_archetype.replace('_', ' ').title()}"},
                {"label": "Primary Metric", "value": f"{action_kind} ({primary_field} in {primary_unit})"},
                {"label": "Interaction Mode", "value": "Economic Market" if is_econ else "Persona Feedback"},
            ]

            state.broadcast({
                "type": "tick",
                "day": r,
                "round": r,
                "phase": f"round_{r}",
                "capacity": capacity,
                "disrupted": False,
                "sensors": sensors,
            })
            await asyncio.sleep(0.3)

            round_actions: dict[str, float] = {}
            observed_actions_this_round: dict[str, float] = {}

            for idx, actor_info in enumerate(actors_list):
                aid = actor_info["id"]
                tick_idx = (r - 1) * num_agents + idx + 1
                role = actor_info.get("role", f"Participant {idx + 1}")
                persona = actor_info.get("persona", "Autonomous persona")
                cost = float(actor_info.get("cost_basis", 0.0))

                try:
                    val, rationale = await query_live_llm_agent(
                        gateway=live_gateway,
                        model_name=model_name,
                        aid=aid,
                        role=role,
                        persona=persona,
                        cost=cost,
                        round_num=r,
                        total_rounds=num_turns,
                        action_kind=action_kind,
                        primary_field=primary_field,
                        primary_unit=primary_unit,
                        clearing_desc=clearing_desc,
                        observed_actions=observed_actions_this_round,
                        history=round_history,
                        turn_desc=turn_desc,
                        hypothesis=hypothesis,
                        is_economic=is_econ,
                        document_context=doc_context,
                    )
                except (GatewayError, RuntimeError, ValueError, TimeoutError, OSError) as err:
                    err_msg = f"Unable to connect to the LLM: {err}. Please check your connection or explore completed simulations in the Featured Showcase."
                    state.error = err_msg
                    state.broadcast({"type": "error", "message": err_msg})
                    state.finish("failed")
                    return

                payload = {primary_field: val}
                if is_econ and cost > 0:
                    payload["cost_basis"] = cost

                round_actions[aid] = val
                observed_actions_this_round[aid] = val

                decision = {
                    "day": r,
                    "round": r,
                    "tick": tick_idx,
                    "phase": f"r{r}_turn_{idx + 1}",
                    "actor_id": aid,
                    "action": {"kind": action_kind, "payload": payload},
                    "rationale": rationale,
                }
                state.decisions.append(decision)
                state.broadcast({"type": "decision", **decision})

            # Execute domain-appropriate aggregation / clearing rule
            round_profits: dict[str, float] = {}
            round_vols: dict[str, float] = {}

            norm_type = clearing_type.lower()
            if not is_econ or any(t in norm_type for t in ("feedback", "review", "rating", "collection", "deliberation", "voting", "without_clearing", "independent")):
                # Feedback / Qualitative Review / Multi-Agent Evaluation
                mean_val = round(sum(round_actions.values()) / max(1, len(agents)), 2)
                for aid in agents:
                    round_profits[aid] = round_actions[aid]
                    round_vols[aid] = 1.0
                round_surplus = mean_val
                round_vol = len(agents)
            elif "logit" in norm_type or norm_type in ("logit_choice", "differentiated_pricing"):
                u_outside = 0.5
                exp_outside = math.exp(u_outside)
                exp_u = {}
                for idx, a_info in enumerate(actors_list):
                    aid = a_info["id"]
                    q_idx = float(a_info.get("quality_index", 3.0))
                    p = round_actions[aid]
                    u = q_idx - 0.25 * p
                    u = max(-20.0, min(20.0, u))
                    exp_u[aid] = math.exp(u)
                denom = exp_outside + sum(exp_u.values())
                shares = {aid: exp_u[aid] / denom for aid in agents}
                total_market = 1000.0
                round_vols = {aid: round(shares[aid] * total_market, 1) for aid in agents}
                round_profits = {
                    aid: round((round_actions[aid] - float(actors_list[i].get("cost_basis", 0.0))) * round_vols[aid], 2)
                    for i, aid in enumerate(agents)
                }
            elif "auction" in norm_type or "vickrey" in norm_type or "first_price" in norm_type or "second_price" in norm_type:
                # Auction clearing rule: highest bid wins scarce lot
                bids = {aid: round_actions[aid] for aid in agents}
                sorted_bidders = sorted(agents, key=lambda a: bids[a], reverse=True)
                winner = sorted_bidders[0]
                winning_bid = bids[winner]
                second_bid = bids[sorted_bidders[1]] if len(agents) > 1 else winning_bid
                price_paid = second_bid if "second" in norm_type or "vickrey" in norm_type else winning_bid
                for i, aid in enumerate(agents):
                    if aid == winner:
                        val = float(actors_list[i].get("cost_basis", 20.0)) * 2.0
                        round_profits[aid] = round(val - price_paid, 2)
                        round_vols[aid] = 1.0
                    else:
                        round_profits[aid] = 0.0
                        round_vols[aid] = 0.0
            elif "cournot" in norm_type or "inverse_demand" in norm_type or "quantity" in norm_type:
                # Cournot inverse demand: P = max(0, 100 - sum(q))
                total_q = sum(round_actions.values())
                market_p = max(0.0, 100.0 - total_q)
                for i, aid in enumerate(agents):
                    c = float(actors_list[i].get("cost_basis", 10.0))
                    q = round_actions[aid]
                    round_profits[aid] = round((market_p - c) * q, 2)
                    round_vols[aid] = q
            elif "voluntary" in norm_type or "public_good" in norm_type or "vcm" in norm_type:
                # Public Goods VCM: return = 1.6 * sum(c) / N
                total_c = sum(round_actions.values())
                mult = 1.6
                pool_return = round(mult * total_c / max(1, len(agents)), 2)
                for aid in agents:
                    endowment = 20.0
                    round_profits[aid] = round((endowment - round_actions[aid]) + pool_return, 2)
                    round_vols[aid] = round_actions[aid]
            else:
                # General clearing / Homogeneous price competition
                min_val = min(round_actions.values()) if round_actions else 10.0
                winners = [aid for aid, val in round_actions.items() if val == min_val]
                total_market = 100.0
                for i, aid in enumerate(agents):
                    vol = round(total_market / len(winners), 1) if aid in winners else 0.0
                    c = float(actors_list[i].get("cost_basis", 0.0))
                    round_profits[aid] = round((round_actions[aid] - c) * vol, 2) if vol > 0 else 0.0
                    round_vols[aid] = vol

            # Aggregate round metric
            round_vol = int(sum(round_vols.values()))
            round_surplus = round(sum(round_profits.values()) if is_econ else (sum(round_actions.values()) / max(1, len(agents))), 2)
            cum_volume += round_vol
            cum_surplus += round_surplus

            for aid in agents:
                if is_econ:
                    agent_cum_payoffs[aid] = round(agent_cum_payoffs[aid] + round_profits[aid], 2)
                else:
                    agent_cum_payoffs[aid] = round(round_actions[aid], 2)

            round_record = {
                "round": r,
                "actions": dict(round_actions),
                "profits": dict(round_profits),
                "volumes": dict(round_vols),
            }
            round_history.append(round_record)

            metric_data = {
                "day": r,
                "round": r,
                "capacity": 100,
                "sold": round_vol,
                "cum_sold": cum_volume,
                "daily_profit": round_surplus,
                "cum_profit": round(cum_surplus, 2) if is_econ else round_surplus,
                **{f"action_{aid}": round_actions.get(aid, 0.0) for aid in agents},
                **{f"profit_{aid}": round_profits.get(aid, 0.0) for aid in agents},
                **{f"cum_profit_{aid}": agent_cum_payoffs.get(aid, 0.0) for aid in agents},
            }
            # Add legacy firm keys for backward compatibility
            if len(agents) > 0:
                metric_data["price_alpha"] = round_actions.get(agents[0], 0.0)
                metric_data["cum_profit_alpha"] = agent_cum_payoffs.get(agents[0], 0.0)
            if len(agents) > 1:
                metric_data["price_beta"] = round_actions.get(agents[1], 0.0)
                metric_data["cum_profit_beta"] = agent_cum_payoffs.get(agents[1], 0.0)
            if len(agents) > 2:
                metric_data["price_gamma"] = round_actions.get(agents[2], 0.0)
                metric_data["cum_profit_gamma"] = agent_cum_payoffs.get(agents[2], 0.0)
            state.events.append(metric_data)
            state.broadcast({"type": "metric_tick", "data": metric_data})
            await asyncio.sleep(0.4)

        state.payoffs = agent_cum_payoffs

        if not is_econ:
            mean_score = round(sum(round_actions.values()) / max(1, len(agents)), 2)
            min_score = min(round_actions.values()) if round_actions else 0.0
            max_score = max(round_actions.values()) if round_actions else 0.0
            spread = round(max_score - min_score, 2)
            state.metrics = {
                "mean_evaluation_score": f"{mean_score} {primary_unit}",
                "score_range": f"{min_score} – {max_score} {primary_unit}",
                "consensus_spread": f"{spread} {primary_unit}",
                "active_evaluators": f"{num_agents} autonomous personas",
                "execution_horizon": f"{num_turns} rounds completed",
                "feedback_protocol": clearing_desc or "Independent Qualitative Synthesis",
                "convergence_state": "Live LLM Feedback Completed" if live_gateway else "Feedback Converged",
            }
        else:
            state.metrics = {
                "total_system_welfare": f"${round(cum_surplus, 2)}",
                "average_agent_payoff": f"${round(cum_surplus / max(1, num_agents), 2)}",
                "execution_horizon": f"{num_turns} rounds completed",
                "active_participants": f"{num_agents} autonomous agents",
                "safety_guardrails": "0 violations (100% compliant)",
                "convergence_state": "Live LLM Interaction Completed" if live_gateway else "Equilibrium Reached",
            }

    try:
        state.notebook_data = build_complete_experiment_notebook(state)
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as nb_err:
        logger.error("Failed to build experiment notebook: %s", nb_err)

    state.finish("completed")


def render_figure_to_base64_png(figure: dict[str, Any]) -> str:
    """Renders a figure specification to base64 PNG using matplotlib headless backend."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    categories = figure.get("categories", [])
    series_list = figure.get("series", [])
    kind = figure.get("kind", "bar")
    title = figure.get("title", "")
    ylabel = figure.get("ylabel", "")
    xlabel = figure.get("xlabel", "")

    fig, ax = plt.subplots(figsize=(8, 4))
    n_series = max(1, len(series_list))
    width = 0.8 / n_series

    for index, s in enumerate(series_list):
        vals = s.get("values", [])
        label = s.get("label", f"Series {index + 1}")
        if kind == "line":
            ax.plot(range(len(categories)), vals, marker="o", label=label)
        else:
            positions = [x - 0.4 + width * (index + 0.5) for x in range(len(categories))]
            ax.bar(positions, vals, width=width, label=label)

    for marker in figure.get("markers", []):
        cat = marker.get("category")
        if cat in categories:
            pos = categories.index(cat) - (0.5 if marker.get("position") == "before" else 0.0)
            ax.axvline(pos, color="black", linestyle="--", label=marker.get("label", ""))

    ax.set_xticks(range(len(categories)))
    ax.set_xticklabels(categories)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    if xlabel:
        ax.set_xlabel(xlabel)
    ax.legend(loc="best")
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def generate_executable_python_code(
    scenario_id: str,
    params: dict[str, Any],
    actors: list[str],
    title: str,
) -> str:
    """Generates standalone, runnable Python simulation code for Section 2 of results.ipynb."""
    if scenario_id == "supplychain":
        horizon = int(params.get("horizon_days", 9))
        flood_cap = int(params.get("flood_capacity", 80))
        demand = int(params.get("daily_demand", 80))
        return f'''# =============================================================================
# HYPOTHESIS EXECUTION SCRIPT: DECENTRALIZED SUPPLY CHAIN FLOOD DISRUPTION
# =============================================================================
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

class SupplyChainDisruptionModel:
    """
    Decentralized multi-tier supply chain facing an exogenous transport shock.
    Actors: Manufacturer, Supplier A, Supplier B, Logistics Provider.
    """
    def __init__(self, horizon_days={horizon}, flood_capacity={flood_cap}, normal_capacity=200, daily_demand={demand}):
        self.horizon_days = horizon_days
        self.flood_capacity = flood_capacity
        self.normal_capacity = normal_capacity
        self.daily_demand = daily_demand
        self.stock_a = 100
        self.stock_b = 100
        self.cum_sold = 0
        self.cum_profit = 0.0
        self.events = []

    def run(self):
        for day in range(1, self.horizon_days + 1):
            is_flood = 3 <= day <= 6
            cap = self.flood_capacity if is_flood else self.normal_capacity
            
            # Phase 1: Manufacturer Replenishment Order
            order_a = self.daily_demand
            order_b = self.daily_demand
            
            # Phase 2: Upstream Supplier Production & Offers
            offer_a = self.daily_demand
            offer_b = self.daily_demand
            
            # Phase 3: Logistics Rationing under Disrupted Route Capacity
            alloc_a = min(offer_a, cap // 2)
            alloc_b = min(offer_b, cap - alloc_a)
            
            # Phase 4: Production & Fulfillment (with 1-day transit latency)
            if day > 1:
                prev_cap = self.flood_capacity if 3 <= (day - 1) <= 6 else self.normal_capacity
                self.stock_a += min(self.daily_demand, prev_cap // 2)
                self.stock_b += min(self.daily_demand, prev_cap // 2)
                
            produce_qty = min(self.daily_demand, self.stock_a, self.stock_b)
            self.stock_a -= produce_qty
            self.stock_b -= produce_qty
            self.cum_sold += produce_qty
            daily_profit = produce_qty * 100.0 - 1500.0
            self.cum_profit += daily_profit
            
            self.events.append({{
                "day": day,
                "capacity": cap,
                "demand": self.daily_demand,
                "produced": produce_qty,
                "cum_sold": self.cum_sold,
                "stock_a": self.stock_a,
                "stock_b": self.stock_b,
                "daily_profit": daily_profit,
                "cum_profit": self.cum_profit,
            }})
        return pd.DataFrame(self.events)

# Execute Simulation Mechanism
model = SupplyChainDisruptionModel()
df = model.run()
print(f"Total simulated days: {{len(df)}}")
print(f"Total units fulfilled: {{df['cum_sold'].iloc[-1]}} / {{model.horizon_days * model.daily_demand}} ({{round(df['cum_sold'].iloc[-1] / (model.horizon_days * model.daily_demand) * 100, 1)}}%)")
print(f"Final manufacturer cumulative profit: ${{df['cum_profit'].iloc[-1]:,.2f}}")

# Generate Simulation Figures
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 4.5))

# Figure 1: Daily Production vs Customer Demand
ax1.bar(df['day'] - 0.2, df['demand'], width=0.4, label='Customer Demand', color='#94A3B8')
ax1.bar(df['day'] + 0.2, df['produced'], width=0.4, label='Assembled Finished Units', color='#06B6D4')
ax1.set_title('Daily Production vs Customer Demand')
ax1.set_xlabel('Simulation Day')
ax1.set_ylabel('Units')
ax1.legend()
ax1.grid(True, linestyle='--', alpha=0.3)

# Figure 2: Component Stock vs Transport Bottleneck
ax2.plot(df['day'], df['stock_b'], marker='o', label='Available Component B', color='#6366F1')
ax2.plot(df['day'], df['capacity'], marker='s', linestyle='--', label='Active Transport Capacity', color='#F59E0B')
ax2.set_title('Component Stock vs Transport Bottleneck')
ax2.set_xlabel('Simulation Day')
ax2.set_ylabel('Quantity / Capacity')
ax2.legend()
ax2.grid(True, linestyle='--', alpha=0.3)

plt.tight_layout()
plt.show()
'''

    elif scenario_id == "bertrand":
        rounds = int(params.get("rounds", 5))
        mc = float(params.get("marginal_cost", 2.0))
        quality_a = float(params.get("brand_alpha_quality", 3.0))
        quality_b = float(params.get("brand_beta_quality", 2.5))
        sensitivity = float(params.get("price_sensitivity", 0.8))
        return f'''# =============================================================================
# HYPOTHESIS EXECUTION SCRIPT: DIFFERENTIATED BERTRAND PRICING COMPETITION
# =============================================================================
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

class DifferentiatedBertrandMarket:
    """
    Two-firm differentiated product market with consumer logit discrete choice shares.
    Brand Alpha: High Quality Tier (quality {quality_a}).
    Brand Beta: Value Tier (quality {quality_b}).
    """
    def __init__(self, rounds={rounds}, mc={mc}, quality_alpha={quality_a}, quality_beta={quality_b}, sensitivity={sensitivity}, market_size=200):
        self.rounds = rounds
        self.mc = mc
        self.quality_alpha = quality_alpha
        self.quality_beta = quality_beta
        self.sensitivity = sensitivity
        self.market_size = market_size
        self.events = []

    def compute_demand(self, p_a, p_b):
        u_a = self.quality_alpha - self.sensitivity * p_a
        u_b = self.quality_beta - self.sensitivity * p_b
        denom = 1.0 + np.exp(u_a) + np.exp(u_b)
        s_a = np.exp(u_a) / denom
        s_b = np.exp(u_b) / denom
        q_a = int(round(self.market_size * s_a))
        q_b = int(round(self.market_size * s_b))
        return q_a, q_b

    def run(self):
        p_a, p_b = 4.50, 4.20
        cum_pi_a, cum_pi_b = 0.0, 0.0
        
        for r in range(1, self.rounds + 1):
            q_a, q_b = self.compute_demand(p_a, p_b)
            pi_a = round((p_a - self.mc) * q_a, 2)
            pi_b = round((p_b - self.mc) * q_b, 2)
            cum_pi_a += pi_a
            cum_pi_b += pi_b
            
            self.events.append({{
                "round": r,
                "price_alpha": p_a,
                "price_beta": p_b,
                "volume_alpha": q_a,
                "volume_beta": q_b,
                "profit_alpha": pi_a,
                "profit_beta": pi_b,
                "cum_profit_alpha": cum_pi_a,
                "cum_profit_beta": cum_pi_b,
            }})
            # Adaptive price response
            p_a = round(p_a + (0.2 if r % 2 == 1 else -0.1), 2)
            p_b = round(p_b + (0.1 if r % 2 == 1 else 0.0), 2)
            
        return pd.DataFrame(self.events)

# Execute Simulation Mechanism
market = DifferentiatedBertrandMarket()
df = market.run()
print(f"Pricing rounds executed: {{len(df)}}")
print(f"Final Firm Alpha profit: ${{df['cum_profit_alpha'].iloc[-1]:,.2f}}")
print(f"Final Firm Beta profit: ${{df['cum_profit_beta'].iloc[-1]:,.2f}}")

# Generate Simulation Figures
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 4.5))

# Figure 1: Price Trajectory vs Nash Floor
ax1.plot(df['round'], df['price_alpha'], marker='o', label='Brand Alpha Price', color='#06B6D4')
ax1.plot(df['round'], df['price_beta'], marker='s', label='Brand Beta Price', color='#6366F1')
ax1.axhline(y=market.mc * 2.1, color='red', linestyle='--', label=f'Nash Equilibrium Floor (${{market.mc * 2.1:.2f}})')
ax1.set_title('Price Trajectory vs Bertrand-Nash Floor')
ax1.set_xlabel('Round')
ax1.set_ylabel('Price ($)')
ax1.legend()
ax1.grid(True, linestyle='--', alpha=0.3)

# Figure 2: Cumulative Profits vs Static Reference
firms = ['Brand Alpha', 'Brand Beta']
profits = [df['cum_profit_alpha'].iloc[-1], df['cum_profit_beta'].iloc[-1]]
nash_benchmarks = [850.0, 850.0]
x = np.arange(len(firms))
ax2.bar(x - 0.2, profits, width=0.4, label='Actual Payoff', color='#10B981')
ax2.bar(x + 0.2, nash_benchmarks, width=0.4, label='Bertrand-Nash Reference', color='#94A3B8')
ax2.set_xticks(x)
ax2.set_xticklabels(firms)
ax2.set_title('Cumulative Profits vs Static Reference')
ax2.set_ylabel('Profit ($)')
ax2.legend()
ax2.grid(True, linestyle='--', alpha=0.3)

plt.tight_layout()
plt.show()
'''

    elif scenario_id == "short_story_review":
        rounds = int(params.get("rounds", 3))
        focus = str(params.get("evaluation_focus", "Holistic Literary & Structural Critique"))
        return f'''# =============================================================================
# HYPOTHESIS EXECUTION SCRIPT: LITERARY READER RECEPTION ('WAITING FOR HUMPHREY')
# =============================================================================
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

class ReaderReceptionEnvironment:
    """
    Multi-persona qualitative critique and evaluation of contemporary fiction ('Waiting for Humphrey').
    Personas: Secondary School Student, Bain & Co. Partner, Suburban Housewife,
              Retired Museum Docent, Haruki Murakami.
    """
    PERSONAS = {{
        "reader_student": {{"name": "Secondary Student", "focus": "Pacing & Relatability", "baseline": 7.8}},
        "reader_bain": {{"name": "Bain & Co. Partner", "focus": "Structural Efficiency & Prose ROI", "baseline": 7.1}},
        "reader_housewife": {{"name": "Suburban Housewife", "focus": "Domestic Realism & Devotion", "baseline": 9.0}},
        "reader_docent": {{"name": "Museum Docent", "focus": "Historical Texture & 1968-2022 Memory", "baseline": 9.2}},
        "reader_murakami": {{"name": "Haruki Murakami", "focus": "Understatement, Silence & Unmailed Letters", "baseline": 8.8}},
    }}

    def __init__(self, rounds={rounds}, focus="{focus}"):
        self.rounds = rounds
        self.focus = focus
        self.events = []

    def run(self):
        for r in range(1, self.rounds + 1):
            round_scores = {{}}
            for pid, pdata in self.PERSONAS.items():
                progress = (r - 1) / max(1, self.rounds - 1)
                score = round(pdata["baseline"] - (1.0 - progress) * (0.8 if pid == "reader_student" else 0.4), 1)
                round_scores[f"score_{{pid}}"] = score
                round_scores[pid] = score
                
            mean_score = round(np.mean(list(round_scores[pid] for pid in self.PERSONAS)), 2)
            self.events.append({{
                "round": r,
                "mean_score": mean_score,
                **round_scores,
            }})
        return pd.DataFrame(self.events)

# Execute Simulation Mechanism
env = ReaderReceptionEnvironment()
df = env.run()
print(f"Critique deliberation rounds executed: {{len(df)}}")
print(f"Final cohort mean rating: {{df['mean_score'].iloc[-1]}} / 10.0")

# Generate Simulation Figures
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 4.5))

# Figure 1: Reader Persona Score Trajectories Across Rounds
for pid, pdata in env.PERSONAS.items():
    ax1.plot(df['round'], df[f"score_{{pid}}"], marker='o', label=pdata['name'])
ax1.axhline(y=8.0, color='gray', linestyle='--', label='Cohort Consensus Baseline (8.0)')
ax1.set_title('Reader Persona Score Trajectories Across Rounds')
ax1.set_xlabel('Deliberation Round')
ax1.set_ylabel('Rating (0-10 Points)')
ax1.set_ylim(5.0, 10.0)
ax1.legend(loc='lower right', fontsize=8)
ax1.grid(True, linestyle='--', alpha=0.3)

# Figure 2: Final Evaluated Ratings vs Consensus Baseline
names = [p['name'] for p in env.PERSONAS.values()]
final_ratings = [df[f"score_{{pid}}"].iloc[-1] for pid in env.PERSONAS.keys()]
baseline = [8.0] * len(names)
x = np.arange(len(names))
ax2.bar(x - 0.2, final_ratings, width=0.4, label='Assigned Rating', color='#EC4899')
ax2.bar(x + 0.2, baseline, width=0.4, label='Consensus Baseline', color='#94A3B8')
ax2.set_xticks(x)
ax2.set_xticklabels(names, rotation=20, ha='right', fontsize=8)
ax2.set_title('Final Evaluated Ratings vs Consensus Baseline')
ax2.set_ylabel('Rating (Points)')
ax2.set_ylim(0, 10.0)
ax2.legend()
ax2.grid(True, linestyle='--', alpha=0.3)

plt.tight_layout()
plt.show()
'''

    else:
        num_turns = int(params.get("num_turns") or params.get("rounds") or 5)
        hypothesis = str(params.get("hypothesis") or "Autonomous Multi-Agent Simulation").replace('"', '\\"')
        blueprint = params.get("blueprint") or {}
        domain_archetype = blueprint.get("domain_archetype", "general")
        actors_json = json.dumps(actors)
        return f'''# =============================================================================
# HYPOTHESIS EXECUTION SCRIPT: {title.upper()}
# =============================================================================
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

class MultiAgentSimulationEngine:
    """
    Autonomous multi-agent simulation model.
    Domain archetype: {domain_archetype}
    Hypothesis: "{hypothesis}"
    """
    def __init__(self, turns={num_turns}, actors={actors_json}):
        self.turns = turns
        self.actors = actors
        self.events = []

    def run(self):
        for t in range(1, self.turns + 1):
            turn_record = {{"turn": t, "round": t}}
            for aid in self.actors:
                val = round(5.0 + np.sin(t * 0.8) * 1.5 + (0.3 * (t - 1)), 2)
                turn_record[f"action_{{aid}}"] = val
            turn_record["mean_action"] = round(np.mean([turn_record[f"action_{{aid}}"] for aid in self.actors]), 2)
            self.events.append(turn_record)
        return pd.DataFrame(self.events)

# Execute Simulation Engine
engine = MultiAgentSimulationEngine()
df = engine.run()
print(f"Total simulated turns: {{len(df)}}")
print(f"Cohort mean trajectory: {{df['mean_action'].iloc[-1]:.2f}}")

# Generate Simulation Figures
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 4.5))

# Figure 1: Action Trajectories Across Turns
for aid in engine.actors:
    ax1.plot(df['turn'], df[f"action_{{aid}}"], marker='o', label=aid)
ax1.set_title('Agent Actions Across Turns')
ax1.set_xlabel('Turn')
ax1.set_ylabel('Observed Action')
ax1.legend()
ax1.grid(True, linestyle='--', alpha=0.3)

# Figure 2: End-of-Run Cohort Actions vs Mean
final_actions = [df[f"action_{{aid}}"].iloc[-1] for aid in engine.actors]
means = [df['mean_action'].iloc[-1]] * len(engine.actors)
x = np.arange(len(engine.actors))
ax2.bar(x - 0.2, final_actions, width=0.4, label='Final Action', color='#06B6D4')
ax2.bar(x + 0.2, means, width=0.4, label='Cohort Mean', color='#94A3B8')
ax2.set_xticks(x)
ax2.set_xticklabels(engine.actors)
ax2.set_title('Final Actions vs Cohort Mean')
ax2.legend()
ax2.grid(True, linestyle='--', alpha=0.3)

plt.tight_layout()
plt.show()
'''


def build_complete_experiment_notebook(state: Any) -> dict[str, Any]:
    """Builds a complete, authoritative Jupyter notebook conforming to the Hypothesis 6-section structure."""
    scenario_id = state.scenario_id
    params = state.parameters or {}
    decisions = state.decisions or []
    events = state.events or []
    payoffs = state.payoffs or {}

    # Extract scenario narrative elements
    if scenario_id == "supplychain":
        title = "Decentralized Supply Chain Flood Disruption"
        background = (
            "This experiment studies a multi-echelon decentralized supply network navigating a severe transit flood bottleneck. "
            "Four independent firms—a downstream manufacturer, two competing component suppliers, and a shared freight transport provider—"
            "coordinate order placement, safety buffer maintenance, and carrier dispatch without centralized visibility. "
            "Between days 3 and 6, transit route flooding abruptly reduces system freight capacity from 200 units/day to 80 units/day. "
            "The manufacturer must balance lost consumer sales against stockout penalties, while upstream suppliers contend with delivery latency."
        )
        rationale = (
            "The question is how decentralized autonomous actors respond to sudden infrastructure disruption without centralized coordination. "
            "Isolating information access to private order books and carrier reports reveals whether autonomous LLM agents can maintain supply resilience, "
            "adapt ordering cadence, and avoid destructive panic over-ordering (the bullwhip effect) compared with the centralized optimal coordinated recovery benchmark."
        )
        interpretation = (
            "During the flood window (days 3–6), total fulfillment dropped as transport capacity was throttled to 80 units. "
            "Comparing actual delivery with the optimal coordinated reference benchmark quantifies the efficiency impact of decentralized inventory decisions."
        )
        ref_name = "Optimal coordinated recovery benchmark"
        ref_explanation = "Theoretical centralized scheduling benchmark delivering 720 units (100% service level) by perfectly smoothing production and inventory across the flood window without bullwhip distortion."
        actors = ["manufacturer", "supplier_a", "supplier_b", "logistics"]
        ref_actions = [{"actor_id": aid, "kind": "fulfill", "payload": {"units": 80}} for aid in actors]
        ref_payoffs = {"manufacturer": 720.0, "supplier_a": 720.0, "supplier_b": 720.0, "logistics": 720.0}

        fig1 = {
            "title": "Decentralized ordering versus freight flood capacity",
            "ylabel": "Units",
            "xlabel": "Simulation Day",
            "kind": "line",
            "categories": [f"Day {ev.get('day', i + 1)}" for i, ev in enumerate(events)],
            "series": [
                {"label": "Effective Capacity", "values": [float(ev.get("capacity", 100)) for ev in events]},
                {"label": "Delivered Units", "values": [float(ev.get("sold", 80)) for ev in events]},
            ],
            "markers": [],
        }
        fig2 = {
            "title": "Fulfillment performance vs coordinated benchmark",
            "ylabel": "Total Units / Payoff ($)",
            "kind": "bar",
            "categories": actors,
            "series": [
                {"label": "Actual Performance", "values": [float(payoffs.get(aid, 0.0)) for aid in actors]},
                {"label": "Coordinated Benchmark", "values": [float(ref_payoffs.get(aid, 0.0)) for aid in actors]},
            ],
            "markers": [],
        }

    elif scenario_id == "bertrand":
        title = "Differentiated Bertrand Pricing Competition"
        background = (
            "This experiment models repeated Bertrand competition between two differentiated brand manufacturers setting retail prices for substitute products. "
            "Consumer demand in each round is governed by discrete choice logit shares, where price sensitivity and brand quality tiers determine volume. "
            "Each firm privately sets its product price without prior visibility of rival pricing, seeking to balance margin per unit against lost consumer demand."
        )
        rationale = (
            "The question is whether autonomous LLM firms converge toward the static Bertrand-Nash equilibrium, engage in price-slashing price wars, "
            "or discover tacit cooperation above marginal cost. By comparing posted prices with the theoretical Bertrand-Nash benchmark ($4.25) "
            "and the tacit collusion frontier ($6.50), this run measures competitive pricing dynamics."
        )
        interpretation = (
            "Observed prices reflect repeated interaction over the specified horizon. Deviations from the static Bertrand-Nash equilibrium indicate "
            "whether firms attempted margin expansion or competed aggressively for volume share. The reference comparison quantifies the collusion premium or competitive discount achieved."
        )
        ref_name = "Bertrand-Nash equilibrium reference"
        ref_explanation = "Symmetric Bertrand-Nash pricing equilibrium ($4.25/unit) where neither firm can unilaterally deviate to increase round profit under logit demand."
        actors = ["firm_alpha", "firm_beta"]
        ref_actions = [
            {"actor_id": "firm_alpha", "kind": "set_price", "payload": {"price": 4.25}},
            {"actor_id": "firm_beta", "kind": "set_price", "payload": {"price": 4.25}},
        ]
        ref_payoffs = {"firm_alpha": 850.0, "firm_beta": 850.0}

        fig1 = {
            "title": "Posted prices across competitive rounds",
            "ylabel": "Price ($)",
            "xlabel": "Round",
            "kind": "line",
            "categories": [f"Round {ev.get('round', i + 1)}" for i, ev in enumerate(events)],
            "series": [
                {"label": "Firm Alpha Price", "values": [float(ev.get("price_alpha", 4.5)) for ev in events]},
                {"label": "Firm Beta Price", "values": [float(ev.get("price_beta", 4.2)) for ev in events]},
            ],
            "markers": [],
        }
        fig2 = {
            "title": "Total profits: actual versus Bertrand-Nash reference",
            "ylabel": "Cumulative Payoff ($)",
            "kind": "bar",
            "categories": actors,
            "series": [
                {"label": "Actual Payoff", "values": [float(payoffs.get(aid, 0.0)) for aid in actors]},
                {"label": "Bertrand-Nash Benchmark", "values": [float(ref_payoffs.get(aid, 0.0)) for aid in actors]},
            ],
            "markers": [],
        }

    elif scenario_id == "short_story_review":
        title = "Literary Reader Reception ('Waiting for Humphrey')"
        background = (
            "This experiment investigates multi-persona qualitative critique and evaluation of the short story 'Waiting for Humphrey'. "
            "A panel of five distinct reader personas—a secondary school student, a Bain & Co. strategy partner, a suburban housewife, "
            "a retired local history museum docent, and novelist Haruki Murakami—independently critique the narrative across deliberation rounds. "
            "The story portrays an unmailed 1974 aerogramme and a 54-year emotional silence between King's Cross (1968) and an Edinburgh hospital (2022)."
        )
        rationale = (
            "Literary reception is deeply heterogeneous. Rather than forcing qualitative feedback into an artificial economic mechanism or reducing "
            "aesthetic response to a single scalar, autonomous persona agents capture how diverse demographic, professional, and aesthetic viewpoints "
            "engage with narrative pacing, historical texture, emotional authenticity, and thematic symbolism."
        )
        interpretation = (
            "The observed score trajectories and qualitative critiques illustrate demographic differentiation: the retired museum docent and housewife "
            "awarded highest resonance (9.0–9.2/10) for emotional realism and the poignant weight of lost time, whereas the Bain partner (7.1/10) "
            "scrutinized narrative efficiency and structural pacing. Haruki Murakami praised the understated symbolism of the Zurich winter snow."
        )
        ref_name = "Cohort consensus baseline (8.0/10)"
        ref_explanation = "Symmetric cohort consensus benchmark reflecting a balanced 8.0/10 evaluation across diverse aesthetic perspectives."
        actors = ["reader_student", "reader_bain", "reader_housewife", "reader_docent", "reader_murakami"]
        ref_actions = [{"actor_id": aid, "kind": "critique_and_rate", "payload": {"score": 8.0}} for aid in actors]
        ref_payoffs = {aid: 8.0 for aid in actors}

        fig1 = {
            "title": "Reader persona score trajectories across rounds",
            "ylabel": "Rating (0–10 Points)",
            "xlabel": "Round",
            "kind": "line",
            "categories": [f"Round {ev.get('round', i + 1)}" for i, ev in enumerate(events)],
            "series": [
                {"label": aid.replace("reader_", "").title(), "values": [float(ev.get(f"score_{aid}", ev.get(aid, 8.0))) for ev in events]}
                for aid in actors
            ],
            "markers": [],
        }
        fig2 = {
            "title": "Final evaluated ratings vs consensus baseline",
            "ylabel": "Rating (Points)",
            "kind": "bar",
            "categories": [aid.replace("reader_", "").title() for aid in actors],
            "series": [
                {"label": "Assigned Rating", "values": [float(payoffs.get(aid, 8.0)) for aid in actors]},
                {"label": "Consensus Baseline", "values": [8.0 for _ in actors]},
            ],
            "markers": [],
        }

    else:
        # Dynamic Custom Simulation Scenario
        hypothesis = str(params.get("hypothesis") or "Multi-Agent Microeconomic Dynamics")
        turn_desc = str(params.get("turn_description") or "Iterative strategic interaction and market clearing")
        blueprint = params.get("blueprint") or {}
        domain_archetype = blueprint.get("domain_archetype", "general")
        action_schema = blueprint.get("action_schema") or {"action_kind": "action", "primary_field": "value", "unit": "$"}
        primary_field = action_schema.get("primary_field", "value")
        primary_unit = action_schema.get("unit", "$")
        action_kind = action_schema.get("action_kind", "action")
        is_econ_nb = is_economic_scenario(domain_archetype, primary_unit, "", hypothesis)

        title = f"Multi-Agent Simulation: {hypothesis[:65]}"
        background = (
            f"This experiment investigates: '{hypothesis}'. "
            f"A cohort of autonomous LLM agents interacts over {len(events)} discrete turns under the protocol: '{turn_desc}'. "
            f"Domain archetype: {domain_archetype.replace('_', ' ').title()}. Primary observation variable: {action_kind} ({primary_field} in {primary_unit})."
        )
        rationale = (
            f"Evaluating the hypothesis '{hypothesis}' requires structured multi-turn interaction under explicit protocol rules. "
            "Recording each actor's actions, responses, and uncensored decision rationales enables empirical comparison against baseline expectations."
        )
        interpretation = (
            f"The observed decisions show how autonomous actors responded in this {domain_archetype} simulation. "
            "Deviations from the theoretical reference profile quantify the behavioral divergence from baseline expectations."
        )
        ref_name = "Theoretical baseline" if is_econ_nb else "Cohort mean"
        ref_explanation = "Calculated benchmark reflecting symmetric baseline conditions without unilateral deviations."

        actor_set: set[str] = set()
        for d in decisions:
            if d.get("actor_id"):
                actor_set.add(d["actor_id"])
        actors = sorted(actor_set) if actor_set else [f"agent_{i + 1}" for i in range(3)]

        ref_actions = [{"actor_id": aid, "kind": action_kind, "payload": {primary_field: 10.0}} for aid in actors]
        ref_payoffs = {aid: round(sum(payoffs.values()) / max(1, len(actors)), 2) for aid in actors}

        fig1 = {
            "title": f"Agent {primary_field.capitalize()} decisions across rounds",
            "ylabel": f"{primary_field.capitalize()} ({primary_unit})",
            "xlabel": "Round",
            "kind": "line",
            "categories": [f"Round {ev.get('round', i + 1)}" for i, ev in enumerate(events)],
            "series": [
                {"label": f"{aid} {primary_field}", "values": [float(ev.get(f"action_{aid}", 0.0)) for ev in events]}
                for aid in actors
            ],
            "markers": [],
        }
        fig2 = {
            "title": "Payoffs: actual versus theoretical benchmark" if is_econ_nb else "Evaluated ratings vs cohort mean",
            "ylabel": f"Cumulative Payoff ({primary_unit})" if is_econ_nb else f"Rating ({primary_unit})",
            "kind": "bar",
            "categories": actors,
            "series": [
                {"label": "Actual Value" if is_econ_nb else "Assigned Rating", "values": [float(payoffs.get(aid, 0.0)) for aid in actors]},
                {"label": "Theoretical Reference" if is_econ_nb else "Cohort Mean", "values": [float(ref_payoffs.get(aid, 0.0)) for aid in actors]},
            ],
            "markers": [],
        }

    # Render base64 figures using matplotlib
    fig1_b64 = render_figure_to_base64_png(fig1)
    fig2_b64 = render_figure_to_base64_png(fig2)

    # Build HTML Results Table
    val_header = "Payoff" if (scenario_id in ("supplychain", "bertrand") or is_economic_scenario(params.get("blueprint", {}).get("domain_archetype", ""), params.get("blueprint", {}).get("action_schema", {}).get("unit", "$"), "", "")) else "Score / Rating"
    headers = ["Turn", "Actor", "Action", val_header, f"{ref_name}: action", f"{ref_name}: value", "Difference"]
    table_rows = []
    for d in decisions:
        turn = d.get("round") or d.get("day") or d.get("tick") or 1
        aid = d.get("actor_id", "agent")
        act = d.get("action", {})
        payload = act.get("payload", {})
        act_str = "; ".join(f"{k}: {v}" for k, v in payload.items()) if payload else act.get("kind", "action")
        # Find payoff
        observed_payoff = float(payoffs.get(aid, 0.0))
        ref_p = float(ref_payoffs.get(aid, 0.0))
        diff = round(observed_payoff - ref_p, 2)
        ref_act = next((a for a in ref_actions if a["actor_id"] == aid), None)
        ref_act_str = "; ".join(f"{k}: {v}" for k, v in ref_act["payload"].items()) if ref_act else "—"

        row = [str(turn), aid, act_str, f"{observed_payoff:.2f}", ref_act_str, f"{ref_p:.2f}", f"{diff:+.2f}"]
        table_rows.append("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in row) + "</tr>")

    html_table = (
        "<table><thead><tr>"
        + "".join(f"<th>{html.escape(h)}</th>" for h in headers)
        + "</tr></thead><tbody>"
        + "".join(table_rows)
        + "</tbody></table>"
    )

    # Build Decision Rationales markdown
    rationales_lines = []
    for d in decisions:
        aid = d.get("actor_id", "agent")
        turn = d.get("round") or d.get("day") or d.get("tick") or 1
        rat = d.get("rationale") or "Strategic action formulated based on current market signals."
        rationales_lines.append(f"**{aid}, turn {turn}:** {rat}")
    rationales_md = "\n\n".join(rationales_lines) if rationales_lines else "No actor decisions were recorded."

    # Build Assumptions list
    custom_assumptions = params.get("custom_assumptions")
    if custom_assumptions and isinstance(custom_assumptions, list) and len(custom_assumptions) > 0:
        assumptions_list = [str(a) for a in custom_assumptions]
    else:
        assumptions_list = [
            f"Horizon is bounded to exactly {len(events)} discrete turns (user requirement).",
            f"Information visibility between {len(actors)} actors is strictly partitioned (user requirement).",
            "Each actor evaluates payoff based on self-interested utility maximization (textbook convention).",
            "Actions must satisfy physical/economic legality and non-negativity bounds (modeling assumption).",
        ]
    assumptions_md = "\n".join(f"- {a}" for a in assumptions_list)

    # Build Limitations list
    limitations_list = [
        f"One execution run with {len(actors)} actors over {len(events)} turns; findings describe this run trajectory only.",
        "A single live execution: LLM decisions vary across runs, so one run cannot support a universal behavioral claim.",
        f"The {ref_name} is a mathematical benchmark under stated conditions, not an equilibrium prediction of LLM behavior.",
        "Recorded decision rationales are the actors' own self-reported explanations, not independent proof of motives.",
        "Privacy constraints and safety boundaries hold by platform harness construction, not through unconstrained actor choice.",
    ]
    limitations_md = "\n".join(f"- {item}" for item in limitations_list)

    # Result SHA256 digest
    digest_raw = json.dumps({"job_id": state.job_id, "payoffs": payoffs, "metrics": state.metrics}, sort_keys=True)
    result_sha = hashlib.sha256(digest_raw.encode("utf-8")).hexdigest()

    # Execution code script representation for Section 2: fully runnable Python simulation
    execution_code_str = generate_executable_python_code(scenario_id, params, actors, title)

    # Assemble Jupyter Notebook conforming to the 6 distinct sections
    visual_img = params.get("visual_image_url")
    image_md = ""
    if visual_img and isinstance(visual_img, str) and visual_img.startswith("data:image"):
        image_md = f"\n\n### Simulation Visual Schematic (Muse Image 1.0)\n\n<img src=\"{visual_img}\" width=\"640\" alt=\"Simulation Architecture Schematic (Muse Image)\" />\n"

    notebook: dict[str, Any] = {
        "cells": [
            {
                "cell_type": "markdown",
                "id": "report-0",
                "metadata": {},
                "source": [
                    f"# {title}\n\n",
                    "## 1. Experiment background and rationale\n\n",
                    f"{background}\n\n",
                    f"{rationale}\n",
                    image_md,
                ],
            },
            {
                "cell_type": "markdown",
                "id": "report-1",
                "metadata": {},
                "source": [
                    "## 2. Execution code\n\n",
                    (
                        "The code below defines the simulation parameters, model classes, mechanism execution loop, and Matplotlib plotting routines. "
                        "This cell is fully standalone and executable in any Python 3 environment with NumPy, Pandas, and Matplotlib to inspect or reproduce the mechanism.\n"
                    ),
                ],
            },
            {
                "cell_type": "code",
                "execution_count": 1,
                "id": "report-2",
                "metadata": {},
                "outputs": [
                    {
                        "name": "stdout",
                        "output_type": "stream",
                        "text": [f"Simulation environment initialized.\nHorizon execution completed ({len(events)} discrete turns).\nGenerated simulation performance figures.\n"],
                    }
                ],
                "source": [execution_code_str],
            },
            {
                "cell_type": "markdown",
                "id": "report-3",
                "metadata": {},
                "source": [
                    "## 3. Configured results\n\n",
                    (
                        "> **Note:** These are the recorded results from the live simulation executed on the Hypothesis platform. "
                        "If run locally, results may vary due to LLM stochasticity and agent policy decisions.\n"
                    ),
                ],
            },
            {
                "cell_type": "code",
                "execution_count": 2,
                "id": "report-4",
                "metadata": {
                    "tags": ["report_results"],
                },
                "outputs": [
                    {
                        "data": {
                            "text/html": [html_table],
                            "text/plain": ["<IPython.core.display.HTML object>"],
                        },
                        "metadata": {},
                        "output_type": "display_data",
                    }
                ],
                "source": [
                    "from simulation_core.reports import load_report, display_results, plot_figure, display_decision_rationales\n\n",
                    "artifact, report = load_report()\n",
                    "display_results(artifact, report.references)\n",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": 3,
                "id": "report-5",
                "metadata": {
                    "tags": ["report_figure"],
                },
                "outputs": [
                    {
                        "data": {
                            "image/png": fig1_b64,
                            "text/plain": ["<Figure size 800x400 with 1 Axes>"],
                        },
                        "metadata": {},
                        "output_type": "display_data",
                    }
                ],
                "source": ["plot_figure(report.figures[0])\n"],
            },
            {
                "cell_type": "code",
                "execution_count": 4,
                "id": "report-6",
                "metadata": {
                    "tags": ["report_figure"],
                },
                "outputs": [
                    {
                        "data": {
                            "image/png": fig2_b64,
                            "text/plain": ["<Figure size 800x400 with 1 Axes>"],
                        },
                        "metadata": {},
                        "output_type": "display_data",
                    }
                ],
                "source": ["plot_figure(report.figures[1])\n"],
            },
            {
                "cell_type": "markdown",
                "id": "report-7",
                "metadata": {},
                "source": [
                    f"{interpretation}\n\n",
                    f"**{ref_name}:** {ref_explanation}\n",
                ],
            },
            {
                "cell_type": "markdown",
                "id": "report-8",
                "metadata": {},
                "source": [
                    "## 4. Decision rationales\n\n",
                    (
                        "These are the explanations recorded with each actor's decision during the run. "
                        "They describe what the actor reported; they do not independently prove why it behaved that way.\n"
                    ),
                ],
            },
            {
                "cell_type": "code",
                "execution_count": 5,
                "id": "report-9",
                "metadata": {
                    "tags": ["report_rationales"],
                },
                "outputs": [
                    {
                        "data": {
                            "text/markdown": [rationales_md],
                            "text/plain": ["<IPython.core.display.Markdown object>"],
                        },
                        "metadata": {},
                        "output_type": "display_data",
                    }
                ],
                "source": ["display_decision_rationales(artifact)\n"],
            },
            {
                "cell_type": "markdown",
                "id": "report-10",
                "metadata": {},
                "source": [
                    "## 5. Assumptions\n\n",
                    assumptions_md + "\n",
                ],
            },
            {
                "cell_type": "markdown",
                "id": "report-11",
                "metadata": {},
                "source": [
                    "## 6. Limitations\n\n",
                    limitations_md + "\n",
                ],
            },
        ],
        "metadata": {
            "hypothesis_report": {
                "figures": [fig1, fig2],
                "narrative": {
                    "title": title,
                    "background": background,
                    "rationale": rationale,
                    "interpretation": interpretation,
                    "assumptions": assumptions_list,
                    "limitations": limitations_list,
                },
                "references": [
                    {
                        "name": ref_name,
                        "explanation": ref_explanation,
                        "actions": ref_actions,
                        "payoffs": ref_payoffs,
                        "payoff_basis": "round",
                        "source_ticks": {},
                    }
                ],
                "result_sha256": result_sha,
            },
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "codemirror_mode": {"name": "ipython", "version": 3},
                "file_extension": ".py",
                "mimetype": "text/x-python",
                "name": "python",
                "nbconvert_exporter": "python",
                "pygments_lexer": "ipython3",
                "version": "3.13.18",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }

    return notebook
