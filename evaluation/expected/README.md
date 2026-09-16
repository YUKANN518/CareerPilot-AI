# Expected Labels

The first evaluation baseline uses the manually authored expected fields in the frozen backend
label source referenced by `dataset/manifest.json`. This directory reserves a stable namespace
for future independent expected snapshots; it is intentionally not a second copy that could drift
from the reviewed fixture labels.

The evaluator validates duplicate case IDs, fixture references, expected skill-state exclusivity
and required expected fields before running.

