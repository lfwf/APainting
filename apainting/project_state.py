from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_unit_order(unit_order: list[str], known_ids: list[str]) -> list[str]:
    if len(unit_order) != len(known_ids):
        raise ValueError("unit_order must contain every Drawing Unit exactly once")
    if len(unit_order) != len(set(unit_order)):
        raise ValueError("unit_order contains duplicates")
    missing = sorted(set(known_ids) - set(unit_order))
    unknown = sorted(set(unit_order) - set(known_ids))
    if missing or unknown:
        raise ValueError(f"invalid unit_order; missing={missing}, unknown={unknown}")
    return list(unit_order)


def load_playback_settings(run_dir: Path) -> dict[str, object]:
    path = run_dir / "playback_settings.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("playback_settings.json must be a JSON object")
    return data


def save_playback_settings(
    run_dir: Path,
    unit_order: list[str],
    *,
    source: str = "manual",
    note: str = "",
    archive: bool = True,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "version": 1,
        "updated_at": _now_iso(),
        "source": source,
        "note": note,
        "unit_order": list(unit_order),
    }
    path = run_dir / "playback_settings.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if archive:
        history_dir = run_dir / "history"
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        name = f"order_{stamp}_{uuid4().hex[:6]}.json"
        (history_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        payload["history_id"] = name
    return payload


def list_order_history(run_dir: Path) -> list[dict[str, object]]:
    history_dir = run_dir / "history"
    if not history_dir.exists():
        return []
    result: list[dict[str, object]] = []
    for path in sorted(history_dir.glob("order_*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        result.append(
            {
                "id": path.name,
                "updated_at": data.get("updated_at", ""),
                "source": data.get("source", ""),
                "note": data.get("note", ""),
                "unit_order": data.get("unit_order", []),
            }
        )
    return result


def load_history_snapshot(run_dir: Path, history_id: str) -> dict[str, object]:
    safe_name = Path(history_id).name
    if safe_name != history_id or not safe_name.startswith("order_") or not safe_name.endswith(".json"):
        raise ValueError("invalid history id")
    path = run_dir / "history" / safe_name
    if not path.exists():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("history snapshot must be a JSON object")
    return data
