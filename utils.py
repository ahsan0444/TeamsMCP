from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
from config import settings


def format_tools_for_prompt(tools: List[Any]) -> str:
    """Return a clean, comma-separated list of tool names for LLM prompts.
    Accepts strings or dicts and is resilient to mixed input.
    """
    if not tools:
        return "(none)"
    names: List[str] = []
    for t in tools:
        if isinstance(t, str):
            names.append(t)
        elif isinstance(t, dict):
            name = t.get("name") or t.get("tool") or t.get("id") or "unknown"
            names.append(str(name))
        else:
            try:
                names.append(str(t))
            except Exception:
                names.append("unknown")
    return ", ".join(names)


def pick_base_url() -> str:
    """Pick the best available base URL from config settings."""
    candidates = [
        getattr(settings, "BASE_URL", ""),
        getattr(settings, "base_url", ""),
        getattr(settings, "login_base_url", ""),
        getattr(settings, "APP_BASE_URL", ""),
    ]
    for b in candidates:
        if b:
            return b
    return ""


def absolutize_url(item_url: Optional[str], base: Optional[str]) -> str:
    """Return an absolute URL. If `item_url` is relative, join with `base`.
    If `base` is not available, best-effort return an http:// URL.
    """
    if not item_url:
        return ""
    iu = item_url.strip()
    if iu.startswith("http://") or iu.startswith("https://"):
        return iu
    b = (base or "").strip()
    if not b:
        # Fallback: if item_url looks like a host/path, prefix http
        if iu and not iu.startswith("http"):
            return "http://" + iu
        return iu
    if not b.endswith("/"):
        b = b + "/"
    return urljoin(b, iu.lstrip("/"))


def normalize_data(obj: Any) -> Any:
    """Normalize common response wrappers (data, response, result) for easier consumption."""
    if isinstance(obj, dict):
        if "data" in obj and isinstance(obj["data"], (dict, list)):
            return obj["data"]
        if "response" in obj and isinstance(obj["response"], (dict, list)):
            return obj["response"]
        if "result" in obj and isinstance(obj["result"], (dict, list)):
            return obj["result"]
        return obj
    return obj


def find_task_in_payload(obj: Any) -> Optional[Dict[str, Any]]:
    """Search a nested payload for a task-like dict with id/title/url fields."""
    def inner(o: Any) -> Optional[Dict[str, Any]]:
        if isinstance(o, dict):
            if ("id" in o and ("text" in o or "title" in o or "item_url" in o or "itemUrl" in o)) or (
                "planning_number" in o and "id" in o
            ):
                return o
            for v in o.values():
                found = inner(v)
                if found:
                    return found
        elif isinstance(o, list):
            for item in o:
                found = inner(item)
                if found:
                    return found
        return None

    return inner(obj)