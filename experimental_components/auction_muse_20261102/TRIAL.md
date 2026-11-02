# Muse Code second-price auction trial

**Completed with v1 on the first submitted implementation.** The coding agent
created the custom auction package, tests and notebook generator in Docker.
Real LLM bidders bid 90, 65 and 40; A paid 65 and earned 25, matching the truthful
reference. Twenty acceptance checks and 252 regression tests passed (one skipped).

- [Detailed report and independent findings](../../docs/auction_live_trial_20261102.md)
- [Executed notebook](../_runs/auction_muse_20261102/v1/dc51c9f6ee47418688ab60c2e6ff85b1/results.ipynb)
- [Result](../_runs/auction_muse_20261102/v1/dc51c9f6ee47418688ab60c2e6ff85b1/result.json)
- [Receipt](../_runs/auction_muse_20261102/v1/dc51c9f6ee47418688ab60c2e6ff85b1.json)
- [Agent-written implementation](v1/experiment_extension/auction.py)
- [Frozen tests](v1/tests)
- [Configuration and user request](v1/job.example.json)

The operator supplied the user details and general CLI/actor-relay infrastructure,
not the auction implementation. Muse Code used the full coding model at max
reasoning; bidders used the separate Contributor model. No past experiment bundles
were available to the CLI. Its two authoring stages used 112 provider calls in
total; the simulation used six calls including acceptance integration.

Independent review passed ten extra settlement cases but demonstrated checker
identity/oracle weaknesses, a notebook field-alias failure and an ignored option.
These findings and the substantial authoring overhead are documented in the full
report. They were not repaired in the completed sealed v1.

Bundle seal:
`596c1d51694e960fa6fb4ebae7fcc4a116203d4d490f63822be693e254d3d496`

Raw authoring traces and independent probe results are retained locally under
`experimental_components/_authoring/auction_muse_20261102/`. Outputs/logs are
ignored by Git under the existing private-retention convention; this report and
the versioned source bundle are trackable.
