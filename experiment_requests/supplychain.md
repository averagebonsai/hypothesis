# Simulation Request: Supply-Chain Disruption and Multi-Agent Coordination

## 1. Problem Description

A consumer electronics manufacturer relies on two suppliers to provide critical components for its products. Both suppliers deliver components through a shared logistics provider.

A severe regional flooding event disrupts transportation infrastructure, reducing shipping capacity and causing delays. The manufacturer must maintain production while suppliers compete for limited transportation resources.

Each organization makes decisions independently, based on its own objectives and the information available to it.

**Primary research question:**

How does information sharing and coordination between supply-chain participants affect production continuity, supply-chain costs, and recovery time following a major disruption?

The experiment should run 1 scenario:

- **Decentralized response:** Each actor makes decisions using limited information. Organizations prioritize their own objectives and do not share private operational information.

## 2. Simulation Environment

Simulate a supply chain over **9 rounds**, with each round representing one day.

There are four organizations:

1. One manufacturer.
2. Supplier A.
3. Supplier B.
4. One logistics provider.

The manufacturer produces finished electronic products using components supplied by both suppliers.

Each finished product requires:

- One unit of Component A, supplied exclusively by Supplier A.
- One unit of Component B, supplied exclusively by Supplier B.

Production cannot occur unless both components are available.

### Initial conditions

| Variable | Initial value |
|---|---:|
| Manufacturer inventory — Component A | 150 units |
| Manufacturer inventory — Component B | 150 units |
| Supplier A initial inventory | 200 units |
| Supplier B initial inventory | 200 units |
| Supplier A daily production capacity | 100 units |
| Supplier B daily production capacity | 100 units |
| Manufacturer daily production capacity | 100 finished products |
| Customer demand | 80 finished products per day |
| Normal logistics capacity | 200 component units per day |
| Disrupted logistics capacity | 80 component units per day |
| Manufacturer finished-goods inventory | 0 units |

The flood occurs at the beginning of Round 3.

- Rounds 1–2: Normal logistics capacity.
- Rounds 3–6: Logistics capacity reduced to 80 units per day.
- Rounds 7–9: Logistics capacity restored to 200 units per day.

These values are hypothetical and should be treated as experimental assumptions.

### Transportation

All component shipments use the shared logistics provider.

Transportation capacity is measured in individual component units, not finished-product equivalents.

For example, shipping 50 units of Component A and 50 units of Component B consumes 100 units of logistics capacity.

All shipments have a one-round transit delay. A shipment dispatched in Round 3 arrives at the beginning of Round 4.

The logistics provider cannot exceed its daily shipping capacity.

Unshipped components remain at their respective suppliers.

## 3. Actors and Decision-Making

Each actor has its own objective, action space, private information, and observation rules.

### Actor 1 — Manufacturer

**Objective:** Maximize fulfilled customer demand while minimizing inventory holding costs, procurement costs, and production disruptions.

**Available actions:**

- Submit an order quantity to Supplier A.
- Submit an order quantity to Supplier B.
- Choose the number of finished products to manufacture.
- Request transportation priority for specific shipments.

**Private information:**

- Current component inventory.
- Finished-goods inventory.
- Customer demand.
- Outstanding orders.
- Internal production capacity.
- Accumulated costs and unmet demand.

**Public information:**

- Published transportation capacity.
- Disruption status.
- Confirmed shipment arrivals.
- Supplier delivery commitments.

The manufacturer does not automatically know suppliers' true inventories or production capacities in the decentralized scenario.

### Actor 2 — Supplier A

**Objective:** Maximize revenue from fulfilled orders while minimizing production, inventory holding, and unfulfilled-order costs.

**Available actions:**

- Choose daily production quantity.
- Accept or partially fulfill manufacturer orders.
- Submit available shipment quantities to the logistics provider.
- Request transportation priority.

**Private information:**

- Current Component A inventory.
- Production capacity.
- Production cost.
- Outstanding orders.
- Accumulated profit.

Supplier A does not observe Supplier B's inventory, production decisions, or outstanding orders in the decentralized scenario.

### Actor 3 — Supplier B

Supplier B has the same action types and objective structure as Supplier A, but controls Component B.

Its operational state is independent of Supplier A.

Supplier B cannot observe Supplier A's private information unless information sharing is enabled.

### Actor 4 — Logistics Provider

**Objective:** Maximize completed deliveries and transportation revenue while minimizing unused capacity, transportation costs, and unfulfilled shipment requests.

**Available actions:**

- Allocate available shipping capacity between Supplier A and Supplier B.
- Accept or defer shipment requests.
- Prioritize shipments according to its decision policy.

**Private information:**

- Current shipment requests.
- Transportation capacity.
- Pending shipments.
- Transportation operating costs.

The logistics provider does not automatically know the manufacturer's internal inventory or customer demand in the decentralized scenario.

## 4. Information Sharing Intervention

The primary intervention is the information available to each actor.

### Scenario A — Decentralized

Actors observe only their own private operational information and explicitly communicated orders, commitments, and shipment confirmations.

They cannot access other organizations' private inventories, costs, or production decisions.

### Scenario B — Coordinated

Before each round's decisions, actors receive a shared operational dashboard containing:

- Manufacturer component inventory.
- Manufacturer outstanding component requirements.
- Supplier inventories.
- Supplier production capacities.
- Pending shipment requests.
- Available logistics capacity.
- Expected shipment arrivals.

The information must be generated from the authoritative world state. Actors cannot invent or alter dashboard values.

The dashboard reveals operational information but does not grant any actor control over another actor's actions.

All other model parameters, costs, action spaces, and physical constraints must remain identical between scenarios.

## 5. Physical and Economic Constraints

The simulation must enforce the following constraints.

### Inventory conservation

Inventory cannot become negative.

For each supplier:

Ending inventory = Starting inventory + Production − Components dispatched.

For the manufacturer:

Ending component inventory = Starting inventory + Arriving shipments − Components consumed in production.

### Production constraints

Supplier production cannot exceed available daily production capacity.

Manufacturer production cannot exceed daily production capacity or available component inventory.

Each finished product consumes exactly one unit of Component A and one unit of Component B.

### Transportation constraints

Total dispatched components cannot exceed the logistics provider's daily capacity.

Shipments cannot exceed components physically available for dispatch.

A shipment cannot arrive before its scheduled arrival round.

### Demand fulfillment

The manufacturer can fulfill customer demand using finished goods produced during the current round and any existing finished-goods inventory.

Unfulfilled customer demand is recorded as lost sales rather than carried forward.

### Accounting constraints

All inventory, production, shipments, costs, revenues, and profits must be calculated from actual committed state transitions.

Actors cannot create inventory, transportation capacity, or financial resources through their decisions.

## 6. Economic Parameters

Use the following hypothetical values:

| Parameter | Value |
|---|---:|
| Finished-product selling price | $100 |
| Component A procurement price | $20/unit |
| Component B procurement price | $20/unit |
| Supplier A production cost | $12/unit |
| Supplier B production cost | $12/unit |
| Manufacturer assembly cost | $15/product |
| Logistics transportation charge | $5/component unit |
| Logistics operating cost | $3/component unit |
| Manufacturer component holding cost | $1/unit/day |
| Supplier inventory holding cost | $0.50/unit/day |
| Manufacturer finished-goods holding cost | $2/unit/day |

Use consistent accounting conventions.

Procurement and logistics charges should be recognized when components are dispatched, while the manufacturer's assembly costs should be recognized when finished products are produced.

Supplier revenue is earned on dispatched components.

The manufacturer earns revenue only from finished products sold to customers.

Do not double-count transfers when calculating total supply-chain profit. Consolidated profit should exclude internal transfers between participating organizations.

## 7. Round Structure

Each round represents one day and follows a fixed sequence.

**Phase 1 — State update**

- Deliver shipments scheduled to arrive at the beginning of the round.
- Apply the current day's transportation capacity.
- Update the publicly known disruption status.
- Generate each actor's permitted observation.

**Phase 2 — Manufacturer decisions**

The manufacturer submits component orders and requested shipment priorities.

**Phase 3 — Supplier decisions**

Suppliers observe the orders they received.

Each supplier chooses production quantity, order fulfillment quantity, and shipment requests.

Supplier decisions occur simultaneously, without visibility into the other supplier's current uncommitted actions.

**Phase 4 — Logistics decisions**

The logistics provider observes submitted shipment requests and allocates the available transportation capacity.

It cannot allocate more than the requested quantity or available shipping capacity.

**Phase 5 — Dispatch and production**

- Dispatch accepted component shipments.
- Deduct dispatched quantities from supplier inventories.
- Schedule shipments for arrival in the next round.
- The manufacturer chooses and executes production using components currently in its inventory.
- Finished products become available for sale during the same round.

**Phase 6 — Customer demand and accounting**

- Fulfill customer demand using available finished products.
- Record lost sales.
- Calculate revenues, costs, profits, and inventory balances.
- Commit the updated world state.
- Append actions and outcomes to the event log.

The round ends after all state changes and accounting calculations are complete.

## 8. Actor Policies

Use LLM-driven policies for all four organizations.

Each actor receives a role-specific observation containing:

- Its objective.
- Its available actions.
- Its permitted operational information.
- Its own past decisions and outcomes.
- The current round number.

The LLM must return structured actions conforming to the actor's Pydantic action schema.

The runtime must validate all actions before committing them.

If an actor proposes an infeasible action, reject it and request a corrected action within a fixed retry budget. If retries are exhausted, apply an explicitly documented safe fallback, such as zero production or zero shipment allocation, and record the failure.

Do not permit actors to modify the world state directly.

Use the same underlying LLM model and policy instructions across both scenarios. The information-sharing intervention should affect observations, not the actors' underlying objectives.

## 9. Experimental Design

Run the simulation under both scenarios.

Use identical initial conditions and disruption schedules.

For each scenario, conduct five independent replications with controlled random seeds where supported.

Preserve model configuration, prompts, and execution settings for reproducibility.

Record any nondeterminism from LLM responses.

### Primary outcome metrics

1. Total finished products sold.
2. Total lost customer demand.
3. Total consolidated supply-chain profit.
4. Number of days with production below customer demand.
5. Time required to return to stable fulfillment after logistics capacity is restored.

Define stable fulfillment as three consecutive days with zero lost sales. If this condition is not reached by Round 12, report that recovery was not observed within the simulation horizon.

### Secondary outcome metrics

- Component inventory by organization.
- Unused logistics capacity.
- Supplier production utilization.
- Component shipment delays.
- Individual actor profits.
- Allocation imbalance between Components A and B.

## 10. Required Visualizations

Produce an explanatory notebook containing:

1. A timeline of the flood disruption and transportation-capacity changes.
2. Finished-product sales versus customer demand by round.
3. Manufacturer inventory levels for Components A and B.
4. Transportation capacity utilization.
5. Cumulative consolidated supply-chain profit.
6. A comparison of decentralized and coordinated outcomes.
7. A turn-by-turn explanation of significant decisions and resulting consequences.

Distinguish actual simulation results from hypothetical examples or fixture data.

## 11. Implementation Requirements

Use the existing simulation toolkit and extension-development SOP.

Before implementing:

- Identify which components can be reused.
- Identify missing capabilities.
- Propose the smallest necessary extensions.
- Document mathematical and behavioral assumptions.
- Generate software, mathematical, and integration tests.

Do not modify the trusted simulation runtime or parent interfaces.

Any newly generated components must implement the appropriate existing interfaces.

Run generated code inside the configured isolated execution environment.

Preserve the extension specifications, tests, validation reports, simulation configurations, event logs, and results.

## 12. Required Validation

At minimum, test:

- Inventory conservation.
- Production capacity constraints.
- Transportation capacity constraints.
- Shipment timing.
- Demand fulfillment and lost-sales accounting.
- Financial accounting consistency.
- Simultaneous supplier information boundaries.
- Scenario-specific information access.
- Deterministic mechanism behavior for fixed action sequences.
- Correct application of the flood disruption.
- Correct recovery of transportation capacity.
- No changes to the trusted runtime.

Also test boundary cases, including zero transport capacity, empty inventories, and shipment requests exceeding available capacity.

## 13. Reporting and Interpretation

The final report must explain:

- What each organization attempted to achieve.
- How the information-sharing intervention changed decisions.
- How decisions affected inventory, production, shipping, and customer fulfillment.
- Whether coordination improved the specified outcome metrics.
- Which bottlenecks were most consequential.
- Whether results were consistent across replications.
- Which assumptions materially influenced the conclusions.

The objective is to explore how coordination and information access affect outcomes within the specified supply-chain model, not to forecast an actual disaster with established accuracy.