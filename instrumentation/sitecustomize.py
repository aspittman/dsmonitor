"""Opt-in metering for engine subprocesses started by the configured launchers."""
import importlib.util
from pathlib import Path
import sys

try:
    path = Path(__file__).resolve().parents[1] / 'ds_usage.py'
    spec = importlib.util.spec_from_file_location('ds_usage', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules['ds_usage'] = module
    spec.loader.exec_module(module)
    module.install()
except Exception:
    pass
