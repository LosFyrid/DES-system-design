"""
Statistics Service

Business logic for generating system statistics and performance analytics.
"""

import logging
from typing import Dict, List, Any
from datetime import datetime, timedelta
from collections import defaultdict

from models.schemas import (
    StatisticsData,
    SummaryStatistics,
    PerformanceTrendPoint,
    TopFormulation
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
        logger.info("Generating system statistics")

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

            # Build statistics data
            stats_data = StatisticsData(
                summary=summary,
                by_material=by_material,
                by_status=by_status,
                performance_trend=performance_trend,
                top_formulations=top_formulations
            )

            logger.info(
                f"Statistics generated: {summary.total_recommendations} total recommendations, "
                f"avg performance: {summary.average_performance_score:.2f}"
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
        """Calculate summary statistics"""
        total = len(all_recs)
        pending = sum(1 for rec in all_recs if rec.status == "PENDING")
        completed = sum(1 for rec in all_recs if rec.status == "COMPLETED")
        cancelled = sum(1 for rec in all_recs if rec.status == "CANCELLED")

        # Calculate average performance score (only for completed)
        completed_recs = [rec for rec in all_recs if rec.status == "COMPLETED" and rec.experiment_result]
        if completed_recs:
            avg_performance = sum(
                rec.experiment_result.get_performance_score()
                for rec in completed_recs
            ) / len(completed_recs)

            # Calculate liquid formation rate
            liquid_formed_count = sum(
                1 for rec in completed_recs
                if rec.experiment_result.is_liquid_formed
            )
            liquid_formation_rate = liquid_formed_count / len(completed_recs)
        else:
            avg_performance = 0.0
            liquid_formation_rate = 0.0

        return SummaryStatistics(
            total_recommendations=total,
            pending_experiments=pending,
            completed_experiments=completed,
            cancelled=cancelled,
            average_performance_score=avg_performance,
            liquid_formation_rate=liquid_formation_rate
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
        """Calculate performance trend by date"""
        # Group by date
        by_date = defaultdict(list)
        for rec in all_recs:
            if rec.status == "COMPLETED" and rec.experiment_result:
                # Extract date (YYYY-MM-DD)
                date_str = rec.created_at[:10]
                by_date[date_str].append(rec)

        # Calculate statistics for each date
        trend_points = []
        for date_str in sorted(by_date.keys()):
            recs = by_date[date_str]

            # Calculate averages
            solubilities = [
                rec.experiment_result.solubility
                for rec in recs
                if rec.experiment_result.solubility is not None
            ]
            avg_solubility = sum(solubilities) / len(solubilities) if solubilities else 0.0

            performances = [
                rec.experiment_result.get_performance_score()
                for rec in recs
            ]
            avg_performance = sum(performances) / len(performances) if performances else 0.0

            liquid_formed_count = sum(
                1 for rec in recs
                if rec.experiment_result.is_liquid_formed
            )
            liquid_formation_rate = liquid_formed_count / len(recs) if recs else 0.0

            trend_point = PerformanceTrendPoint(
                date=date_str,
                avg_solubility=avg_solubility,
                avg_performance_score=avg_performance,
                experiment_count=len(recs),
                liquid_formation_rate=liquid_formation_rate
            )
            trend_points.append(trend_point)

        return trend_points

    def _calculate_top_formulations(self, all_recs: List[Any]) -> List[TopFormulation]:
        """Calculate top performing formulations"""
        # Group by formulation string
        by_formulation = defaultdict(list)
        for rec in all_recs:
            if rec.status == "COMPLETED" and rec.experiment_result:
                # Build formulation string
                f = rec.formulation
                formulation_str = f"{f.get('HBA', 'Unknown')}:{f.get('HBD', 'Unknown')} ({f.get('molar_ratio', 'Unknown')})"
                by_formulation[formulation_str].append(rec)

        # Calculate average performance for each formulation
        formulation_stats = []
        for formulation_str, recs in by_formulation.items():
            performances = [
                rec.experiment_result.get_performance_score()
                for rec in recs
            ]
            avg_performance = sum(performances) / len(performances) if performances else 0.0

            formulation_stats.append((
                formulation_str,
                avg_performance,
                len(recs)
            ))

        # Sort by average performance (descending) and take top 10
        formulation_stats.sort(key=lambda x: x[1], reverse=True)
        top_10 = formulation_stats[:10]

        # Build TopFormulation objects
        top_formulations = [
            TopFormulation(
                formulation=f_str,
                avg_performance=avg_perf,
                success_count=count
            )
            for f_str, avg_perf, count in top_10
        ]

        return top_formulations


# Singleton instance
_service: StatisticsService = None


def get_statistics_service() -> StatisticsService:
    """Get statistics service singleton"""
    global _service
    if _service is None:
        _service = StatisticsService()
    return _service
