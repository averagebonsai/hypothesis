# Experimental vector allocation v1

Retained experiment bundle; not part of the approved global library.

One actor chooses a nonnegative vector summing to 10. Its score is minus squared
distance to target (8,6). The offline scripted fixture chooses (5,5), score -10;
the analytical optimum is (6,4), score -8. These are illustrative values, not
empirical findings or live LLM behavior. A single-actor Nash optimum is simply
that actor's own optimum.

Read bundle.json for the gap analysis, typed schemas, assumptions, and acceptance
criteria. Import and execute only through the isolated worker. Never run these
tests on the host controller. job.example.json is a checked-in input fixture;
per-run transport manifests are temporary. Seal only after reviewing tests and
source. A changed sealed version requires a new version, not an overwritten seal.

See docs/experimental_workflow.md in the main project for commands.
