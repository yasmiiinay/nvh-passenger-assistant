"""Every script must at least compile and import. Added after a syntax error
slipped into scripts/benchmark_env.py in a commit that changed only the
benchmark harness, which no test exercised."""
import importlib.util
import py_compile
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPTS = sorted((ROOT / "scripts").glob("*.py"))


@pytest.mark.parametrize("path", SCRIPTS, ids=[p.name for p in SCRIPTS])
def test_script_compiles_and_imports(path):
    py_compile.compile(str(path), doraise=True)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)          # scripts guard their work behind __main__
