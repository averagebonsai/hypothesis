# Explanatory simulation notebooks

New simulation plans declare `NotebookSpec.report_version="explanatory.v1"`.
Existing sealed bundles and legacy notebook generators remain readable; they do
not silently acquire a new acceptance contract.

Use `simulation_core.reports.write_experiment_notebook(artifact, directory,
narrative, references=(), figures=())`. Domain code supplies `ReportNarrative`,
optional calculated `ReportReference` data and optional `ReportFigure`/`ChartSeries`
data. These models contain no experiment-specific rules or outcome defaults.
References can describe scalar or vector actions, payoffs, multiple solutions and
explicit source ticks; absent ticks refer to each actor's final recorded decision.

The writer provides:

1. **Experiment background and rationale:** concepts, question, participants,
   rules, information and why this is an informative experiment.
2. **Execution and results:** brief calls to external rendering code, one result
   table, relevant figures, comparisons and plain-language interpretation.
3. **Decision rationales:** each original actor/turn explanation once, clearly
   described as a reported explanation rather than independent causal evidence.
4. **Assumptions:** substantive modeled conditions in prose/bullets, with user,
   textbook or inferred sources explained where useful. Machine configuration
   paths and JSON dumps remain in provenance files.
5. **Limitations:** scope, sample size, uncertainty and conclusions not supported.

The notebook/result pair is self-contained. Typed report data is stored in notebook
metadata and bound to the canonical serialized result by SHA-256. Notebook cells
load the saved result and call shared external rendering helpers. They contain no
domain settlement/optimization logic and make no policy or model calls. Calculating
a new reference remains the responsibility of experiment code outside the cells.

The worker executes notebooks offline and checks the five sections, their order,
unique result/rationale displays, normal-text presentation, recorded rationale
coverage and result binding. These checks establish structure and provenance,
not pedagogical quality or mathematical independence. The reviewer must also ask:

- Can a reader unfamiliar with the domain explain the rules and terms afterward?
- Does the interpretation follow the recorded results, including disagreements?
- Is the benchmark's meaning and applicability clear without claiming uniqueness
  or a general behavioral law from one sample?
- Are tables/charts useful rather than repeated dumps of the same data?
- Are actor explanations distinguished from analyst conclusions?
- Are assumptions and limitations substantive and understandable?

The runtime's trusted observation checker separately compares built-in `llm.v1`
requests against their canonical precommit state, including identity, permissions,
public/private facts and memory. Custom policy request formats remain outside that
check's advertised scope. A domain checker sharing its calculation with execution
is a consistency check; independent mathematical claims need separate evidence.

New plans also declare `preview_generator: (JobManifest, Path) -> Path`. Use
`ReportPreview` and `write_preview_notebook(directory, preview)` for configuration-only
problem definition, mathematical benchmark/theory, assumptions and limitations.
The separate offline preview worker has no actor relay and cannot receive a
`JobResult`; observed results, rationales and their interpretation stay explicitly
pending. No invented LLM performance belongs in the preview. Final performance
explanations must use the subsequently recorded artifact. See
[authoring workflow](authoring_workflow.md) for CLI examples and provenance rules.
