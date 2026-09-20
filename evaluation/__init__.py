"""Evaluation harness. Structure created at the foundation stage.

Design rules (Architecture Freeze v1.1, Evidence Pack 02B2):
- every metric function takes plain Python/CSV-ready inputs and returns a dict,
  so results are testable without any model in memory;
- every module has one `write_artifacts()` that persists its tables to
  outputs/evaluation/ as CSV/JSON -- the report only ever cites those files;
- no function here fabricates data: anything needing model output raises
  NotImplementedError until the pipeline phase wires it in.
"""
