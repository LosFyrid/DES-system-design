"""
Regression tests for keeping recommendation generation status separate from
feedback-processing status.
"""

import sys
import types
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

agent_loader_stub = types.ModuleType("utils.agent_loader")
agent_loader_stub.get_agent = lambda: None
agent_loader_stub.get_rec_manager = lambda: None
sys.modules["utils.agent_loader"] = agent_loader_stub

from agent.reasoningbank.feedback import (  # noqa: E402
    ExperimentResult,
    Recommendation,
    RecommendationManager,
)
from agent.reasoningbank.memory import Trajectory  # noqa: E402
import services.feedback_service as feedback_service_module  # noqa: E402
from services.feedback_service import FeedbackService  # noqa: E402


def _make_recommendation(rec_id: str, status: str = "PENDING") -> Recommendation:
    return Recommendation(
        recommendation_id=rec_id,
        task={"target_material": "battery black mass", "target_temperature": 25},
        task_id="task_001",
        formulation={
            "components": [
                {"name": "Choline chloride", "role": "HBA"},
                {"name": "Tin(II) chloride", "role": "Lewis-acidic salt"},
            ],
            "molar_ratio": "1:0.5",
            "num_components": 2,
        },
        reasoning="Candidate formulation.",
        confidence=0.7,
        trajectory=Trajectory(
            task_id="task_001",
            task_description="Design a DES for NMC811 leaching.",
            steps=[],
            outcome="pending",
            final_result={"supporting_evidence": []},
            metadata={},
        ),
        status=status,
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )


def _experiment_result() -> ExperimentResult:
    return ExperimentResult(
        is_liquid_formed=True,
        measurements=[
            {
                "target_material": "Li",
                "time_h": 6,
                "leaching_efficiency": 35.5,
                "unit": "%",
            }
        ],
    )


def test_failed_feedback_extraction_keeps_completed_recommendation_status(tmp_path, monkeypatch):
    rec_manager = RecommendationManager(str(tmp_path))
    rec = _make_recommendation("REC_feedback_failure", status="PROCESSING")
    rec.experiment_result = _experiment_result()
    rec_manager.save_recommendation(rec)

    monkeypatch.setattr(feedback_service_module, "get_rec_manager", lambda: rec_manager)
    service = FeedbackService()

    service._record_feedback_failure(
        recommendation_id=rec.recommendation_id,
        error="ReAct experiment extractor produced 0 memories",
        failed_at="2026-06-01T08:33:09",
        previous_status="COMPLETED",
    )

    saved = rec_manager.get_recommendation(rec.recommendation_id)

    assert saved.status == "COMPLETED"
    assert saved.trajectory.metadata["feedback_processing_status"] == "failed"
    assert (
        saved.trajectory.metadata["feedback_processing_error"]
        == "ReAct experiment extractor produced 0 memories"
    )


def test_index_views_treat_failed_records_with_experiment_results_as_completed(tmp_path):
    rec_manager = RecommendationManager(str(tmp_path))
    rec = _make_recommendation("REC_contaminated_status", status="FAILED")
    rec.experiment_result = _experiment_result()
    rec_manager.save_recommendation(rec)

    # Simulate an older index written before `has_experiment_result` existed.
    rec_manager.index[rec.recommendation_id].pop("has_experiment_result")

    stats = rec_manager.get_statistics_fast()
    listing = rec_manager.list_recommendations_fast(status="COMPLETED")
    full_listing = rec_manager.list_recommendations(status="COMPLETED")

    assert stats["FAILED"] == 0
    assert stats["COMPLETED"] == 1
    assert listing["pagination"]["total"] == 1
    assert listing["items"][0]["status"] == "COMPLETED"
    assert [rec.recommendation_id for rec in full_listing] == [
        rec.recommendation_id
    ]
