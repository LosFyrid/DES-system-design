"""
History inspection and notebook tools used by the feedback experience extractor.

These tools are deliberately plain Python callables. They make the extractor
agentic without coupling it to a specific LLM tool-calling API: an LLM can
choose actions in a ReAct loop, while local code executes bounded history reads
and in-session notebook writes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .experience_analysis import (
    extract_formulation_components,
    summarize_measurements,
)
from .memory import MemoryItem, MemoryQuery, Trajectory
from ..utils.formulation_signature import (
    normalize_component_name,
    normalize_material_name,
    normalize_temperature_C,
)
from ..utils.formulation_validation import summarize_formulation
from ..utils.serialization import to_jsonable


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _as_dict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        try:
            out = obj.to_dict()
            return out if isinstance(out, dict) else {}
        except Exception:
            return {}
    if hasattr(obj, "model_dump"):
        try:
            out = obj.model_dump()
            return out if isinstance(out, dict) else {}
        except Exception:
            return {}
    try:
        out = dict(obj)  # type: ignore[arg-type]
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


def _clip_text(value: Any, max_chars: int = 800) -> str:
    text = "" if value is None else str(value)
    max_chars = max(20, int(max_chars or 800))
    if len(text) <= max_chars:
        return text
    suffix = f"... <truncated {len(text) - max_chars} chars>"
    return text[: max(0, max_chars - len(suffix))] + suffix


def _clip_text_with_flag(value: Any, max_chars: int = 800) -> Tuple[str, bool]:
    text = "" if value is None else str(value)
    clipped = _clip_text(text, max_chars)
    return clipped, clipped != text


def _compact_value(
    value: Any,
    *,
    max_string: int = 800,
    max_items: int = 12,
    max_depth: int = 5,
    _depth: int = 0,
) -> Any:
    """Bound nested values before JSON serialization so prompts stay valid."""
    value = to_jsonable(value)
    if _depth >= max_depth:
        if isinstance(value, (dict, list)):
            return _clip_text(json.dumps(value, ensure_ascii=False, sort_keys=True), max_string)
        if isinstance(value, str):
            return _clip_text(value, max_string)
        return value

    if isinstance(value, str):
        return _clip_text(value, max_string)
    if isinstance(value, list):
        limited = [
            _compact_value(
                item,
                max_string=max_string,
                max_items=max_items,
                max_depth=max_depth,
                _depth=_depth + 1,
            )
            for item in value[:max_items]
        ]
        if len(value) > max_items:
            limited.append({"truncated_items": len(value) - max_items})
        return limited
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                out["truncated_keys"] = len(value) - max_items
                break
            out[str(key)] = _compact_value(
                item,
                max_string=max_string,
                max_items=max_items,
                max_depth=max_depth,
                _depth=_depth + 1,
            )
        return out
    return value


def _memory_to_tool_row(memory: MemoryItem, *, score: Optional[float] = None) -> Dict[str, Any]:
    row = {
        "title": memory.title,
        "description": memory.description,
        "content": memory.content,
        "source_task_id": memory.source_task_id,
        "created_at": memory.created_at,
        "is_from_success": memory.is_from_success,
        "metadata": to_jsonable(memory.metadata or {}),
    }
    if score is not None:
        row["score"] = round(float(score), 4)
    return row


def _item_ref(kind: str, row: Dict[str, Any]) -> str:
    if kind == "recommendation":
        return f"recommendation:{row.get('recommendation_id') or ''}"
    return f"memory:{row.get('source_task_id') or ''}:{row.get('title') or ''}"


def _compact_memory_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    metadata = metadata if isinstance(metadata, dict) else {}
    keep = [
        "source",
        "target_material",
        "recommendation_id",
        "performance_band",
        "relative_interpretation",
        "is_positive_signal",
        "memory_kind",
        "evidence_strength",
        "component_implications",
        "source_evidence",
        "avoid_absolute_language",
    ]
    out = {
        key: _compact_value(metadata.get(key), max_string=500, max_items=8, max_depth=4)
        for key in keep
        if key in metadata
    }
    profile = metadata.get("extractor_profile")
    if isinstance(profile, dict):
        profile_keep = [
            "formulation_components_norm",
            "performance_profile",
            "recommendation_implications",
            "condition_context",
        ]
        out["extractor_profile"] = {
            key: _compact_value(profile.get(key), max_string=500, max_items=8, max_depth=4)
            for key in profile_keep
            if key in profile
        }
    return out


def _memory_to_compact_tool_row(
    row: Dict[str, Any],
    *,
    number: int,
) -> Dict[str, Any]:
    item = {
        "item_number": number,
        "item_ref": _item_ref("memory", row),
        "kind": "memory",
        "title": row.get("title"),
        "description": _clip_text(row.get("description"), 500),
        "content_excerpt": _clip_text(row.get("content"), 700),
        "source_task_id": row.get("source_task_id"),
        "created_at": row.get("created_at"),
        "is_from_success": row.get("is_from_success"),
        "metadata": _compact_memory_metadata(row.get("metadata") or {}),
    }
    if row.get("score") is not None:
        item["score"] = row.get("score")
    return item


def _path_values(obj: Any, field: str) -> List[Any]:
    """Resolve dotted paths across dict/object/list structures."""
    parts = [p for p in str(field or "").strip().split(".") if p]
    if not parts:
        return [obj]

    def walk(value: Any, remaining: List[str]) -> List[Any]:
        if not remaining:
            return [value]
        if value is None:
            return []
        if isinstance(value, list):
            out: List[Any] = []
            for item in value:
                out.extend(walk(item, remaining))
            return out

        head = remaining[0]
        tail = remaining[1:]
        if isinstance(value, dict):
            if head not in value:
                return []
            return walk(value.get(head), tail)
        if hasattr(value, head):
            return walk(getattr(value, head), tail)
        return []

    return walk(obj, parts)


def _first_path_value(obj: Any, field: str) -> Any:
    values = _path_values(obj, field)
    return values[0] if values else None


def _parse_scalar(raw: str) -> Any:
    text = str(raw or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none"}:
        return None
    try:
        if re.search(r"[.eE]", text):
            return float(text)
        return int(text)
    except Exception:
        return text


def _split_csv_like(raw: str) -> List[Any]:
    values: List[str] = []
    buf: List[str] = []
    quote: Optional[str] = None
    for ch in raw:
        if ch in {"'", '"'}:
            quote = None if quote == ch else (ch if quote is None else quote)
            buf.append(ch)
            continue
        if ch == "," and quote is None:
            values.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    if buf:
        values.append("".join(buf).strip())
    return [_parse_scalar(v) for v in values if str(v).strip()]


def _split_where_and(where: str) -> List[str]:
    clauses: List[str] = []
    buf: List[str] = []
    quote: Optional[str] = None
    depth = 0
    i = 0
    text = str(where or "").strip()
    while i < len(text):
        ch = text[i]
        if ch in {"'", '"'}:
            quote = None if quote == ch else (ch if quote is None else quote)
            buf.append(ch)
            i += 1
            continue
        if quote is None:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            if depth == 0 and text[i : i + 5].lower() == " and ":
                clause = "".join(buf).strip()
                if clause:
                    clauses.append(clause)
                buf = []
                i += 5
                continue
        buf.append(ch)
        i += 1
    clause = "".join(buf).strip()
    if clause:
        clauses.append(clause)
    return clauses


def _stringify_for_match(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _compare_values(actual: Any, op: str, expected: Any) -> bool:
    if op in {"exists", "is not null"}:
        return actual is not None
    if op in {"missing", "is null"}:
        return actual is None

    if op == "contains":
        if isinstance(actual, list):
            return any(_compare_values(item, "contains", expected) for item in actual)
        return str(expected).lower() in _stringify_for_match(actual).lower()

    if op == "like":
        pattern = re.escape(str(expected)).replace("%", ".*")
        return re.search(f"^{pattern}$", _stringify_for_match(actual), flags=re.IGNORECASE) is not None

    if op in {"in", "not in"}:
        expected_values = expected if isinstance(expected, list) else [expected]
        actual_values = actual if isinstance(actual, list) else [actual]
        matched = any(
            str(a).lower() == str(e).lower()
            for a in actual_values
            for e in expected_values
        )
        return not matched if op == "not in" else matched

    if op in {"=", "!="}:
        matched = str(actual).lower() == str(expected).lower()
        return not matched if op == "!=" else matched

    actual_num = _safe_float(actual)
    expected_num = _safe_float(expected)
    if actual_num is None or expected_num is None:
        return False
    if op == ">":
        return actual_num > expected_num
    if op == ">=":
        return actual_num >= expected_num
    if op == "<":
        return actual_num < expected_num
    if op == "<=":
        return actual_num <= expected_num
    return False


def _parse_where_clause(clause: str) -> Tuple[str, str, Any]:
    text = str(clause or "").strip()
    if not text:
        raise ValueError("empty where clause")

    m = re.match(r"^exists\s*\(\s*([A-Za-z0-9_.]+)\s*\)$", text, flags=re.I)
    if m:
        return m.group(1), "exists", None

    m = re.match(r"^([A-Za-z0-9_.]+)\s+is\s+(not\s+)?null$", text, flags=re.I)
    if m:
        return m.group(1), "is not null" if m.group(2) else "is null", None

    m = re.match(r"^([A-Za-z0-9_.]+)\s+(not\s+in|in)\s*\((.*)\)$", text, flags=re.I)
    if m:
        return m.group(1), m.group(2).lower(), _split_csv_like(m.group(3))

    m = re.match(r"^([A-Za-z0-9_.]+)\s+(contains|like)\s+(.+)$", text, flags=re.I)
    if m:
        return m.group(1), m.group(2).lower(), _parse_scalar(m.group(3))

    m = re.match(r"^([A-Za-z0-9_.]+)\s*(>=|<=|!=|=|>|<)\s*(.+)$", text, flags=re.I)
    if m:
        return m.group(1), m.group(2), _parse_scalar(m.group(3))

    raise ValueError(f"unsupported where clause: {text}")


def _matches_where(row: Dict[str, Any], where: str) -> bool:
    where = str(where or "").strip()
    if not where:
        return True
    for clause in _split_where_and(where):
        field, op, expected = _parse_where_clause(clause)
        values = _path_values(row, field)
        if op in {"missing", "is null"} and not values:
            continue
        if not values:
            return False
        if not any(_compare_values(value, op, expected) for value in values):
            return False
    return True


def _sort_rows(rows: List[Dict[str, Any]], order_by: str) -> List[Dict[str, Any]]:
    order_by = str(order_by or "").strip()
    if not order_by:
        return rows
    reverse = order_by.startswith("-")
    field = order_by[1:] if reverse else order_by
    return sorted(
        rows,
        key=lambda row: (
            _first_path_value(row, field) is None,
            _stringify_for_match(_first_path_value(row, field)),
        ),
        reverse=reverse,
    )


def _distinct_field_values(rows: Iterable[Dict[str, Any]], field: str, limit: int) -> List[Dict[str, Any]]:
    counts: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        for value in _path_values(row, field):
            if isinstance(value, (dict, list)):
                key = json.dumps(value, ensure_ascii=False, sort_keys=True)
                display = value
            else:
                key = str(value)
                display = value
            if key not in counts:
                counts[key] = {"value": display, "count": 0}
            counts[key]["count"] += 1
    values = sorted(counts.values(), key=lambda item: (-int(item["count"]), str(item["value"])))
    return values[: max(1, min(int(limit or 50), 200))]


def _recommendation_to_tool_row(rec: Any, *, include_experiment: bool = True) -> Dict[str, Any]:
    exp = getattr(rec, "experiment_result", None)
    formulation = getattr(rec, "formulation", {}) or {}
    task = getattr(rec, "task", {}) or {}
    row = {
        "recommendation_id": getattr(rec, "recommendation_id", None),
        "task_id": getattr(rec, "task_id", None),
        "status": getattr(rec, "status", None),
        "created_at": getattr(rec, "created_at", None),
        "updated_at": getattr(rec, "updated_at", None),
        "target_material": task.get("target_material"),
        "target_temperature": task.get("target_temperature"),
        "formulation": formulation,
        "formulation_summary": summarize_formulation(formulation),
        "components": extract_formulation_components(formulation),
        "confidence": getattr(rec, "confidence", None),
    }
    if include_experiment and exp is not None:
        row["experiment"] = {
            "is_liquid_formed": bool(getattr(exp, "is_liquid_formed", False)),
            "conditions": _as_dict(getattr(exp, "conditions", {}) or {}),
            "measurement_stats": summarize_measurements(getattr(exp, "measurements", []) or []),
            "experiment_date": getattr(exp, "experiment_date", None),
        }
    return row


def _recommendation_performance_band(row: Dict[str, Any], config: Dict[str, Any]) -> str:
    extractor_cfg = config.get("extractor", {}) if isinstance(config, dict) else {}
    low = float(extractor_cfg.get("low_performance_percent", 20.0))
    high = float(extractor_cfg.get("high_performance_percent", 60.0))
    stats = ((row.get("experiment") or {}).get("measurement_stats") or {})
    max_value = _safe_float(stats.get("max_value"))
    is_liquid = bool((row.get("experiment") or {}).get("is_liquid_formed"))
    if not is_liquid:
        return "no_liquid"
    if max_value is None:
        return "formation_only"
    if max_value >= high:
        return "high"
    if max_value < low:
        return "low"
    return "moderate"


def _recommendation_to_compact_tool_row(
    row: Dict[str, Any],
    *,
    number: int,
) -> Dict[str, Any]:
    experiment = row.get("experiment") if isinstance(row.get("experiment"), dict) else {}
    return {
        "item_number": number,
        "item_ref": _item_ref("recommendation", row),
        "kind": "recommendation",
        "recommendation_id": row.get("recommendation_id"),
        "task_id": row.get("task_id"),
        "status": row.get("status"),
        "created_at": row.get("created_at"),
        "target_material": row.get("target_material"),
        "target_temperature": row.get("target_temperature"),
        "formulation_summary": _clip_text(row.get("formulation_summary"), 700),
        "components": _compact_value(row.get("components") or [], max_string=300, max_items=12, max_depth=3),
        "confidence": row.get("confidence"),
        "performance_band": row.get("performance_band"),
        "experiment": {
            "is_liquid_formed": experiment.get("is_liquid_formed"),
            "measurement_stats": _compact_value(
                experiment.get("measurement_stats") or {},
                max_string=400,
                max_items=12,
                max_depth=3,
            ),
            "experiment_date": experiment.get("experiment_date"),
        } if experiment else None,
    }


def _notebook_entry_from_row(
    *,
    kind: str,
    row: Dict[str, Any],
    source_tool: str,
    result_set_id: str,
    item_number: int,
    note: str = "",
) -> Dict[str, Any]:
    if kind == "recommendation":
        structured = _recommendation_to_compact_tool_row(row, number=item_number)
        raw = {
            "recommendation_id": row.get("recommendation_id"),
            "task_id": row.get("task_id"),
            "status": row.get("status"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "target_material": row.get("target_material"),
            "target_temperature": row.get("target_temperature"),
            "formulation": _compact_value(row.get("formulation") or {}, max_string=1000, max_items=20, max_depth=6),
            "formulation_summary": _clip_text(row.get("formulation_summary"), 1200),
            "components": _compact_value(row.get("components") or [], max_string=600, max_items=20, max_depth=5),
            "confidence": row.get("confidence"),
            "performance_band": row.get("performance_band"),
            "experiment": _compact_value(row.get("experiment") or {}, max_string=1000, max_items=20, max_depth=6),
        }
    else:
        structured = _memory_to_compact_tool_row(row, number=item_number)
        raw = {
            "title": row.get("title"),
            "description": _clip_text(row.get("description"), 1200),
            "content": _clip_text(row.get("content"), 2000),
            "source_task_id": row.get("source_task_id"),
            "created_at": row.get("created_at"),
            "is_from_success": row.get("is_from_success"),
            "metadata": _compact_value(row.get("metadata") or {}, max_string=1000, max_items=20, max_depth=6),
        }
        if row.get("score") is not None:
            raw["score"] = row.get("score")

    return {
        "entry_type": "evidence_item",
        "kind": kind,
        "source_tool": source_tool,
        "result_set_id": result_set_id,
        "item_number": item_number,
        "item_ref": _item_ref(kind, row),
        "model_note": _clip_text(note, 700),
        "structured_summary": structured,
        "evidence": raw,
    }


def _memory_raw_view(row: Dict[str, Any]) -> Dict[str, Any]:
    content, content_truncated = _clip_text_with_flag(row.get("content"), 6000)
    description, description_truncated = _clip_text_with_flag(row.get("description"), 2000)
    metadata = row.get("metadata") or {}
    metadata_text = json.dumps(to_jsonable(metadata), ensure_ascii=False, sort_keys=True, indent=2)
    metadata_view, metadata_truncated = _clip_text_with_flag(metadata_text, 8000)
    out = {
        "kind": "memory",
        "item_ref": _item_ref("memory", row),
        "title": row.get("title"),
        "description": description,
        "description_truncated": description_truncated,
        "content": content,
        "content_truncated": content_truncated,
        "source_task_id": row.get("source_task_id"),
        "created_at": row.get("created_at"),
        "is_from_success": row.get("is_from_success"),
        "metadata_json": metadata_view,
        "metadata_truncated": metadata_truncated,
    }
    if row.get("score") is not None:
        out["score"] = row.get("score")
    return out


def _recommendation_raw_view(row: Dict[str, Any]) -> Dict[str, Any]:
    formulation_text = json.dumps(to_jsonable(row.get("formulation") or {}), ensure_ascii=False, sort_keys=True, indent=2)
    experiment_text = json.dumps(to_jsonable(row.get("experiment") or {}), ensure_ascii=False, sort_keys=True, indent=2)
    formulation_view, formulation_truncated = _clip_text_with_flag(formulation_text, 8000)
    experiment_view, experiment_truncated = _clip_text_with_flag(experiment_text, 8000)
    summary, summary_truncated = _clip_text_with_flag(row.get("formulation_summary"), 3000)
    return {
        "kind": "recommendation",
        "item_ref": _item_ref("recommendation", row),
        "recommendation_id": row.get("recommendation_id"),
        "task_id": row.get("task_id"),
        "status": row.get("status"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "target_material": row.get("target_material"),
        "target_temperature": row.get("target_temperature"),
        "formulation_summary": summary,
        "formulation_summary_truncated": summary_truncated,
        "formulation_json": formulation_view,
        "formulation_truncated": formulation_truncated,
        "components": _compact_value(row.get("components") or [], max_string=800, max_items=30, max_depth=5),
        "confidence": row.get("confidence"),
        "performance_band": row.get("performance_band"),
        "experiment_json": experiment_view,
        "experiment_truncated": experiment_truncated,
    }


@dataclass
class ExperienceHistoryTools:
    memory_bank: Any
    retriever: Any
    rec_manager: Any
    config: Dict[str, Any]
    _result_set_counter: int = dataclass_field(default=0, init=False, repr=False)
    _result_sets: Dict[str, Dict[str, Any]] = dataclass_field(default_factory=dict, init=False, repr=False)
    _last_result_set_id: str = dataclass_field(default="", init=False, repr=False)
    _notebook_entries: List[Dict[str, Any]] = dataclass_field(default_factory=list, init=False, repr=False)
    _notebook_refs: set[str] = dataclass_field(default_factory=set, init=False, repr=False)

    def tool_specs_text(self) -> str:
        """Human-readable tool list for the extractor ReAct prompt."""
        return """Available tools:
- search_similar_memories: semantic embedding search over existing ReasoningBank memories by natural-language query text. Returns compact numbered items plus result_set_id.
- search_memories: structured filter search over memory fields using a SQL-like WHERE string. Supports AND, =, !=, >, >=, <, <=, IN (...), CONTAINS, LIKE, IS NULL, IS NOT NULL, and exists(field). Example fields: title, source_task_id, is_from_success, metadata.performance_band, metadata.relative_interpretation, metadata.extractor_profile.formulation_components_norm. Returns compact numbered items plus result_set_id.
- list_memory_field_values: list distinct values and counts for one memory field so you can choose valid filter values before calling search_memories.
- search_recommendations: structured search over historical recommendations/experiments. Use scope='comparable' for same material/temperature candidates or scope='all' for global history. Supports component, performance_band, include_pending, and SQL-like WHERE filtering. Returns compact numbered items plus result_set_id.
- list_recommendation_field_values: list distinct values and counts for one recommendation field so you can choose valid filter values before calling search_recommendations.
- inspect_item: view one raw historical item. Pass item_ref from a numbered result, such as memory:<source_task_id>:<title> or recommendation:<recommendation_id>. Returns one numbered item in a new result_set_id.
- inspect_recommendation: view one raw historical recommendation by recommendation_id. Prefer inspect_item when you already have item_ref.
- notebook_add_items: write selected numbered items from a result_set_id into the evidence notebook. You choose item_numbers; program copies the corresponding item evidence.
- notebook_add_note: append a natural-language note to the evidence notebook.
- notebook_view: inspect the notebook summary.
- finish: produce the final JSON memory extraction payload using only the notebook and current experiment.
"""

    def run(self, name: str, args: Dict[str, Any], *, trajectory: Trajectory, experiment_result: Any) -> Dict[str, Any]:
        args = args if isinstance(args, dict) else {}
        if name == "search_similar_memories":
            return self.search_similar_memories(
                query=str(args.get("query") or ""),
                top_k=int(args.get("top_k") or 5),
                where=str(args.get("where") or ""),
            )
        if name == "search_memories":
            return self.search_memories(
                where=str(args.get("where") or ""),
                limit=int(args.get("limit") or 20),
                order_by=str(args.get("order_by") or "-created_at"),
            )
        if name == "list_memory_field_values":
            return self.list_memory_field_values(
                field=str(args.get("field") or ""),
                where=str(args.get("where") or ""),
                limit=int(args.get("limit") or 50),
            )
        if name == "search_recommendations":
            return self.search_recommendations(
                trajectory=trajectory,
                experiment_result=experiment_result,
                component=str(args.get("component") or "").strip() or None,
                performance_band=str(args.get("performance_band") or "").strip() or None,
                include_pending=bool(args.get("include_pending", False)),
                limit=int(args.get("limit") or 8),
                where=str(args.get("where") or ""),
                order_by=str(args.get("order_by") or "-created_at"),
                scope=str(args.get("scope") or "comparable"),
            )
        if name == "list_recommendation_field_values":
            return self.list_recommendation_field_values(
                trajectory=trajectory,
                experiment_result=experiment_result,
                field=str(args.get("field") or ""),
                where=str(args.get("where") or ""),
                include_pending=bool(args.get("include_pending", False)),
                limit=int(args.get("limit") or 50),
                scope=str(args.get("scope") or "comparable"),
            )
        if name == "inspect_recommendation":
            return self.inspect_recommendation(str(args.get("recommendation_id") or ""))
        if name == "inspect_item":
            return self.inspect_item(str(args.get("item_ref") or ""))
        if name == "notebook_add_items":
            return self.notebook_add_items(
                result_set_id=str(args.get("result_set_id") or ""),
                item_numbers=args.get("item_numbers") if isinstance(args.get("item_numbers"), list) else [],
                note=str(args.get("note") or ""),
            )
        if name == "notebook_add_note":
            return self.notebook_add_note(str(args.get("note") or ""))
        if name == "notebook_view":
            return self.notebook_view()
        return {"ok": False, "error": f"unknown tool: {name}"}

    @property
    def notebook_entries(self) -> List[Dict[str, Any]]:
        return list(self._notebook_entries)

    def notebook_payload(self) -> Dict[str, Any]:
        evidence = [
            entry
            for entry in self._notebook_entries
            if entry.get("entry_type") == "evidence_item"
        ]
        notes = [
            entry
            for entry in self._notebook_entries
            if entry.get("entry_type") == "note"
        ]
        return {
            "evidence_count": len(evidence),
            "note_count": len(notes),
            "entries": _compact_value(self._notebook_entries, max_string=1800, max_items=60, max_depth=8),
        }

    def _next_result_set_id(self) -> str:
        self._result_set_counter += 1
        return f"rs_{self._result_set_counter}"

    def _register_result_set(
        self,
        *,
        tool: str,
        kind: str,
        raw_rows: List[Dict[str, Any]],
        compact_items: List[Dict[str, Any]],
        query: Dict[str, Any],
    ) -> str:
        result_set_id = self._next_result_set_id()
        raw_by_number = {index + 1: row for index, row in enumerate(raw_rows)}
        kind_by_number = {index + 1: kind for index in range(len(raw_rows))}
        self._result_sets[result_set_id] = {
            "tool": tool,
            "kind": kind,
            "query": _compact_value(query, max_string=500, max_items=20, max_depth=4),
            "raw_by_number": raw_by_number,
            "kind_by_number": kind_by_number,
            "items": compact_items,
        }
        self._last_result_set_id = result_set_id
        return result_set_id

    def _register_mixed_result_set(
        self,
        *,
        tool: str,
        rows: List[Tuple[str, Dict[str, Any]]],
        compact_items: List[Dict[str, Any]],
        query: Dict[str, Any],
    ) -> str:
        result_set_id = self._next_result_set_id()
        self._result_sets[result_set_id] = {
            "tool": tool,
            "kind": "mixed",
            "query": _compact_value(query, max_string=500, max_items=20, max_depth=4),
            "raw_by_number": {index + 1: row for index, (_kind, row) in enumerate(rows)},
            "kind_by_number": {index + 1: kind for index, (kind, _row) in enumerate(rows)},
            "items": compact_items,
        }
        self._last_result_set_id = result_set_id
        return result_set_id

    def _result_set_response(
        self,
        *,
        ok: bool,
        result_set_id: str,
        items: List[Dict[str, Any]],
        total_matches: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        response: Dict[str, Any] = {
            "ok": ok,
            "result_set_id": result_set_id,
            "items": items,
            "notebook_instruction": (
                "Call notebook_add_items with result_set_id and chosen item_numbers "
                "to preserve evidence for final extraction."
            ),
        }
        if total_matches is not None:
            response["total_matches"] = total_matches
        if extra:
            response.update(extra)
        return response

    def _comparable_recommendations(
        self,
        *,
        trajectory: Trajectory,
        experiment_result: Any,
        component: Optional[str] = None,
        include_pending: bool = False,
        limit: int = 50,
    ) -> List[Any]:
        if self.rec_manager is None:
            return []

        metadata = getattr(trajectory, "metadata", {}) or {}
        target_material_norm = normalize_material_name(metadata.get("target_material"))
        target_temp = normalize_temperature_C(metadata.get("target_temperature"))
        temp_tol = float(
            ((self.config.get("agent", {}) or {}).get("acceptance", {}) or {}).get(
                "temperature_tolerance_C", 0.5
            )
        )
        component_norm = normalize_component_name(component) if component else ""

        try:
            recs = self.rec_manager.list_recommendations(limit=max(limit * 4, 1000))
        except Exception:
            return []

        rows: List[Any] = []
        current_task_id = str(getattr(trajectory, "task_id", "") or "")
        for rec in recs:
            if not include_pending and getattr(rec, "experiment_result", None) is None:
                continue
            if current_task_id and str(getattr(rec, "task_id", "") or "") == current_task_id:
                continue

            task = getattr(rec, "task", {}) or {}
            rec_material_norm = normalize_material_name(task.get("target_material"))
            if target_material_norm and rec_material_norm and target_material_norm != rec_material_norm:
                continue

            rec_temp = normalize_temperature_C(task.get("target_temperature"))
            if target_temp is not None and rec_temp is not None:
                if abs(float(target_temp) - float(rec_temp)) > temp_tol:
                    continue

            if component_norm:
                formulation = getattr(rec, "formulation", {}) or {}
                comp_norms = {
                    c.get("normalized")
                    for c in extract_formulation_components(formulation)
                    if c.get("normalized")
                }
                if component_norm not in comp_norms:
                    continue

            rows.append(rec)
            if len(rows) >= limit:
                break

        return rows

    def search_similar_memories(
        self,
        *,
        query: str,
        top_k: int = 5,
        where: str = "",
    ) -> Dict[str, Any]:
        if not self.retriever:
            return {"ok": False, "error": "memory retriever unavailable", "items": []}
        top_k = max(1, min(int(top_k or 5), 12))
        filters: Dict[str, Any] = {}
        candidates: Optional[List[MemoryItem]] = None
        if where:
            structured_rows = self._memory_rows(where=where, order_by="")
            titles = {item.get("title") for item in structured_rows}
            candidates = [
                memory
                for memory in (self.memory_bank.get_all_memories() if self.memory_bank else [])
                if memory.title in titles
            ]
            if candidates is not None and self.memory_bank is not None:
                # Use temporary exact-title filtering through the bank's existing retriever interface.
                # If duplicate titles exist, they intentionally remain eligible.
                filters = {}
        q = MemoryQuery(query_text=query, top_k=top_k, filters=filters, min_similarity=0.0)
        try:
            if candidates is not None:
                query_embedding = self.retriever.embedding_func(query)
                scored = self.retriever._score_memories(query_embedding, candidates)  # type: ignore[attr-defined]
                scored.sort(key=lambda item: item[1], reverse=True)
                rows = [_memory_to_tool_row(memory, score=score) for memory, score in scored[:top_k]]
            elif hasattr(self.retriever, "retrieve_with_scores"):
                rows = [
                    _memory_to_tool_row(memory, score=score)
                    for memory, score in self.retriever.retrieve_with_scores(q)
                ]
            else:
                rows = [_memory_to_tool_row(memory) for memory in self.retriever.retrieve(q)]
        except Exception as e:
            return {"ok": False, "error": str(e), "items": []}
        raw_rows = rows[:top_k]
        compact_items = [
            _memory_to_compact_tool_row(row, number=index + 1)
            for index, row in enumerate(raw_rows)
        ]
        result_set_id = self._register_result_set(
            tool="search_similar_memories",
            kind="memory",
            raw_rows=raw_rows,
            compact_items=compact_items,
            query={"query": query, "top_k": top_k, "where": where},
        )
        return self._result_set_response(
            ok=True,
            result_set_id=result_set_id,
            items=compact_items,
        )

    def _memory_rows(self, *, where: str = "", order_by: str = "-created_at") -> List[Dict[str, Any]]:
        rows = [_memory_to_tool_row(memory) for memory in self.memory_bank.get_all_memories()]
        rows = [row for row in rows if _matches_where(row, where)]
        return _sort_rows(rows, order_by)

    def search_memories(
        self,
        *,
        where: str = "",
        limit: int = 20,
        order_by: str = "-created_at",
    ) -> Dict[str, Any]:
        if not self.memory_bank:
            return {"ok": False, "error": "memory bank unavailable", "items": []}
        return_limit = max(1, min(int(limit or 20), 100))
        try:
            rows = self._memory_rows(where=where, order_by=order_by)
        except Exception as e:
            return {"ok": False, "error": str(e), "items": []}
        raw_rows = rows[:return_limit]
        compact_items = [
            _memory_to_compact_tool_row(row, number=index + 1)
            for index, row in enumerate(raw_rows)
        ]
        result_set_id = self._register_result_set(
            tool="search_memories",
            kind="memory",
            raw_rows=raw_rows,
            compact_items=compact_items,
            query={"where": where, "limit": return_limit, "order_by": order_by},
        )
        return self._result_set_response(
            ok=True,
            result_set_id=result_set_id,
            items=compact_items,
            total_matches=len(rows),
        )

    def list_memory_field_values(
        self,
        *,
        field: str,
        where: str = "",
        limit: int = 50,
    ) -> Dict[str, Any]:
        if not self.memory_bank:
            return {"ok": False, "error": "memory bank unavailable", "field": field, "values": []}
        if not field:
            return {"ok": False, "error": "field is required", "field": field, "values": []}
        try:
            rows = self._memory_rows(where=where, order_by="")
            values = _distinct_field_values(rows, field, limit)
        except Exception as e:
            return {"ok": False, "error": str(e), "field": field, "values": []}
        return {"ok": True, "field": field, "where": where, "values": values}

    def _recommendation_rows(
        self,
        *,
        trajectory: Trajectory,
        component: Optional[str] = None,
        performance_band: Optional[str] = None,
        include_pending: bool = False,
        where: str = "",
        order_by: str = "-created_at",
        scope: str = "comparable",
    ) -> List[Dict[str, Any]]:
        if str(scope or "comparable").strip().lower() == "all":
            recs = self.rec_manager.list_recommendations(limit=10000) if self.rec_manager else []
            if not include_pending:
                recs = [r for r in recs if getattr(r, "experiment_result", None) is not None]
            if component:
                component_norm = normalize_component_name(component)
                filtered = []
                for rec in recs:
                    comp_norms = {
                        c.get("normalized")
                        for c in extract_formulation_components(getattr(rec, "formulation", {}) or {})
                        if c.get("normalized")
                    }
                    if component_norm in comp_norms:
                        filtered.append(rec)
                recs = filtered
        else:
            recs = self._comparable_recommendations(
                trajectory=trajectory,
                experiment_result=None,
                component=component,
                include_pending=include_pending,
                limit=10000,
            )
        candidate_rows = []
        for rec in recs:
            row = _recommendation_to_tool_row(rec, include_experiment=True)
            row["performance_band"] = _recommendation_performance_band(row, self.config)
            candidate_rows.append(row)
        candidate_rows = [row for row in candidate_rows if _matches_where(row, where)]
        candidate_rows = _sort_rows(candidate_rows, order_by)

        if performance_band:
            candidate_rows = [
                row for row in candidate_rows
                if str(row.get("performance_band") or "") == str(performance_band)
            ]
        return candidate_rows

    def search_recommendations(
        self,
        *,
        trajectory: Trajectory,
        experiment_result: Any,
        component: Optional[str] = None,
        performance_band: Optional[str] = None,
        include_pending: bool = False,
        limit: int = 8,
        where: str = "",
        order_by: str = "-created_at",
        scope: str = "comparable",
    ) -> Dict[str, Any]:
        return_limit = max(1, min(int(limit or 8), 20))
        try:
            candidate_rows = self._recommendation_rows(
                trajectory=trajectory,
                component=component,
                performance_band=performance_band,
                include_pending=include_pending,
                where=where,
                order_by=order_by,
                scope=scope,
            )
        except Exception as e:
            return {"ok": False, "error": str(e), "items": []}

        raw_rows = candidate_rows[:return_limit]
        compact_items = [
            _recommendation_to_compact_tool_row(row, number=index + 1)
            for index, row in enumerate(raw_rows)
        ]
        result_set_id = self._register_result_set(
            tool="search_recommendations",
            kind="recommendation",
            raw_rows=raw_rows,
            compact_items=compact_items,
            query={
                "component": component or "",
                "performance_band": performance_band or "",
                "include_pending": include_pending,
                "limit": return_limit,
                "where": where,
                "order_by": order_by,
                "scope": scope,
            },
        )
        return self._result_set_response(
            ok=True,
            result_set_id=result_set_id,
            items=compact_items,
            total_matches=len(candidate_rows),
        )

    def list_recommendation_field_values(
        self,
        *,
        trajectory: Trajectory,
        experiment_result: Any,
        field: str,
        where: str = "",
        include_pending: bool = False,
        limit: int = 50,
        scope: str = "comparable",
    ) -> Dict[str, Any]:
        if not self.rec_manager:
            return {"ok": False, "error": "recommendation manager unavailable", "field": field, "values": []}
        if not field:
            return {"ok": False, "error": "field is required", "field": field, "values": []}
        try:
            all_rows = self._recommendation_rows(
                trajectory=trajectory,
                include_pending=include_pending,
                where=where,
                order_by="",
                scope=scope,
            )
            values = _distinct_field_values(all_rows, field, limit)
        except Exception as e:
            return {"ok": False, "error": str(e), "field": field, "values": []}
        return {"ok": True, "field": field, "where": where, "scope": scope, "values": values}

    def inspect_recommendation(self, recommendation_id: str) -> Dict[str, Any]:
        if not self.rec_manager:
            return {"ok": False, "error": "recommendation manager unavailable"}
        if not recommendation_id:
            return {"ok": False, "error": "recommendation_id is required"}
        try:
            rec = self.rec_manager.get_recommendation(recommendation_id)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        if rec is None:
            return {"ok": False, "error": f"recommendation not found: {recommendation_id}"}
        row = _recommendation_to_tool_row(rec, include_experiment=True)
        row["performance_band"] = _recommendation_performance_band(row, self.config)
        rows = [("recommendation", row)]
        compact_items = [_recommendation_to_compact_tool_row(row, number=1)]
        result_set_id = self._register_mixed_result_set(
            tool="inspect_recommendation",
            rows=rows,
            compact_items=compact_items,
            query={"recommendation_id": recommendation_id},
        )
        return self._result_set_response(
            ok=True,
            result_set_id=result_set_id,
            items=compact_items,
            extra={"raw_item": _recommendation_raw_view(row)},
        )

    def _find_memory_by_ref(self, item_ref: str) -> Optional[Dict[str, Any]]:
        if not self.memory_bank:
            return None
        item_ref = str(item_ref or "")
        prefix = "memory:"
        if not item_ref.startswith(prefix):
            return None
        rest = item_ref[len(prefix):]
        source_task_id, sep, title = rest.partition(":")
        for memory in self.memory_bank.get_all_memories():
            if sep:
                if str(memory.source_task_id or "") == source_task_id and str(memory.title or "") == title:
                    return _memory_to_tool_row(memory)
            elif str(memory.title or "") == rest:
                return _memory_to_tool_row(memory)
        return None

    def _find_recommendation_by_ref(self, item_ref: str) -> Optional[Dict[str, Any]]:
        if not self.rec_manager:
            return None
        item_ref = str(item_ref or "")
        prefix = "recommendation:"
        if not item_ref.startswith(prefix):
            return None
        recommendation_id = item_ref[len(prefix):]
        if not recommendation_id:
            return None
        rec = self.rec_manager.get_recommendation(recommendation_id)
        if rec is None:
            return None
        row = _recommendation_to_tool_row(rec, include_experiment=True)
        row["performance_band"] = _recommendation_performance_band(row, self.config)
        return row

    def inspect_item(self, item_ref: str) -> Dict[str, Any]:
        item_ref = str(item_ref or "").strip()
        if not item_ref:
            return {"ok": False, "error": "item_ref is required"}

        if item_ref.startswith("recommendation:"):
            try:
                row = self._find_recommendation_by_ref(item_ref)
            except Exception as e:
                return {"ok": False, "error": str(e)}
            if row is None:
                return {"ok": False, "error": f"item not found: {item_ref}"}
            compact = _recommendation_to_compact_tool_row(row, number=1)
            raw_item = _recommendation_raw_view(row)
            rows = [("recommendation", row)]
        elif item_ref.startswith("memory:"):
            row = self._find_memory_by_ref(item_ref)
            if row is None:
                return {"ok": False, "error": f"item not found: {item_ref}"}
            compact = _memory_to_compact_tool_row(row, number=1)
            raw_item = _memory_raw_view(row)
            rows = [("memory", row)]
        else:
            return {
                "ok": False,
                "error": "item_ref must start with memory: or recommendation:",
            }

        result_set_id = self._register_mixed_result_set(
            tool="inspect_item",
            rows=rows,
            compact_items=[compact],
            query={"item_ref": item_ref},
        )
        return self._result_set_response(
            ok=True,
            result_set_id=result_set_id,
            items=[compact],
            extra={"raw_item": raw_item},
        )

    def notebook_add_items(
        self,
        *,
        result_set_id: str,
        item_numbers: List[Any],
        note: str = "",
    ) -> Dict[str, Any]:
        result_set_id = str(result_set_id or "").strip() or self._last_result_set_id
        if not result_set_id:
            return {"ok": False, "error": "result_set_id is required"}
        result_set = self._result_sets.get(result_set_id)
        if result_set is None:
            return {"ok": False, "error": f"unknown result_set_id: {result_set_id}"}

        raw_by_number = result_set.get("raw_by_number") or {}
        kind_by_number = result_set.get("kind_by_number") or {}
        added: List[int] = []
        skipped: List[Dict[str, Any]] = []
        for raw_number in item_numbers:
            try:
                number = int(raw_number)
            except Exception:
                skipped.append({"item_number": raw_number, "reason": "not an integer"})
                continue
            row = raw_by_number.get(number)
            kind = kind_by_number.get(number)
            if row is None or kind is None:
                skipped.append({"item_number": number, "reason": "not found in result_set"})
                continue
            ref = _item_ref(kind, row)
            if ref in self._notebook_refs:
                skipped.append({"item_number": number, "item_ref": ref, "reason": "already in notebook"})
                continue
            entry = _notebook_entry_from_row(
                kind=kind,
                row=row,
                source_tool=str(result_set.get("tool") or ""),
                result_set_id=result_set_id,
                item_number=number,
                note=note,
            )
            self._notebook_entries.append(entry)
            self._notebook_refs.add(ref)
            added.append(number)

        return {
            "ok": bool(added),
            "result_set_id": result_set_id,
            "added_item_numbers": added,
            "skipped": skipped,
            "notebook": self.notebook_view().get("notebook"),
        }

    def notebook_add_note(self, note: str) -> Dict[str, Any]:
        note = str(note or "").strip()
        if not note:
            return {"ok": False, "error": "note is required"}
        self._notebook_entries.append(
            {
                "entry_type": "note",
                "note": _clip_text(note, 2000),
            }
        )
        return {"ok": True, "notebook": self.notebook_view().get("notebook")}

    def notebook_view(self) -> Dict[str, Any]:
        evidence = [
            entry
            for entry in self._notebook_entries
            if entry.get("entry_type") == "evidence_item"
        ]
        notes = [
            entry
            for entry in self._notebook_entries
            if entry.get("entry_type") == "note"
        ]
        evidence_summary = []
        for index, entry in enumerate(evidence, start=1):
            summary = entry.get("structured_summary") or {}
            evidence_summary.append(
                {
                    "notebook_number": index,
                    "kind": entry.get("kind"),
                    "item_ref": entry.get("item_ref"),
                    "title": summary.get("title"),
                    "recommendation_id": summary.get("recommendation_id"),
                    "performance_band": summary.get("performance_band")
                    or ((summary.get("metadata") or {}).get("performance_band") if isinstance(summary.get("metadata"), dict) else None),
                    "model_note": entry.get("model_note"),
                }
            )
        return {
            "ok": True,
            "notebook": {
                "evidence_count": len(evidence),
                "note_count": len(notes),
                "evidence_summary": evidence_summary,
                "notes": [_clip_text(entry.get("note"), 700) for entry in notes],
            },
        }


def dumps_tool_result(result: Dict[str, Any], *, max_chars: int = 6000) -> str:
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... <truncated>"
