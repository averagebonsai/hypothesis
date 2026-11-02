# Isolated vector-allocation trial

The external-agent bundle passed Ruff, mypy against the installed typed toolkit,
six acceptance/framework integration tests, 207 framework regressions (one live
test skipped), declared-test coverage, and composition preflight. All code imports,
tests, and simulation execution occurred in a restricted Docker container inside
the mountless hypothesis-worker Docker sbx sandbox.

| Result | Allocation | Score |
|---|---|---:|
| Scripted primary fixture | (5,5) | -10 |
| Separate analytical benchmark | (6,4) | -8 |

Possible improvement: 2. These are illustrative deterministic results, not live
LLM actions. No API keys were passed to the worker. The primary choice was not
overwritten by the benchmark.

Bundle: v1, digest `eb7af6a48d1cb0f2a962f8d7b212d3b99ff19a59ed6862c8d00e2d05d6ba6ce5`.

Worker image: `sha256:7d4db57e9a544f5cefba8d3ea5aaf86213f1e2bdfb4a582949df7a9e2345bd9c`.

Trusted framework/dependency digest: `94b5219f155bed4eed33ca42cf5197ca55ef9d608353716760cde6535e7d6c23`.

Resource limits: `{"wall_seconds":180,"memory_mb":2048,"cpus":2,"pids":128,"output_bytes":4000000}`.

Full local receipt: [validation and result](../_runs/vector_allocation/v1/2c535406ee154fac9386172db0975fc2.json).
Receipts remain local and ignored by Git because other experiments may contain
private state. Earlier failed harness-validation receipts are retained as well.

The pilot exposed two framework packaging issues: inconsistent import
classification across working directories, and missing installed-package
py.typed markers. Both were corrected in the trusted harness. The sealed v1
source and acceptance criteria remained unchanged throughout these checks.


Documentation amendment: the v1 README was subsequently expanded at the user's
request. The original tested README and seal were archived, and a documentation-only
amendment was recorded. This trial's receipt and digest still identify the original
tested bytes. See [the amendment record](provenance/v1-readme-report-amendment.json)
and the provenance section in [the current v1 report](v1/README.md). Implementation,
acceptance tests, specification and input fixture were not changed.
