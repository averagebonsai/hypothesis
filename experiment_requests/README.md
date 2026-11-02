# Fresh experiment requests

`allocation.json` contains only the user problem and supplied inputs for the next
allocation trial. It contains no prior implementation, optimum, payoff result,
validation feedback or experiment-history path. It is input data, not an executed
experiment. No model or simulation is started by loading it.

Use a new experiment ID, bundle directory and authoring audit for the next run.
The coding model receives this request, the general blind prompt and the curated
toolkit inventory. It receives neither this README nor existing experimental
bundles. See [the preparation guide](../docs/authoring_preparation.md).
