"""Small compatibility wrapper around Python's standard json module.

The collector asks the model for strict JSON. Lower-cost models can sometimes
wrap the JSON object with a short explanation, which made the scheduled Action
fail before the dashboard could be rebuilt. This wrapper keeps normal json
behavior, but retries ``loads`` after extracting the first JSON object.
"""

from __future__ import annotations

import importlib.util
import sys
import sysconfig
from pathlib import Path
from typing import Any


_stdlib_json_dir = Path(sysconfig.get_paths()["stdlib"]) / "json"
_spec = importlib.util.spec_from_file_location(
    "_opportunity_radar_stdlib_json",
    _stdlib_json_dir / "__init__.py",
    submodule_search_locations=[str(_stdlib_json_dir)],
)
if _spec is None or _spec.loader is None:
    raise ImportError("Could not load Python standard-library json module")

_stdlib_json = importlib.util.module_from_spec(_spec)
_wrapper_json = sys.modules[__name__]
sys.modules[_spec.name] = _stdlib_json
sys.modules[__name__] = _stdlib_json
try:
    _spec.loader.exec_module(_stdlib_json)
finally:
    sys.modules[__name__] = _wrapper_json

JSONDecodeError = _stdlib_json.JSONDecodeError
JSONDecoder = _stdlib_json.JSONDecoder


def _extract_json_payload(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    decoder = _stdlib_json.JSONDecoder()
    for index, char in enumerate(stripped):
        if char != "{":
            continue
        try:
            _, end = decoder.raw_decode(stripped[index:])
        except _stdlib_json.JSONDecodeError:
            continue
        return stripped[index : index + end]
    return stripped


def loads(value: str | bytes | bytearray, *args: Any, **kwargs: Any) -> Any:
    if isinstance(value, str):
        try:
            return _stdlib_json.loads(value, *args, **kwargs)
        except _stdlib_json.JSONDecodeError:
            return _stdlib_json.loads(_extract_json_payload(value), *args, **kwargs)
    return _stdlib_json.loads(value, *args, **kwargs)


def dumps(*args: Any, **kwargs: Any) -> str:
    return _stdlib_json.dumps(*args, **kwargs)


def dump(*args: Any, **kwargs: Any) -> Any:
    return _stdlib_json.dump(*args, **kwargs)


def load(*args: Any, **kwargs: Any) -> Any:
    return _stdlib_json.load(*args, **kwargs)


def __getattr__(name: str) -> Any:
    return getattr(_stdlib_json, name)
