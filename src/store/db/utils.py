import json
import re
from typing import Any, Dict

_VALID_TABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def safe_json_loads(raw: str | None) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
        return {"value": obj}
    except Exception:
        return {"raw": str(raw)}
