"""
Read-only tools used by the feedback experience extractor.

These tools are deliberately plain Python callables. They make the extractor
agentic without coupling it to a specific LLM tool-calling API: an LLM can choose
actions in a ReAct loop, while local code executes only these bounded reads.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
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


def _memory_to_tool_row(memory: MemoryItem, *, score: Optional[float] = None) -> Dict[str, Any]:
    row = {
        "title": memory.title,
        "description": memory.description,
        "content": memory.content,
        "source_task_id": memory.source_task_id,
        "created_at": memory.created_at,
        "is_from_success": memory.is_from_success,
        "metadata": memory.metadata,
    }
    if score is not None:
        row["score"] = round(float(score), 4)
    return row


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


@dataclass
class ExperienceHistoryTools:
    memory_bank: Any
    retriever: Any
    rec_manager: Any
    config: Dict[str, Any]

    def tool_specs_text(self) -> str:
        """Human-readable tool list for the extractor ReAct prompt."""
        return """Available read-only tools:
- search_similar_memories: semantic embedding search over existing ReasoningBank memories by natural-language query text.
- search_memories: structured filter search over memory fields using a SQL-like WHERE string. Supports AND, =, !=, >, >=, <, <=, IN (...), CONTAINS, LIKE, IS NULL, IS NOT NULL, and exists(field). Example fields: title, source_task_id, is_from_success, metadata.performance_band, metadata.relative_interpretation, metadata.extractor_profile.formulation_components_norm.
- list_memory_field_values: list distinct values and counts for one memory field so you can choose valid filter values before calling search_memories.
- search_recommendations: structured search over historical recommendations/experiments. Use scope='comparable' for same material/temperature candidates or scope='all' for global history. Supports component, performance_band, include_pending, and SQL-like WHERE filtering.
- list_recommendation_field_values: list distinct values and counts for one recommendation field so you can choose valid filter values before calling search_recommendations.
- inspect_recommendation: inspect one historical recommendation by recommendation_id.
- finish: produce the final JSON memory extraction payload.
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
        return {"ok": False, "error": f"unknown tool: {name}"}

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
        return {"ok": True, "items": rows}

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
        return {"ok": True, "items": rows[:return_limit], "total_matches": len(rows)}

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
        extractor_cfg = self.config.get("extractor", {}) or {}
        low = float(extractor_cfg.get("low_performance_percent", 20.0))
        high = float(extractor_cfg.get("high_performance_percent", 60.0))

        candidate_rows = []
        for rec in recs:
            row = _recommendation_to_tool_row(rec, include_experiment=True)
            stats = ((row.get("experiment") or {}).get("measurement_stats") or {})
            max_value = _safe_float(stats.get("max_value"))
            is_liquid = bool((row.get("experiment") or {}).get("is_liquid_formed"))
            if not is_liquid:
                band = "no_liquid"
            elif max_value is None:
                band = "formation_only"
            elif max_value >= high:
                band = "high"
            elif max_value < low:
                band = "low"
            else:
                band = "moderate"
            row["performance_band"] = band
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

        return {
            "ok": True,
            "items": candidate_rows[:return_limit],
            "total_matches": len(candidate_rows),
        }

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
        return {"ok": True, "item": _recommendation_to_tool_row(rec, include_experiment=True)}


def dumps_tool_result(result: Dict[str, Any], *, max_chars: int = 6000) -> str:
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... <truncated>"
