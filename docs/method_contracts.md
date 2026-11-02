# Method assumptions and guarantees

Methods expose a typed `MethodContract`: requirements, conditional guarantees, and
limitations. `assess(...)` returns a report for a particular problem without running
the search or calling actors. `solve(...)` attaches that report as `applicability`.

| Method | Requirements and scope | What the method does not establish |
|---|---|---|
| Pure Nash enumeration | Finite, nonempty, correctly owned action lists; deterministic complete finite payoffs; enough budget to enumerate all profiles | Mixed equilibria; results outside the supplied action domains. No convexity, continuity, or differentiability assumption is needed. |
| Textbook Bertrand | Standard homogeneous market rules, truncated linear demand, unlimited supply, exact tie splitting; two firms with equal constant nonnegative costs; marginal-cost price feasible with positive demand and room above it | Applicability to differentiated products, capacity limits, unequal costs, or arbitrary custom market rules; prediction of LLM behavior |
| Stackelberg backward induction | Standard two-firm linear inverse-demand quantity model, nonnegative constant costs, bounded nonnegative quantities, irrevocable leader commitment, observed follower continuation, minimum-quantity follower tie rule | All possible tied follower strategies; rationality of LLM behavior. Global concavity is not needed because the leader problem is split into analytic branches. |
| Numerical Nash | Finite scalar intervals, unique actors, deterministic pure finite payoffs, correct sufficiently smooth own-payoff gradients for the root-search stage | Global best responses, uniqueness, completeness, or existence/nonexistence from convergence/failure. Convexity/concavity is neither required nor certified. |
| Scalar search | Finite ordered interval, feasible finite current point, finite evaluated outputs; deterministic objective for caching and suitable local regularity for refinements | Global optimality, unimodality, convexity, or concavity from finite samples or successful local refinement |

All numerical implementations use floating-point arithmetic and declared tolerances.
A successful method status must be interpreted together with its applicability
report and limitations. `certification="analytic"` describes the method, not a
machine-checked proof that an arbitrary supplied implementation satisfies its
mathematical assumptions.

## Discover and assess

```python
from components.library import standard_registry
from components.solvers.bertrand import TextbookBertrandSolver

catalog = standard_registry().describe()["solver_contracts"]
contract = TextbookBertrandSolver.contract
print(contract.requirements)
print(contract.guarantees)
print(contract.limitations)

# When you have a game view:
report = TextbookBertrandSolver().assess(game, {})
for requirement, evidence in zip(report.contract.requirements, report.evidence):
    print(requirement.id, requirement.enforcement,
          evidence.status, evidence.basis, evidence.explanation)
print("Execution allowed:", report.can_execute)
print("All listed preconditions established:", report.preconditions_verified)

result = TextbookBertrandSolver().solve(game, {})
assert result.applicability is not None
```

For a resolved experiment, use `registry.benchmark_applicability(config)` with the
appropriate registry/gateway injection. This validates composition and reports the
benchmark's applicability without executing actor decisions or searching payoffs.
For scalar tools use `SCALAR_SEARCH_CONTRACT` and `assess_scalar_search(bounds, current)`
in `components.common.math.scalar`; successful ScalarMaximum results retain the
report, including the finite-output check for actually evaluated points.

## Enforcement and evidence

- **Required:** violated or unverified conditions block the algorithm. The public
  solver returns `unsupported` with the report; `report.require_execution()` raises
  `ApplicabilityError`. These checks remain active under `python -O`.
- **Conditional:** execution is permitted, but the guarantee remains conditional
  while any such assumption is unverified or violated. For example, a numerical
  search can be useful without a proof of smoothness, but it cannot claim the
  associated convergence guarantee. Budget exhaustion has its own result status.
- **Verified:** supported by an explicit runtime check, a known model definition,
  or an analytical argument recorded by trusted component code.
- **Unverified:** an unresolved property, declaration, or positive sampled test.
  Do not silently turn an assumption into a fact.
- **Violated:** an explicit check or counterexample contradicts the requirement.

The generic interface cannot prove that an arbitrary function is pure, smooth, or
convex. These properties deliberately stay unverified when no suitable evidence is
available. Analytical market-rule evidence is restricted to the standard
implementations. A subclass is not automatically assumed to preserve a theorem.
Extensions must supply their own justified evidence or override the assessment.

A caller that requires all listed preconditions to be established can invoke
`report.require_preconditions()` before execution. This stricter opt-in policy
also blocks unresolved conditional assumptions; it is not a certificate of the
algorithm's implementation or of a successful run.

Model-definition checks identify the model implemented in code; they do not
establish that its assumptions describe a real market.

An evidence label is an audit record, not a formal theorem prover. In particular,
`analytic_argument` records a justification supplied by trusted component code; the
framework does not check its mathematical validity. Authoring or relabeling evidence
must not substitute for actually establishing the property.

## Future convex methods

For convex minimization, both the objective's convexity and the feasible set's
convexity matter. For maximization, the corresponding objective condition is
concavity. Algorithm-specific conditions such as differentiability, gradient
Lipschitz constants, step sizes, or strong convexity may also be necessary for a
particular convergence or uniqueness guarantee.

A future tool can declare those as required MethodRequirements:

```python
from simulation_core.contracts import MethodContract, MethodRequirement

contract = MethodContract(
    name="Future convex minimization method",
    requirements=(
        MethodRequirement(id="convex_objective", description="Objective is convex over the full domain"),
        MethodRequirement(id="convex_domain", description="The entire feasible set is convex"),
    ),
    guarantees=("Only the guarantee justified by the chosen algorithm and all its conditions",),
)
report = contract.assess()  # Both properties remain unverified.
# report.require_execution() raises until the required properties are established.
```

Use analytical structure, a valid mathematical derivation, or a suitable certified
procedure to establish a global property. Positive sampled Hessians, repeated runs,
or one successful optimizer call do not establish global convexity. A genuine
counterexample may refute it. The evidence schema rejects `verified` claims based
only on declarations or sampled tests.

New equilibrium solvers implement `_solve` and the requirement-evidence hook. The
shared public `Solver.solve` template enforces required preconditions, preserves
reports for expected evaluation failures, and attaches the report to results. Pure
mathematical tools can use MethodContract directly without inheriting Solver.

Use explicit validation and exceptions for enforcement. Python removes `assert`
statements under optimization; assertions are suitable for tests and debugging,
not required mathematical preconditions.
