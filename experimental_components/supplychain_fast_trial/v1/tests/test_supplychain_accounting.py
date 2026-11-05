"""Financial identities and multi-day conservation, recomputed independently."""

from experiment_extension.supplychain import Parameters, capacity_for_day, max_sellable_bound
from support import PARAMS, run_with_sequences

SCRIPTS = {
    "manufacturer": (
        [("order", {"order_a": 80, "order_b": 80, "priority": "none"})]
        + [("produce", {"produce": 80})]
    ),
    "supplier_a": [("offer", {"produce": 80, "offer": 80, "priority_request": False})],
    "supplier_b": [("offer", {"produce": 80, "offer": 80, "priority_request": False})],
    "logistics": [("allocate", {"alloc_a": 40, "alloc_b": 40})],
}


def full_script():
    produces = (80, 80, 70, 60, 60, 60, 60, 80, 80)
    manufacturer = [
        action
        for day in range(9)
        for action in (
            ("order", {"order_a": 80, "order_b": 80, "priority": "none"}),
            ("produce", {"produce": produces[day]}),
        )
    ]
    return {
        "manufacturer": manufacturer,
        "supplier_a": [
            ("offer", {"produce": 80, "offer": 80, "priority_request": False}) for _ in range(9)
        ],
        "supplier_b": [
            ("offer", {"produce": 80, "offer": 80, "priority_request": False}) for _ in range(9)
        ],
        "logistics": (
            [("allocate", {"alloc_a": 80, "alloc_b": 80}) for _ in range(2)]
            + [("allocate", {"alloc_a": 40, "alloc_b": 40}) for _ in range(4)]
            + [("allocate", {"alloc_a": 80, "alloc_b": 80}) for _ in range(3)]
        ),
    }


def test_transfers_cancel_and_match_consolidated_total():
    artifact = run_with_sequences(full_script())
    assert artifact.result.status == "completed"
    assert len([e for e in artifact.result.events if e.kind == "committed"]) == 36
    totals = artifact.result.final_state.public["history"]
    assert len(totals) == 9
    state_totals = artifact.result.final_state.public["totals"]
    profits: dict[str, float] = {}
    for event in artifact.result.events:
        if event.outcome is None:
            continue
        for actor_id, value in event.outcome.payoffs.items():
            profits[actor_id] = profits.get(actor_id, 0.0) + value
    # Transfers cancel: consolidated profit equals the sum of actor payoffs,
    # and the recorded consolidated total agrees with that sum.
    assert (
        state_totals["consolidated"]
        == profits["manufacturer"]
        + profits["supplier_a"]
        + profits["supplier_b"]
        + profits["logistics"]
    )
    # Independent recomputation from recorded day rows, not the transition helper.
    revenue = PARAMS["finished_selling_price"] * state_totals["sold"]
    real_costs = (
        state_totals["supplier_production_cost"]
        + state_totals["assembly_cost"]
        + state_totals["transport_operating_cost"]
        + state_totals["holding_cost"]
    )
    assert state_totals["consolidated"] == revenue - real_costs
    assert state_totals["sold"] == sum(row["sold"] for row in totals)
    assert state_totals["lost"] == sum(row["lost"] for row in totals)
    assert state_totals["consumer_revenue"] == 100.0 * state_totals["sold"]
    assert capacity_for_day(PARAMS["capacity_schedule"], 3) == totals[2]["capacity"] == 80


def test_component_conservation_with_in_transit():
    assert max_sellable_bound(Parameters.from_json_values(PARAMS)) == 720
    artifact = run_with_sequences(full_script())
    history = artifact.result.final_state.public["history"]
    final = artifact.result.final_state
    mfg_a = final.private["manufacturer"].facts["comp_a"]
    mfg_b = final.private["manufacturer"].facts["comp_b"]
    in_transit_a = sum(s["quantity"] for s in final.public["in_transit"] if s["component"] == "A")
    in_transit_b = sum(s["quantity"] for s in final.public["in_transit"] if s["component"] == "B")
    for component, mfg_close, in_transit, supplier in (
        ("A", mfg_a, in_transit_a, "supplier_a"),
        ("B", mfg_b, in_transit_b, "supplier_b"),
    ):
        produced = sum(r[f"produce_{component.lower()}"] for r in history)
        dispatched = sum(r[f"alloc_{component.lower()}"] for r in history)
        consumed = sum(r["mfg_produce"] for r in history)
        closing_supplier = final.private[supplier].facts["inventory"]
        assert 200 + produced == dispatched + closing_supplier  # supplier line
        assert 150 + dispatched == consumed + mfg_close + in_transit  # manufacturer line


def test_day_three_and_day_seven_capacity_boundaries():
    artifact = run_with_sequences(full_script())
    history = artifact.result.final_state.public["history"]
    by_day = {row["day"]: row for row in history}
    schedule = PARAMS["capacity_schedule"]
    for row in history:
        assert capacity_for_day(schedule, row["day"]) == row["capacity"]
    assert by_day[2]["capacity"] == 200
    assert by_day[3]["capacity"] == 80
    assert by_day[6]["capacity"] == 80
    assert by_day[7]["capacity"] == 200
    for day in (3, 4, 5, 6):
        assert by_day[day]["alloc_a"] + by_day[day]["alloc_b"] <= 80
    assert by_day[1]["alloc_a"] + by_day[1]["alloc_b"] <= 200


def test_physical_sales_ceiling():
    params = Parameters.from_json_values(PARAMS)
    assert max_sellable_bound(params) == 720
    artifact = run_with_sequences(full_script())
    totals = artifact.result.final_state.public["totals"]
    assert totals["sold"] <= max_sellable_bound(params)


def test_lost_sales_never_become_backlog():
    params = Parameters.from_json_values(PARAMS)
    assert max_sellable_bound(params) == 720
    artifact = run_with_sequences(full_script())
    for row in artifact.result.final_state.public["history"]:
        assert row["lost"] >= 0
        assert row["sold"] <= 80
    assert artifact.result.final_state.private["manufacturer"].facts["finished_goods"] >= 0
    # Day-9 dispatches remain in transit beyond the horizon.
    assert artifact.result.final_state.public["in_transit"] != []
    assert all(s["arrival_day"] == 10 for s in artifact.result.final_state.public["in_transit"])
