# Adding a model (outline, to be completed)

1. Write `cards/<model_id>.json` (inputs, outputs, run command, limits, supervision levels, validation test case).
   Mark anything not confirmed from the model's own documentation as `verify`.
2. Add Processing algorithms in `algorithms/` that inherit `EiaAlgorithm`, set `LEVEL`, and call
   `approval.require(...)` in `prepareAlgorithm` (main thread) for levels B and C.
3. Write to the audit log with `AuditLog(...).append(...)`.
4. Do not bundle binaries; add a path setting in `provider.py`.
5. A model counts as accepted only when the plugin reproduces the model's own test case.
