import pytest
from fastapi.testclient import TestClient

from web.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_list_presets(client):
    response = client.get("/api/presets")
    assert response.status_code == 200
    presets = response.json()
    assert len(presets) == 3
    preset_ids = {p["id"] for p in presets}
    assert "supplychain" in preset_ids
    assert "bertrand" in preset_ids
    assert "short_story_review" in preset_ids


def test_align_simulation(client):
    payload = {
        "hypothesis": "Test Supply Shock",
        "num_turns": 6,
        "num_agents": 4,
        "turn_description": "Suppliers quote prices, buyers purchase",
        "constraints": "Non-negative inventory",
    }
    response = client.post("/api/simulations/align", json=payload)
    assert response.status_code == 200
    data = response.json()
    readback = data["readback"].lower()
    assert "supply" in readback and "shock" in readback
    assert len(data["assumptions"]) >= 3
    assert len(data["feasibility_rules"]) >= 2
    assert "schematic_image_prompt" in data


def test_run_preset_simulation_and_get_results(client):
    run_payload = {
        "kind": "preset",
        "scenario_id": "bertrand",
        "parameters": {"rounds": 2, "marginal_cost": 2.0, "agent_mode": "heuristic"},
    }
    response = client.post("/api/simulations/run", json=run_payload)
    assert response.status_code == 200
    job_info = response.json()
    job_id = job_info["job_id"]
    assert job_id.startswith("job_")

    # Poll status until complete
    status_response = client.get(f"/api/simulations/{job_id}")
    assert status_response.status_code == 200

    results_response = client.get(f"/api/simulations/{job_id}/results")
    assert results_response.status_code == 200
    results = results_response.json()
    assert "payoffs" in results
    assert "metrics" in results


def test_run_short_story_review_preset(client):
    run_payload = {
        "kind": "preset",
        "scenario_id": "short_story_review",
        "parameters": {"rounds": 2, "agent_mode": "heuristic"},
    }
    response = client.post("/api/simulations/run", json=run_payload)
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    results_response = client.get(f"/api/simulations/{job_id}/results")
    assert results_response.status_code == 200
    results = results_response.json()
    assert len(results["payoffs"]) == 5
    assert "reader_student" in results["payoffs"]
    assert "reader_murakami" in results["payoffs"]
    assert len(results["decisions"]) == 10
    assert len(results["events"]) == 2
    assert "mean_cohort_score" in results["metrics"]

    # Verify downloaded notebook has executable Python code for short story
    nb_res = client.get(f"/api/simulations/{job_id}/download/notebook")
    assert nb_res.status_code == 200
    nb = nb_res.json()
    sources = ["".join(c["source"]) for c in nb["cells"]]
    combined_text = "\n".join(sources)
    assert "ReaderReceptionEnvironment" in combined_text
    assert "## 2. Execution code" in combined_text
    assert "## 3. Configured results" in combined_text
    assert "Waiting for Humphrey" in combined_text


def test_download_artifacts(client):
    run_payload = {
        "kind": "preset",
        "scenario_id": "bertrand",
        "parameters": {"rounds": 2, "agent_mode": "heuristic"},
    }
    job_id = client.post("/api/simulations/run", json=run_payload).json()["job_id"]

    # Download notebook
    nb_res = client.get(f"/api/simulations/{job_id}/download/notebook")
    assert nb_res.status_code == 200
    nb = nb_res.json()
    assert "cells" in nb
    assert len(nb["cells"]) >= 10

    # Verify sections
    sources = ["".join(c["source"]) for c in nb["cells"]]
    combined_text = "\n".join(sources)
    assert "## 1. Experiment background and rationale" in combined_text
    assert "## 2. Execution code" in combined_text
    assert "DifferentiatedBertrandMarket" in combined_text
    assert "## 3. Configured results" in combined_text
    assert "Hypothesis platform" in combined_text
    assert "if run locally, results may vary" in combined_text.lower()
    assert "## 4. Decision rationales" in combined_text
    assert "## 5. Assumptions" in combined_text
    assert "## 6. Limitations" in combined_text

    # Verify metadata
    assert "hypothesis_report" in nb["metadata"]
    assert "figures" in nb["metadata"]["hypothesis_report"]
    assert "references" in nb["metadata"]["hypothesis_report"]

    # Download events
    ev_res = client.get(f"/api/simulations/{job_id}/download/events")
    assert ev_res.status_code == 200


def test_sandbox_prepare(client):
    res = client.post("/api/sandbox/prepare")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("ready", "warning")
    assert data["agent"] == "muse_coding_agent"


def test_contradictions_block_simulation(client):
    run_payload = {
        "kind": "custom",
        "scenario_id": "custom_experiment",
        "parameters": {
            "hypothesis": "Test Contradiction",
            "contradictions": [
                "Hypothesis assumes non-negative pricing but turn protocol mandates zero-revenue disposal.",
            ],
        },
    }
    res = client.post("/api/simulations/run", json=run_payload)
    assert res.status_code == 400
    assert "unresolved contradiction" in res.json()["detail"].lower()


def test_run_custom_simulation_dynamic(client):
    run_payload = {
        "kind": "custom",
        "scenario_id": "custom_experiment",
        "parameters": {
            "hypothesis": "Test Collusion in Retail Pricing",
            "turn_description": "Firms post prices sequentially",
            "num_turns": 1,
            "num_agents": 2,
        },
    }
    response = client.post("/api/simulations/run", json=run_payload)
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    results_res = client.get(f"/api/simulations/{job_id}/results")
    assert results_res.status_code == 200
    data = results_res.json()
    assert len(data["payoffs"]) == 2
    assert "agent_1" in data["payoffs"]
    assert "agent_2" in data["payoffs"]
    assert len(data["decisions"]) >= 2
    assert len(data["decisions"][0]["rationale"]) > 20
    assert len(data["events"]) == 1


def test_align_fails_cleanly_when_llm_unavailable(client, monkeypatch):
    import components.gateways.live as live_gw

    def mock_fail():
        raise RuntimeError("Simulated gateway network disconnect")

    monkeypatch.setattr(live_gw, "configured_gateway", mock_fail)

    payload = {
        "hypothesis": "Test Offline Failure Handling",
        "num_turns": 3,
        "num_agents": 2,
        "turn_description": "Sequential moves",
    }
    response = client.post("/api/simulations/align", json=payload)
    assert response.status_code == 503
    assert "Unable to connect to the LLM" in response.json()["detail"]
    assert "Featured Showcase" in response.json()["detail"]


def test_process_uploaded_document():
    import base64
    from io import BytesIO

    from PIL import Image

    from web.app import process_uploaded_document

    # Test PNG image processing
    img = Image.new("RGB", (100, 100), color="blue")
    buf = BytesIO()
    img.save(buf, format="PNG")
    b64_png = base64.b64encode(buf.getvalue()).decode("utf-8")

    doc_info = process_uploaded_document({
        "name": "market_chart.png",
        "type": "image/png",
        "data_base64": f"data:image/png;base64,{b64_png}",
    })
    assert doc_info["filename"] == "market_chart.png"
    assert doc_info["mime_type"] == "image/png"
    assert doc_info["dimensions"] == "100x100"


def test_generate_image_endpoint(client, monkeypatch):
    import web.app as web_app

    def mock_generate(prompt: str) -> str:
        return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

    monkeypatch.setattr(web_app, "generate_muse_image", mock_generate)

    res = client.post("/api/simulations/generate-image", json={"prompt": "Test schematic"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["model"] == "muse-image-1.0"
    assert data["image_url"].startswith("data:image/png;base64,")


def test_is_economic_scenario_detection():
    from web.presets import is_economic_scenario
    assert is_economic_scenario("differentiated_pricing", "$", "logit_choice", "Pricing war") is True
    assert is_economic_scenario("auction", "$", "second_price", "Vickrey bidding") is True
    assert is_economic_scenario("literary_reception_evaluation", "points_on_0_to_10_scale", "independent_collection_without_clearing", "Evaluate readers' reactions to the short story") is False
    assert is_economic_scenario("creative_feedback", "/10", "independent_feedback", "Short story critique") is False


def test_faulty_pdf_manuscript_rejected_by_api(client):
    import base64

    # Corrupted PDF bytes
    corrupt_b64 = base64.b64encode(b"%PDF-1.4 corrupted incomplete stream byte garbage").decode("utf-8")
    payload = {
        "kind": "preset",
        "scenario_id": "short_story_review",
        "parameters": {
            "rounds": 1,
            "agent_mode": "heuristic",
            "manuscript_pdf": {
                "name": "corrupt_story.pdf",
                "type": "application/pdf",
                "data_base64": f"data:application/pdf;base64,{corrupt_b64}",
            },
        },
    }
    response = client.post("/api/simulations/run", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert "PDF parsing error" in data["detail"]
    assert "PDF parsing is faulty" in data["detail"]


def test_empty_pdf_manuscript_rejected(client):
    import base64

    empty_b64 = base64.b64encode(b"").decode("utf-8")
    payload = {
        "kind": "preset",
        "scenario_id": "short_story_review",
        "parameters": {
            "rounds": 1,
            "agent_mode": "heuristic",
            "manuscript_pdf": {
                "name": "empty.pdf",
                "type": "application/pdf",
                "data_base64": empty_b64,
            },
        },
    }
    response = client.post("/api/simulations/run", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert "PDF parsing is faulty" in data["detail"]


def test_process_uploaded_document_faulty_pdf_detection():
    import base64
    from web.app import process_uploaded_document

    # 1. Truncated bytes
    res_trunc = process_uploaded_document({
        "name": "bad.pdf",
        "type": "application/pdf",
        "data_base64": base64.b64encode(b"tiny").decode("utf-8"),
    })
    assert "error" in res_trunc
    assert "PDF parsing is faulty" in res_trunc["error"]

    # 2. Corrupt non-PDF bytes
    res_corrupt = process_uploaded_document({
        "name": "broken.pdf",
        "type": "application/pdf",
        "data_base64": base64.b64encode(b"This is definitely not a real PDF structure and will fail to parse").decode("utf-8"),
    })
    assert "error" in res_corrupt
    assert "PDF parsing is faulty" in res_corrupt["error"]



