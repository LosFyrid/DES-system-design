"""
Tests for the feedback experience extraction refactor.

These tests focus on deterministic behavior around the user-facing failure
cases: redundant metrics, low-information solid/liquid ratio, calibrated
low/moderate performance, and downstream component reuse constraints.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent.des_agent import DESAgent
from agent.reasoningbank import MemoryExtractor, MemoryItem, ReasoningBank, Trajectory
from agent.reasoningbank.experience_analysis import build_experience_profile
from agent.reasoningbank.experience_history_tools import ExperienceHistoryTools
from agent.reasoningbank.feedback import ExperimentResult


def _exp(max_values, *, ratio=(0.1, 5.0), formed=True):
    targets = ["Li", "Ni", "Co", "Mn"][: len(max_values)]
    return ExperimentResult(
        is_liquid_formed=formed,
        measurements=[
            {
                "target_material": target,
                "time_h": 6,
                "leaching_efficiency": value,
                "unit": "%",
            }
            for target, value in zip(targets, max_values)
        ],
        conditions={
            "temperature_C": 25,
            "solid_liquid_ratio": {
                "solid_mass_g": ratio[0],
                "liquid_volume_ml": ratio[1],
                "ratio_text": f"{ratio[0]}:{ratio[1]}",
            },
        },
    )


def _traj(formulation=None):
    return Trajectory(
        task_id="task_current",
        task_description="Design a DES for lithium battery black mass leaching at 25C",
        steps=[],
        outcome="pending",
        final_result={
            "formulation": formulation
            or {
                "components": [
                    {"name": "Choline chloride", "role": "HBA"},
                    {"name": "Levulinic acid", "role": "HBD"},
                    {"name": "Water", "role": "modifier"},
                ],
                "molar_ratio": "1:1.2:0.4",
                "num_components": 3,
            }
        },
        metadata={"target_material": "black mass", "target_temperature": 25},
    )


def _history_rec(rec_id, values, formulation=None, *, ratio=(0.1, 5.0)):
    return SimpleNamespace(
        recommendation_id=rec_id,
        task_id=f"task_{rec_id}",
        status="COMPLETED",
        created_at=f"2026-05-0{rec_id[-1]}T00:00:00",
        updated_at=f"2026-05-0{rec_id[-1]}T00:00:00",
        task={"target_material": "black mass", "target_temperature": 25},
        formulation=formulation
        or {
            "components": [
                {"name": "Choline chloride", "role": "HBA"},
                {"name": "Levulinic acid", "role": "HBD"},
                {"name": "Water", "role": "modifier"},
            ],
            "molar_ratio": "1:1.2:0.4",
            "num_components": 3,
        },
        confidence=0.2,
        experiment_result=_exp(values, ratio=ratio),
    )


def test_experience_profile_marks_constant_solid_liquid_ratio_low_information():
    profile = build_experience_profile(
        trajectory=_traj(),
        experiment_result=_exp([33.0, 31.0, 30.0, 32.0]),
        history_recommendations=[
            _history_rec("REC_1", [20.0, 18.0, 19.0, 17.0]),
            _history_rec("REC_2", [10.0, 8.0, 9.0, 7.0]),
        ],
        config={"low_performance_percent": 20.0, "high_performance_percent": 60.0},
    )

    perf = profile["performance_profile"]
    assert perf["performance_band"] == "moderate"
    assert perf["relative_interpretation"] == "best_so_far"
    assert profile["recommendation_implications"]["preserve_relative_merit"] is True
    assert profile["recommendation_implications"]["avoid_absolute_negative"] is True
    assert "solid_liquid_ratio" in profile["condition_context"]["low_information_fields"]


def test_experience_profile_calibrates_low_but_better_than_worse_history():
    profile = build_experience_profile(
        trajectory=_traj(),
        experiment_result=_exp([8.7, 7.6, 7.6, 7.8]),
        history_recommendations=[
            _history_rec("REC_1", [2.9, 2.8, 2.7, 2.9]),
            _history_rec("REC_2", [65.0, 60.0, 58.0, 61.0]),
        ],
        config={"low_performance_percent": 20.0, "high_performance_percent": 60.0},
    )

    perf = profile["performance_profile"]
    assert perf["performance_band"] == "low"
    assert perf["relative_interpretation"] == "partial_positive"
    assert profile["recommendation_implications"]["preserve_relative_merit"] is True
    assert profile["recommendation_implications"]["avoid_absolute_negative"] is True

    levulinic = [
        s
        for s in profile["component_performance_signals"]
        if s["normalized"] == "levulinic acid"
    ][0]
    assert levulinic["level"] in {"mixed_or_promising", "exploratory_partial_positive"}


def test_extractor_raises_when_react_returns_no_memories():
    extractor = MemoryExtractor(
        lambda prompt, **kwargs: "",
        config={
            "extractor": {
                "react_enabled": True,
                "react_max_steps": 1,
                "require_history_tools": False,
            }
        },
    )

    with pytest.raises(RuntimeError, match="produced 0 memories"):
        extractor.extract_from_experiment(
            _traj(),
            _exp([33.0, 31.0, 30.0, 32.0]),
            history_tools=None,
        )

    assert extractor.last_extraction_audit["error"] == "react_extractor_returned_no_memories"


def test_history_tools_support_semantic_and_structured_memory_queries():
    memory_bank = ReasoningBank()
    memory_bank.add_memory(
        MemoryItem(
            title="Moderate benchmark memory",
            description="33 percent leaching has relative merit.",
            content="Preserve relative merit instead of labeling the formulation unsuitable.",
            source_task_id="task_old",
            metadata={
                "performance_band": "moderate",
                "relative_interpretation": "partial_positive",
                "extractor_profile": {
                    "formulation_components_norm": ["choline chloride", "urea"]
                },
            },
        ),
        compute_embedding=False,
    )
    memory_bank.add_memory(
        MemoryItem(
            title="Low signal memory",
            description="Weak leaching requires a mechanism change.",
            content="Avoid blind reuse.",
            source_task_id="task_low",
            metadata={"performance_band": "low", "relative_interpretation": "below_history"},
        ),
        compute_embedding=False,
    )

    class FakeRetriever:
        embedding_func = staticmethod(lambda text: [1.0, 0.0])

        def _score_memories(self, query_embedding, candidates):
            return [(memory, 0.9 - i * 0.1) for i, memory in enumerate(candidates)]

        def retrieve_with_scores(self, query):
            return [
                (memory, 0.9 - i * 0.1)
                for i, memory in enumerate(memory_bank.get_all_memories()[: query.top_k])
            ]

    tools = ExperienceHistoryTools(
        memory_bank=memory_bank,
        retriever=FakeRetriever(),
        rec_manager=None,
        config={},
    )

    structured = tools.search_memories(where="metadata.performance_band = 'moderate'")
    assert structured["ok"] is True
    assert structured["result_set_id"] == "rs_1"
    assert structured["total_matches"] == 1
    assert structured["items"][0]["title"] == "Moderate benchmark memory"
    assert structured["items"][0]["item_number"] == 1
    assert structured["items"][0]["kind"] == "memory"
    assert "content" not in structured["items"][0]
    assert structured["items"][0]["content_excerpt"].startswith("Preserve relative merit")

    values = tools.list_memory_field_values(field="metadata.performance_band")
    assert {item["value"] for item in values["values"]} == {"moderate", "low"}

    semantic = tools.search_similar_memories(
        query="relative leaching benchmark",
        where="metadata.relative_interpretation = 'partial_positive'",
    )
    assert semantic["ok"] is True
    assert semantic["items"][0]["title"] == "Moderate benchmark memory"

    added = tools.notebook_add_items(
        result_set_id=semantic["result_set_id"],
        item_numbers=[1],
        note="Relevant calibrated partial-positive memory.",
    )
    assert added["ok"] is True
    assert tools.notebook_payload()["evidence_count"] == 1
    assert tools.notebook_payload()["entries"][0]["evidence"]["content"].startswith(
        "Preserve relative merit"
    )


def test_history_tools_support_recommendation_filters_and_field_values():
    exp_moderate = _exp([33.0, 31.0, 30.0, 32.0])
    exp_low = _exp([8.0, 7.0, 6.0, 7.5])
    rec_moderate = _history_rec(
        "REC_1",
        [33.0, 31.0, 30.0, 32.0],
        formulation={
            "components": [
                {"name": "Choline chloride", "role": "HBA"},
                {"name": "Urea", "role": "HBD"},
            ],
            "molar_ratio": "1:2",
            "num_components": 2,
        },
    )
    rec_moderate.experiment_result = exp_moderate
    rec_low = _history_rec(
        "REC_2",
        [8.0, 7.0, 6.0, 7.5],
        formulation={
            "components": [
                {"name": "Levulinic acid", "role": "HBD"},
                {"name": "Choline chloride", "role": "HBA"},
            ],
            "molar_ratio": "1:1",
            "num_components": 2,
        },
    )
    rec_low.experiment_result = exp_low

    class RecManager:
        def list_recommendations(self, limit=100):
            return [rec_moderate, rec_low][:limit]

        def get_recommendation(self, recommendation_id):
            return {"REC_1": rec_moderate, "REC_2": rec_low}.get(recommendation_id)

    tools = ExperienceHistoryTools(
        memory_bank=ReasoningBank(),
        retriever=None,
        rec_manager=RecManager(),
        config={
            "extractor": {"low_performance_percent": 20.0, "high_performance_percent": 60.0},
            "agent": {"acceptance": {"temperature_tolerance_C": 0.5}},
        },
    )
    current = _traj()

    filtered = tools.search_recommendations(
        trajectory=current,
        experiment_result=exp_moderate,
        performance_band="moderate",
        where="components.normalized contains 'urea'",
        limit=5,
    )
    assert filtered["ok"] is True
    assert filtered["result_set_id"] == "rs_1"
    assert [item["recommendation_id"] for item in filtered["items"]] == ["REC_1"]
    assert filtered["items"][0]["item_number"] == 1
    assert "formulation" not in filtered["items"][0]
    assert filtered["items"][0]["formulation_summary"]

    inspected = tools.inspect_item(filtered["items"][0]["item_ref"])
    assert inspected["ok"] is True
    assert inspected["result_set_id"] == "rs_2"
    assert inspected["raw_item"]["recommendation_id"] == "REC_1"
    assert "formulation_json" in inspected["raw_item"]

    added = tools.notebook_add_items(
        result_set_id=filtered["result_set_id"],
        item_numbers=[1],
        note="Comparable moderate urea baseline.",
    )
    assert added["ok"] is True
    notebook = tools.notebook_payload()
    assert notebook["evidence_count"] == 1
    assert notebook["entries"][0]["evidence"]["recommendation_id"] == "REC_1"

    values = tools.list_recommendation_field_values(
        trajectory=current,
        experiment_result=exp_moderate,
        field="performance_band",
    )
    assert values["ok"] is True
    assert {item["value"] for item in values["values"]} == {"moderate", "low"}


def test_final_extraction_prompt_uses_notebook_not_raw_tool_results():
    extractor = MemoryExtractor(lambda prompt, **kwargs: "", config={"extractor": {}})
    tool_results = [
        {
            "tool": "search_memories",
            "result": {
                "items": [
                    {
                        "item_number": 1,
                        "title": "Should not appear",
                        "content": "UNWRITTEN_TOOL_RESULT_SHOULD_NOT_APPEAR",
                    }
                ]
            },
        }
    ]
    notebook = {
        "evidence_count": 1,
        "note_count": 1,
        "entries": [
            {
                "entry_type": "evidence_item",
                "kind": "memory",
                "evidence": {"content": "NOTEBOOK_EVIDENCE_SHOULD_APPEAR"},
            },
            {"entry_type": "note", "note": "NOTEBOOK_NOTE_SHOULD_APPEAR"},
        ],
    }
    profile = build_experience_profile(
        trajectory=_traj(),
        experiment_result=_exp([33.0, 31.0, 30.0, 32.0]),
        history_recommendations=[],
        config={},
    )

    prompt = extractor._build_final_extraction_prompt(
        trajectory=_traj(),
        experiment_result=_exp([33.0, 31.0, 30.0, 32.0]),
        profile=profile,
        notebook=notebook,
    )

    assert "NOTEBOOK_EVIDENCE_SHOULD_APPEAR" in prompt
    assert "NOTEBOOK_NOTE_SHOULD_APPEAR" in prompt
    assert "UNWRITTEN_TOOL_RESULT_SHOULD_NOT_APPEAR" not in prompt
    assert tool_results[0]["result"]["items"][0]["title"] not in prompt


def test_component_experience_gate_rejects_unexplained_reuse():
    memory_bank = ReasoningBank()
    memory_bank.add_memory(
        MemoryItem(
            title="Levulinic acid weak signal",
            description="Levulinic acid needs a rationale after low leaching",
            content="Low current leaching means reuse should require a mechanism change.",
            source_task_id="task_old",
            metadata={
                "source": "experiment_validated",
                "target_material": "black mass",
                "recommendation_id": "REC_LOW",
                "performance_band": "low",
                "relative_interpretation": "partial_positive",
                "measurements": [
                    {"target_material": "Li", "time_h": 6, "leaching_efficiency": 8.7, "unit": "%"}
                ],
                "extractor_profile": {
                    "formulation_components_norm": ["levulinic acid", "choline chloride"],
                    "performance_profile": {
                        "performance_band": "low",
                        "relative_interpretation": "partial_positive",
                        "measurement_stats": {"max_value": 8.7, "unit": "%"},
                    },
                    "recommendation_implications": {
                        "requires_mechanistic_change_before_reuse": ["Levulinic acid"]
                    },
                },
                "component_implications": [
                    {
                        "component": "Levulinic acid",
                        "action": "avoid_unless_changed",
                        "rationale": "Low leaching unless mechanism changes.",
                    }
                ],
            },
        ),
        compute_embedding=False,
    )

    agent = object.__new__(DESAgent)
    agent.memory = memory_bank
    agent.config = {
        "agent": {"component_experience_gate": {"enabled": True}},
        "extractor": {"low_performance_percent": 20.0},
    }

    formulation = {
        "components": [
            {"name": "Choline chloride", "role": "HBA"},
            {"name": "Levulinic acid", "role": "HBD"},
            {"name": "Water", "role": "modifier"},
        ],
        "molar_ratio": "1:1:0.4",
        "num_components": 3,
    }
    rejected = agent._component_experience_gate_check(
        formulation,
        task={"target_material": "black mass", "target_temperature": 25},
        expected_num_components=3,
        candidate={"reasoning": "This is a novel formulation.", "delta_to_baseline": []},
    )
    assert rejected["passed"] is False
    assert "component_experience_requires_rationale" in rejected["reasons"]

    accepted = agent._component_experience_gate_check(
        formulation,
        task={"target_material": "black mass", "target_temperature": 25},
        expected_num_components=3,
        candidate={
            "reasoning": "Levulinic acid is reused because a different Lewis-acid chloride complexation mechanism is introduced.",
            "delta_to_baseline": [
                {"change": "Add Lewis-acid chloride", "rationale": "Different mechanism"}
            ],
        },
    )
    assert accepted["passed"] is True
    assert accepted["rationale_detected"] is True
