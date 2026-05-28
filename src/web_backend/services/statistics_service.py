"""
Statistics Service

Business logic for generating system statistics and performance analytics.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import statistics

from models.schemas import (
    StatisticsData,
    SummaryStatistics,
    PerformanceTrendPoint,
    TopFormulation,
    TargetMaterialStats,
    LeachingEfficiencyByElementStats,
)
from utils.agent_loader import get_rec_manager

logger = logging.getLogger(__name__)


class StatisticsService:
    """Service for generating statistics and analytics"""

    def __init__(self):
        """Initialize statistics service"""
        pass

    def get_statistics(self) -> StatisticsData:
        """
        Get comprehensive system statistics.

        Returns:
            StatisticsData with all statistics

        Raises:
            RuntimeError: If statistics generation fails
        """
        logger.info("Generating system statistics (leaching-efficiency based)")

        try:
            # Get all recommendations
            rec_manager = get_rec_manager()
            all_recs = rec_manager.list_recommendations(limit=10000)

            # Calculate summary statistics
            summary = self._calculate_summary(all_recs)

            # Calculate by-material statistics
            by_material = self._calculate_by_material(all_recs)

            # Calculate by-status statistics
            by_status = self._calculate_by_status(all_recs)

            # Calculate performance trend
            performance_trend = self._calculate_performance_trend(all_recs)

            # Calculate top formulations
            top_formulations = self._calculate_top_formulations(all_recs)

            # Calculate target-material stats
            target_material_stats = self._calculate_target_material_stats(all_recs)

            # Calculate leaching stats for each measured element/material
            leaching_efficiency_by_element = self._calculate_leaching_efficiency_by_element(
                all_recs
            )

            # Build statistics data
            stats_data = StatisticsData(
                summary=summary,
                by_material=by_material,
                by_status=by_status,
                performance_trend=performance_trend,
                top_formulations=top_formulations,
                target_material_stats=target_material_stats,
                leaching_efficiency_by_element=leaching_efficiency_by_element,
            )

            logger.info(
                f"Statistics generated: {summary.total_recommendations} total recommendations, "
                f"mean max leaching eff: {summary.max_leaching_efficiency_mean}"
            )

            return stats_data

        except Exception as e:
            logger.error(f"Failed to generate statistics: {e}", exc_info=True)
            raise RuntimeError(f"Failed to generate statistics: {str(e)}")

    def get_performance_trend(
        self,
        start_date: str,
        end_date: str
    ) -> List[PerformanceTrendPoint]:
        """
        Get performance trend for a date range.

        Args:
            start_date: Start date (ISO format YYYY-MM-DD)
            end_date: End date (ISO format YYYY-MM-DD)

        Returns:
            List of PerformanceTrendPoint

        Raises:
            ValueError: If date format invalid
            RuntimeError: If trend calculation fails
        """
        logger.info(f"Calculating performance trend: {start_date} to {end_date}")

        try:
            # Parse dates
            start_dt = datetime.fromisoformat(start_date)
            end_dt = datetime.fromisoformat(end_date)

            if start_dt > end_dt:
                raise ValueError("start_date must be before end_date")

            # Get all recommendations
            rec_manager = get_rec_manager()
            all_recs = rec_manager.list_recommendations(limit=10000)

            # Filter by date range and calculate trend
            filtered_recs = [
                rec for rec in all_recs
                if start_dt <= datetime.fromisoformat(rec.created_at[:10]) <= end_dt
            ]

            trend = self._calculate_performance_trend(filtered_recs)

            logger.info(f"Trend calculated: {len(trend)} data points")

            return trend

        except ValueError as e:
            # Re-raise validation errors
            raise
        except Exception as e:
            logger.error(f"Failed to calculate performance trend: {e}", exc_info=True)
            raise RuntimeError(f"Failed to calculate performance trend: {str(e)}")

    def _calculate_summary(self, all_recs: List[Any]) -> SummaryStatistics:
        """Calculate summary statistics using leaching efficiency"""
        total = len(all_recs)
        pending = sum(1 for rec in all_recs if rec.status == "PENDING")
        completed = sum(1 for rec in all_recs if rec.status == "COMPLETED")
        cancelled = sum(1 for rec in all_recs if rec.status == "CANCELLED")

        # Completed with experiment result
        completed_recs = [rec for rec in all_recs if rec.status == "COMPLETED" and rec.experiment_result]
        max_effs: List[float] = []
        liquid_formed_count = 0
        measurement_rows = []
        for rec in completed_recs:
            exp = rec.experiment_result
            if exp.is_liquid_formed:
                liquid_formed_count += 1
            measurements = getattr(exp, "measurements", []) or []
            measurement_rows.append(len(measurements))
            max_eff = self._get_max_eff(measurements)
            if max_eff is not None:
                max_effs.append(max_eff)

        liquid_formation_rate = (liquid_formed_count / len(completed_recs)) if completed_recs else 0.0
        max_eff_mean = statistics.mean(max_effs) if max_effs else None
        max_eff_median = statistics.median(max_effs) if max_effs else None
        measurement_rows_mean = statistics.mean(measurement_rows) if measurement_rows else None

        return SummaryStatistics(
            total_recommendations=total,
            pending_experiments=pending,
            completed_experiments=completed,
            cancelled=cancelled,
            liquid_formation_rate=liquid_formation_rate,
            max_leaching_efficiency_mean=max_eff_mean,
            max_leaching_efficiency_median=max_eff_median,
            measurement_rows_mean=measurement_rows_mean,
        )

    def _calculate_by_material(self, all_recs: List[Any]) -> Dict[str, int]:
        """Calculate count by material"""
        by_material = defaultdict(int)
        for rec in all_recs:
            material = rec.task.get("target_material", "unknown")
            by_material[material] += 1
        return dict(by_material)

    def _calculate_by_status(self, all_recs: List[Any]) -> Dict[str, int]:
        """Calculate count by status"""
        by_status = defaultdict(int)
        for rec in all_recs:
            by_status[rec.status] += 1
        return dict(by_status)

    def _calculate_performance_trend(self, all_recs: List[Any]) -> List[PerformanceTrendPoint]:
        """Calculate performance trend by date (leaching efficiency based)"""
        by_date = defaultdict(list)
        for rec in all_recs:
            if rec.status == "COMPLETED" and rec.experiment_result:
                date_str = rec.created_at[:10]
                by_date[date_str].append(rec)

        trend_points: List[PerformanceTrendPoint] = []
        for date_str in sorted(by_date.keys()):
            recs = by_date[date_str]
            max_effs = []
            liquid_formed_count = 0
            for rec in recs:
                exp = rec.experiment_result
                if exp.is_liquid_formed:
                    liquid_formed_count += 1
                max_eff = self._get_max_eff(getattr(exp, "measurements", []) or [])
                if max_eff is not None:
                    max_effs.append(max_eff)

            max_mean = statistics.mean(max_effs) if max_effs else None
            max_median = statistics.median(max_effs) if max_effs else None
            liquid_formation_rate = liquid_formed_count / len(recs) if recs else 0.0

            trend_points.append(
                PerformanceTrendPoint(
                    date=date_str,
                    max_leaching_efficiency_mean=max_mean,
                    max_leaching_efficiency_median=max_median,
                    experiment_count=len(recs),
                    liquid_formation_rate=liquid_formation_rate,
                )
            )

        return trend_points

    def _calculate_top_formulations(self, all_recs: List[Any]) -> List[TopFormulation]:
        """Top formulations ranked by mean max leaching efficiency"""
        by_formulation = defaultdict(list)
        for rec in all_recs:
            if rec.status == "COMPLETED" and rec.experiment_result:
                f = rec.formulation
                if "components" in f and f.get("components"):
                    names = [c.get("name", "Unknown") for c in f["components"]]
                    molar_ratio = f.get("molar_ratio", "?")
                    formulation_str = f"{' + '.join(names)} ({molar_ratio})"
                else:
                    hbd = f.get("HBD", "?")
                    hba = f.get("HBA", "?")
                    molar_ratio = f.get("molar_ratio", "?")
                    formulation_str = f"{hbd} : {hba} ({molar_ratio})"
                by_formulation[formulation_str].append(rec)

        formulation_stats = []
        for formulation_str, recs in by_formulation.items():
            max_effs = []
            for rec in recs:
                max_eff = self._get_max_eff(getattr(rec.experiment_result, "measurements", []) or [])
                if max_eff is not None:
                    max_effs.append(max_eff)
            avg_max = statistics.mean(max_effs) if max_effs else None
            formulation_stats.append((formulation_str, avg_max, len(recs)))

        formulation_stats.sort(key=lambda x: (x[1] is not None, x[1] or -1), reverse=True)
        top_10 = formulation_stats[:10]

        return [
            TopFormulation(
                formulation=f_str,
                avg_max_leaching_efficiency=avg_max,
                success_count=count
            )
            for f_str, avg_max, count in top_10
        ]

    def _calculate_target_material_stats(self, all_recs: List[Any]) -> List[TargetMaterialStats]:
        """Grouped leaching statistics by target material"""
        grouped = defaultdict(list)
        for rec in all_recs:
            if rec.status == "COMPLETED" and rec.experiment_result:
                target = rec.task.get("target_material", "unknown")
                grouped[target].append(rec)

        stats_list: List[TargetMaterialStats] = []
        for target, recs in grouped.items():
            liquid_formed = 0
            max_effs = []
            measurement_rows = []
            for rec in recs:
                exp = rec.experiment_result
                if exp.is_liquid_formed:
                    liquid_formed += 1
                measurements = getattr(exp, "measurements", []) or []
                measurement_rows.append(len(measurements))
                max_eff = self._get_max_eff(measurements)
                if max_eff is not None:
                    max_effs.append(max_eff)

            formation_rate = liquid_formed / len(recs) if recs else 0.0
            mean_eff = statistics.mean(max_effs) if max_effs else None
            median_eff = statistics.median(max_effs) if max_effs else None
            p90_eff = statistics.quantiles(max_effs, n=10)[8] if len(max_effs) >= 10 else (max(max_effs) if max_effs else None)
            measurement_rows_mean = statistics.mean(measurement_rows) if measurement_rows else None

            stats_list.append(
                TargetMaterialStats(
                    target_material=target,
                    experiments_total=len(recs),
                    liquid_formation_rate=formation_rate,
                    max_leaching_efficiency_mean=mean_eff,
                    max_leaching_efficiency_median=median_eff,
                    max_leaching_efficiency_p90=p90_eff,
                    measurement_rows_mean=measurement_rows_mean,
                )
            )

        # Sort by mean max leaching efficiency descending, then experiments count
        stats_list.sort(key=lambda s: (s.max_leaching_efficiency_mean is not None, s.max_leaching_efficiency_mean or -1, s.experiments_total), reverse=True)
        return stats_list

    def _calculate_leaching_efficiency_by_element(
        self, all_recs: List[Any]
    ) -> List[LeachingEfficiencyByElementStats]:
        """Grouped leaching statistics by measured target material / element."""
        grouped: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "measurement_values": [],
                "max_values_by_experiment": defaultdict(list),
                "latest_rows_by_experiment": {},
            }
        )

        for rec in all_recs:
            if rec.status != "COMPLETED" or not rec.experiment_result:
                continue

            measurements = getattr(rec.experiment_result, "measurements", []) or []
            for measurement in measurements:
                value = measurement.get("leaching_efficiency")
                if value is None:
                    continue

                element = (
                    measurement.get("target_material")
                    or rec.task.get("target_material")
                    or "unknown"
                )
                element = str(element).strip() or "unknown"
                time_h = measurement.get("time_h")

                data = grouped[element]
                data["measurement_values"].append(value)
                data["max_values_by_experiment"][rec.recommendation_id].append(value)

                latest_row = data["latest_rows_by_experiment"].get(rec.recommendation_id)
                if latest_row is None or self._measurement_time_sort_key(time_h) >= self._measurement_time_sort_key(latest_row["time_h"]):
                    data["latest_rows_by_experiment"][rec.recommendation_id] = {
                        "time_h": time_h,
                        "value": value,
                    }

        stats_list: List[LeachingEfficiencyByElementStats] = []
        for element, data in grouped.items():
            max_values = [
                max(values)
                for values in data["max_values_by_experiment"].values()
                if values
            ]
            latest_values = [
                row["value"]
                for row in data["latest_rows_by_experiment"].values()
                if row.get("value") is not None
            ]

            stats_list.append(
                LeachingEfficiencyByElementStats(
                    element=element,
                    measurement_count=len(data["measurement_values"]),
                    experiment_count=len(max_values),
                    max_leaching_efficiency_mean=statistics.mean(max_values) if max_values else None,
                    max_leaching_efficiency_median=statistics.median(max_values) if max_values else None,
                    max_leaching_efficiency_p90=self._p90(max_values),
                    latest_leaching_efficiency_mean=statistics.mean(latest_values) if latest_values else None,
                )
            )

        stats_list.sort(
            key=lambda s: (
                s.max_leaching_efficiency_mean is not None,
                s.max_leaching_efficiency_mean or -1,
                s.experiment_count,
            ),
            reverse=True,
        )
        return stats_list

    @staticmethod
    def _get_max_eff(measurements: List[Dict[str, Any]]) -> Optional[float]:
        vals = [
            m.get("leaching_efficiency")
            for m in measurements
            if m.get("leaching_efficiency") is not None
        ]
        return max(vals) if vals else None

    @staticmethod
    def _p90(values: List[float]) -> Optional[float]:
        if not values:
            return None
        if len(values) >= 10:
            return statistics.quantiles(values, n=10)[8]
        return max(values)

    @staticmethod
    def _measurement_time_sort_key(time_h: Any) -> float:
        if time_h is None:
            return float("-inf")
        try:
            return float(time_h)
        except (TypeError, ValueError):
            return float("-inf")


# Singleton instance
_service: StatisticsService = None


def get_statistics_service() -> StatisticsService:
    """Get statistics service singleton"""
    global _service
    if _service is None:
        _service = StatisticsService()
    return _service
