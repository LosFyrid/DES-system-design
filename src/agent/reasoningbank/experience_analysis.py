"""
Deterministic evidence analysis for experiment-derived memories.

The LLM should decide how to phrase a memory, but it should not have to infer
basic quantitative context from scratch. This module turns one feedback record
plus comparable history into structured signals that extraction and generation
can both reuse.
"""

from __future__ import annotations

from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..utils.formulation_signature import normalize_component_name, normalize_material_name
from ..utils.formulation_validation import summarize_formulation


DEFAULT_LOW_PERCENT = 20.0
DEFAULT_HIGH_PERCENT = 60.0
TRANSITION_METALS = {"ni", "co", "mn"}
LITHIUM = {"li", "lithium"}


def _to_dict(obj: Any) -> Dict[str, Any]:
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


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _is_percent_unit(unit: Any) -> bool:
    return str(unit or "").strip().lower() in {"%", "percent", "pct", "percentage"}


def _round_or_none(value: Optional[float], ndigits: int = 3) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), ndigits)


def _target_key(value: Any) -> str:
    return str(value or "unknown").strip().lower()


def _normalize_ratio_key(conditions: Dict[str, Any]) -> str:
    sl = _to_dict(conditions.get("solid_liquid_ratio"))
    if not sl:
        return ""

    solid = _safe_float(sl.get("solid_mass_g"))
    liquid = _safe_float(sl.get("liquid_volume_ml"))
    ratio_text = str(sl.get("ratio_text") or "").strip().lower()

    if solid is not None and liquid is not None:
        return f"{solid:g}:{liquid:g}"
    return ratio_text


def extract_formulation_components(formulation: Any) -> List[Dict[str, str]]:
    """Return display and normalized component names from binary or N-component formulations."""
    if not isinstance(formulation, dict):
        return []

    components: List[Dict[str, str]] = []
    raw_components = formulation.get("components")
    if isinstance(raw_components, list) and raw_components:
        for item in raw_components:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                role = str(item.get("role") or "").strip()
            else:
                name = str(item or "").strip()
                role = ""
            norm = normalize_component_name(name)
            if name and norm:
                components.append({"name": name, "normalized": norm, "role": role})
        return components

    for key in ("HBD", "HBA"):
        name = str(formulation.get(key) or "").strip()
        norm = normalize_component_name(name)
        if name and norm:
            components.append({"name": name, "normalized": norm, "role": key})
    return components


def summarize_measurements(measurements: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    units: List[str] = []

    for raw in measurements or []:
        if not isinstance(raw, dict):
            continue
        value = _safe_float(raw.get("leaching_efficiency"))
        unit = str(raw.get("unit") or "%").strip() or "%"
        target = str(raw.get("target_material") or "unknown").strip()
        time_h = _safe_float(raw.get("time_h"))
        if value is None:
            continue
        rows.append(
            {
                "target_material": target,
                "target_key": _target_key(target),
                "time_h": time_h,
                "value": value,
                "unit": unit,
            }
        )
        units.append(unit)

    if not rows:
        return {
            "measurement_count": 0,
            "unit": "%",
            "percent_like": True,
            "max_value": None,
            "avg_value": None,
            "target_stats": {},
            "lithium_max": None,
            "transition_metal_avg_max": None,
            "transition_metal_targets": [],
        }

    unit = next((u for u in units if u), "%")
    percent_like = _is_percent_unit(unit)

    target_stats: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = row["target_key"]
        stat = target_stats.setdefault(
            key,
            {
                "target_material": row["target_material"],
                "values": [],
                "max_value": None,
                "time_at_max_h": None,
            },
        )
        stat["values"].append(row["value"])
        if stat["max_value"] is None or row["value"] > stat["max_value"]:
            stat["max_value"] = row["value"]
            stat["time_at_max_h"] = row["time_h"]

    compact_target_stats: Dict[str, Dict[str, Any]] = {}
    for key, stat in target_stats.items():
        vals = stat["values"]
        compact_target_stats[key] = {
            "target_material": stat["target_material"],
            "max_value": _round_or_none(stat["max_value"]),
            "avg_value": _round_or_none(mean(vals) if vals else None),
            "time_at_max_h": stat["time_at_max_h"],
            "n": len(vals),
        }

    all_values = [r["value"] for r in rows]
    lithium_values = [
        stat["max_value"]
        for key, stat in target_stats.items()
        if key in LITHIUM and stat["max_value"] is not None
    ]
    tm_values = [
        stat["max_value"]
        for key, stat in target_stats.items()
        if key in TRANSITION_METALS and stat["max_value"] is not None
    ]

    return {
        "measurement_count": len(rows),
        "unit": unit,
        "percent_like": percent_like,
        "max_value": _round_or_none(max(all_values)),
        "avg_value": _round_or_none(mean(all_values)),
        "target_stats": compact_target_stats,
        "lithium_max": _round_or_none(max(lithium_values) if lithium_values else None),
        "transition_metal_avg_max": _round_or_none(mean(tm_values) if tm_values else None),
        "transition_metal_targets": sorted(
            [compact_target_stats[k]["target_material"] for k in compact_target_stats if k in TRANSITION_METALS]
        ),
    }


def classify_performance_band(
    value: Optional[float],
    *,
    low_percent: float = DEFAULT_LOW_PERCENT,
    high_percent: float = DEFAULT_HIGH_PERCENT,
    is_liquid_formed: bool = True,
) -> str:
    if not is_liquid_formed:
        return "no_liquid"
    if value is None:
        return "formation_only"
    if value >= high_percent:
        return "high"
    if value < low_percent:
        return "low"
    return "moderate"


def _recommendation_to_history_row(rec: Any) -> Optional[Dict[str, Any]]:
    exp = getattr(rec, "experiment_result", None)
    if exp is None:
        return None

    formulation = getattr(rec, "formulation", {}) or {}
    task = getattr(rec, "task", {}) or {}
    stats = summarize_measurements(getattr(exp, "measurements", []) or [])
    components = extract_formulation_components(formulation)

    return {
        "recommendation_id": str(getattr(rec, "recommendation_id", "") or ""),
        "task_id": str(getattr(rec, "task_id", "") or ""),
        "status": str(getattr(rec, "status", "") or ""),
        "created_at": str(getattr(rec, "created_at", "") or ""),
        "target_material": task.get("target_material"),
        "target_material_norm": normalize_material_name(task.get("target_material")),
        "target_temperature": task.get("target_temperature"),
        "formulation_summary": summarize_formulation(formulation),
        "components": components,
        "component_norms": [c["normalized"] for c in components],
        "conditions": _to_dict(getattr(exp, "conditions", {}) or {}),
        "is_liquid_formed": bool(getattr(exp, "is_liquid_formed", False)),
        "measurement_stats": stats,
        "max_value": stats.get("max_value"),
        "avg_value": stats.get("avg_value"),
        "unit": stats.get("unit"),
    }


def _percentile_context(current: Optional[float], history_values: List[float]) -> Dict[str, Any]:
    if current is None or not history_values:
        return {
            "history_count": len(history_values),
            "better_than_count": 0,
            "worse_than_count": 0,
            "percentile_estimate": None,
        }

    better_than = sum(1 for v in history_values if current > v)
    equal_to = sum(1 for v in history_values if current == v)
    worse_than = sum(1 for v in history_values if current < v)
    percentile = (better_than + 0.5 * equal_to) / len(history_values) * 100.0

    return {
        "history_count": len(history_values),
        "better_than_count": better_than,
        "equal_to_count": equal_to,
        "worse_than_count": worse_than,
        "percentile_estimate": round(percentile, 1),
    }


def _best_history_row(history_rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    rows = [r for r in history_rows if _safe_float(r.get("max_value")) is not None]
    if not rows:
        return None
    return max(rows, key=lambda r: float(r.get("max_value") or 0.0))


def _condition_context(current_conditions: Dict[str, Any], history_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    current_ratio = _normalize_ratio_key(current_conditions)
    history_ratios = [
        _normalize_ratio_key(_to_dict(r.get("conditions")))
        for r in history_rows
        if _normalize_ratio_key(_to_dict(r.get("conditions")))
    ]

    ratio_context = {
        "current": current_ratio,
        "history_values": sorted(set(history_ratios)),
        "history_count": len(history_ratios),
        "is_constant_across_history": False,
        "discriminative": True,
    }
    if current_ratio and history_ratios:
        unique = set(history_ratios)
        ratio_context["is_constant_across_history"] = len(unique) == 1 and current_ratio in unique
        ratio_context["discriminative"] = not bool(ratio_context["is_constant_across_history"])

    low_information_fields: List[str] = []
    if current_ratio and not ratio_context["discriminative"]:
        low_information_fields.append("solid_liquid_ratio")

    return {
        "solid_liquid_ratio": ratio_context,
        "low_information_fields": low_information_fields,
    }


def _component_signal_level(
    *,
    current_band: str,
    historical_best: Optional[float],
    high_percent: float,
    better_than_count: int,
) -> str:
    if historical_best is not None and historical_best >= high_percent:
        return "mixed_or_promising"
    if current_band == "high":
        return "promising"
    if current_band == "moderate":
        return "use_with_rationale"
    if current_band == "low":
        if better_than_count > 0:
            return "exploratory_partial_positive"
        return "use_with_rationale"
    if current_band in {"no_liquid", "formation_only"}:
        return "insufficient_evidence"
    return "neutral"


def _component_signals(
    current_components: List[Dict[str, str]],
    *,
    current_band: str,
    history_rows: List[Dict[str, Any]],
    high_percent: float,
    better_than_count: int,
) -> List[Dict[str, Any]]:
    signals: List[Dict[str, Any]] = []
    for comp in current_components:
        norm = comp.get("normalized", "")
        if not norm:
            continue
        matching = [
            r
            for r in history_rows
            if norm in set(str(x) for x in (r.get("component_norms") or []))
            and _safe_float(r.get("max_value")) is not None
        ]
        values = [float(r.get("max_value")) for r in matching if _safe_float(r.get("max_value")) is not None]
        historical_best = max(values) if values else None
        historical_avg = mean(values) if values else None
        level = _component_signal_level(
            current_band=current_band,
            historical_best=historical_best,
            high_percent=high_percent,
            better_than_count=better_than_count,
        )

        signals.append(
            {
                "component": comp.get("name", norm),
                "normalized": norm,
                "role": comp.get("role", ""),
                "level": level,
                "historical_count": len(values),
                "historical_best_percent": _round_or_none(historical_best),
                "historical_avg_percent": _round_or_none(historical_avg),
                "implication": _component_implication(level),
            }
        )
    return signals


def _component_implication(level: str) -> str:
    if level == "promising":
        return "Strong current evidence; can guide future high-performance variants."
    if level == "mixed_or_promising":
        return "History contains stronger variants; reuse should preserve or explain the stronger mechanism."
    if level == "exploratory_partial_positive":
        return "Not a high-performance proof, but has relative merit versus weaker history."
    if level == "use_with_rationale":
        return "Reuse should require a clear mechanistic or compositional change, not blind repetition."
    if level == "insufficient_evidence":
        return "Do not overgeneralize; more comparable experiments are needed."
    return "Neutral signal."


def build_experience_profile(
    *,
    trajectory: Any,
    experiment_result: Any,
    history_recommendations: Optional[List[Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a JSON-safe profile for one experimental feedback item."""
    config = config or {}
    low_percent = float(config.get("low_performance_percent", DEFAULT_LOW_PERCENT))
    high_percent = float(config.get("high_performance_percent", DEFAULT_HIGH_PERCENT))

    final_result = getattr(trajectory, "final_result", {}) or {}
    formulation = final_result.get("formulation", {}) if isinstance(final_result, dict) else {}
    metadata = getattr(trajectory, "metadata", {}) or {}
    components = extract_formulation_components(formulation)
    measurements = getattr(experiment_result, "measurements", []) or []
    current_stats = summarize_measurements(measurements)
    current_max = _safe_float(current_stats.get("max_value"))
    is_liquid_formed = bool(getattr(experiment_result, "is_liquid_formed", False))
    current_band = classify_performance_band(
        current_max,
        low_percent=low_percent,
        high_percent=high_percent,
        is_liquid_formed=is_liquid_formed,
    )

    history_rows = [
        row
        for row in (_recommendation_to_history_row(r) for r in (history_recommendations or []))
        if row is not None
    ]
    history_values = [
        float(r.get("max_value"))
        for r in history_rows
        if _safe_float(r.get("max_value")) is not None
    ]
    percentile = _percentile_context(current_max, history_values)
    best_row = _best_history_row(history_rows)
    condition_context = _condition_context(
        _to_dict(getattr(experiment_result, "conditions", {}) or {}),
        history_rows,
    )

    better_than_count = int(percentile.get("better_than_count") or 0)
    component_signals = _component_signals(
        components,
        current_band=current_band,
        history_rows=history_rows,
        high_percent=high_percent,
        better_than_count=better_than_count,
    )

    relative_interpretation = "no_history"
    if history_values and current_max is not None:
        if best_row and current_max >= float(best_row.get("max_value") or 0.0):
            relative_interpretation = "best_so_far"
        elif better_than_count > 0:
            relative_interpretation = "partial_positive"
        else:
            relative_interpretation = "below_history"

    requires_rationale = [
        s["component"]
        for s in component_signals
        if s.get("level") in {"use_with_rationale", "exploratory_partial_positive"}
    ]

    profile = {
        "extractor_profile_version": "experience_profile_v1",
        "task_id": getattr(trajectory, "task_id", None),
        "task_description": getattr(trajectory, "task_description", ""),
        "target_material": metadata.get("target_material"),
        "target_material_norm": normalize_material_name(metadata.get("target_material")),
        "target_temperature": metadata.get("target_temperature"),
        "formulation_summary": summarize_formulation(formulation),
        "formulation_components": components,
        "formulation_components_norm": [c["normalized"] for c in components],
        "is_liquid_formed": is_liquid_formed,
        "performance_profile": {
            "performance_band": current_band,
            "low_percent_threshold": low_percent,
            "high_percent_threshold": high_percent,
            "measurement_stats": current_stats,
            "relative_interpretation": relative_interpretation,
            "benchmark_context": {
                **percentile,
                "best_history": (
                    {
                        "recommendation_id": best_row.get("recommendation_id"),
                        "formulation_summary": best_row.get("formulation_summary"),
                        "max_value": _round_or_none(_safe_float(best_row.get("max_value"))),
                        "unit": best_row.get("unit"),
                    }
                    if best_row
                    else None
                ),
                "history_median_max": _round_or_none(median(history_values) if history_values else None),
            },
        },
        "condition_context": condition_context,
        "component_performance_signals": component_signals,
        "recommendation_implications": {
            "avoid_absolute_negative": current_band in {"moderate", "low"} or relative_interpretation == "partial_positive",
            "preserve_relative_merit": relative_interpretation in {"best_so_far", "partial_positive"},
            "requires_mechanistic_change_before_reuse": requires_rationale,
            "low_information_fields": condition_context.get("low_information_fields", []),
        },
    }
    return profile


def format_experience_profile(profile: Dict[str, Any], *, max_component_signals: int = 8) -> str:
    """Format an experience profile for prompts without dumping the full JSON."""
    perf = _to_dict(profile.get("performance_profile"))
    stats = _to_dict(perf.get("measurement_stats"))
    bench = _to_dict(perf.get("benchmark_context"))
    implications = _to_dict(profile.get("recommendation_implications"))

    lines = [
        "## Structured Experiment Evidence",
        f"- Formulation: {profile.get('formulation_summary') or 'N/A'}",
        f"- Liquid formed: {profile.get('is_liquid_formed')}",
        (
            f"- Performance band: {perf.get('performance_band')} "
            f"(max={stats.get('max_value')} {stats.get('unit')}, avg={stats.get('avg_value')} {stats.get('unit')})"
        ),
        f"- Relative interpretation: {perf.get('relative_interpretation')}",
        (
            f"- History context: n={bench.get('history_count')}, "
            f"percentile≈{bench.get('percentile_estimate')}, "
            f"better_than={bench.get('better_than_count')}, worse_than={bench.get('worse_than_count')}"
        ),
    ]

    if bench.get("best_history"):
        best = _to_dict(bench.get("best_history"))
        lines.append(
            f"- Best comparable history: {best.get('recommendation_id')} | "
            f"{best.get('formulation_summary')} | max≈{best.get('max_value')} {best.get('unit')}"
        )

    low_info = implications.get("low_information_fields") or []
    if low_info:
        lines.append(
            "- Low-information conditions: "
            + ", ".join(str(x) for x in low_info)
            + " (do not emphasize unless another record varies it)"
        )

    comp_signals = profile.get("component_performance_signals") or []
    if comp_signals:
        lines.append("- Component signals:")
        for sig in comp_signals[:max_component_signals]:
            lines.append(
                "  - {component}: level={level}, historical_best={best}, implication={implication}".format(
                    component=sig.get("component"),
                    level=sig.get("level"),
                    best=sig.get("historical_best_percent"),
                    implication=sig.get("implication"),
                )
            )

    return "\n".join(lines)


def compact_profile_for_metadata(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Keep the parts of the profile that are useful downstream and cheap to store."""
    return {
        "extractor_profile_version": profile.get("extractor_profile_version"),
        "formulation_summary": profile.get("formulation_summary"),
        "formulation_components": profile.get("formulation_components", []),
        "formulation_components_norm": profile.get("formulation_components_norm", []),
        "performance_profile": profile.get("performance_profile", {}),
        "condition_context": profile.get("condition_context", {}),
        "component_performance_signals": profile.get("component_performance_signals", []),
        "recommendation_implications": profile.get("recommendation_implications", {}),
    }

