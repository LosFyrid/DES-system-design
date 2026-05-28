"""
Focused tests for statistics aggregation.
"""

import sys
import types
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

agent_loader_stub = types.ModuleType("utils.agent_loader")
agent_loader_stub.get_rec_manager = lambda: None
sys.modules["utils.agent_loader"] = agent_loader_stub

from services.statistics_service import StatisticsService


def make_rec(rec_id, measurements):
    return SimpleNamespace(
        recommendation_id=rec_id,
        status="COMPLETED",
        task={"target_material": "battery black mass"},
        experiment_result=SimpleNamespace(
            is_liquid_formed=True,
            measurements=measurements,
        ),
    )


def test_leaching_efficiency_stats_are_grouped_by_measured_element():
    service = StatisticsService()
    recs = [
        make_rec(
            "REC_1",
            [
                {"target_material": "Li", "time_h": 1, "leaching_efficiency": 30.0},
                {"target_material": "Li", "time_h": 3, "leaching_efficiency": 50.0},
                {"target_material": "Co", "time_h": 3, "leaching_efficiency": 20.0},
            ],
        ),
        make_rec(
            "REC_2",
            [
                {"target_material": "Li", "time_h": 1, "leaching_efficiency": 40.0},
                {"target_material": "Co", "time_h": 1, "leaching_efficiency": 10.0},
                {"target_material": "Co", "time_h": 6, "leaching_efficiency": 70.0},
            ],
        ),
    ]

    stats = {
        row.element: row
        for row in service._calculate_leaching_efficiency_by_element(recs)
    }

    assert stats["Li"].measurement_count == 3
    assert stats["Li"].experiment_count == 2
    assert stats["Li"].max_leaching_efficiency_mean == 45.0
    assert stats["Li"].latest_leaching_efficiency_mean == 45.0

    assert stats["Co"].measurement_count == 3
    assert stats["Co"].experiment_count == 2
    assert stats["Co"].max_leaching_efficiency_mean == 45.0
    assert stats["Co"].latest_leaching_efficiency_mean == 45.0
