# Choose the smallest execution model

An external coding agent first classifies what the user actually needs. The
request can pin `execution_kind` to `tool` or `agent_simulation`; `auto` lets the
agent explain its classification. Planning rejects a route that contradicts an
explicit user choice.

| Request | Route | Building blocks |
| --- | --- | --- |
| Gaussian elimination, a numerical transform, a pure optimizer | tool | Callable, input/output contracts, method assumptions when mathematical, tests |
| Auction bidders, negotiation, market participants making decisions | agent_simulation | Policies, authorized observations/private memory, protocol, mechanism, runtime, recording |
| Simulation requiring a missing mathematical helper | agent_simulation with helper | Existing simulation interfaces plus a small function; the benchmark stays separate |

A tool plan uses a ToolInvocation and no SimulationConfig. The isolated worker
validates/tests the bundle and invokes the callable with native argument data,
returning a ToolResult. It does not create actors or represent a lone optimizer as
a game merely to fit the simulation loop. Small helpers need no artificial class
hierarchy. Mathematical guarantees still require appropriate assumptions/evidence.

An agent simulation derives behavior from actor policies and their authorized
observations. The mathematical reference evaluates expected/ideal behavior;
it never supplies the actors' committed decisions. A simple mechanism still uses
the simulation interfaces if autonomous actor decisions are part of the question.
Its implementation can delegate calculations to ordinary functions.

## Next proposed experiment

`experiment_requests/second_price_auction.json` is an explicit agent-simulation
request with three private-value LLM bidders and a truthful-bidding reference.
The chosen textbook assumptions and illustrative inputs are stated in that
request; they are not defaults in the general coding-agent prompt. It requires
the Contributor actor model and gives the full Spark model only the coding role.
This request has not been run.

The current isolated extension worker is offline and cannot yet call live actor
models. A credential-isolated broker is a prerequisite for that trial. The new
structured `unsupported`/`needs_review` outcome lets the agent report this missing
capability instead of substituting scripted actors. The coding API transport and
the future actor broker are different capabilities.

The earlier simplex trial used a scripted actor. Its task was therefore an
extension-authoring/integration diagnostic, not an example of live LLM-agent
economic behavior. The fixture/test/serialization failures made that trial hard;
they do not show that projecting a vector onto a simplex is intrinsically hard
for the model. A math-only version should use the direct tool route.
