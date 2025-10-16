"""
Statistics API endpoints

Handles system statistics and performance analytics.
"""

import logging
from fastapi import APIRouter, HTTPException, Query, status

from models.schemas import (
    StatisticsResponse,
    PerformanceTrendResponse,
    ErrorResponse
)
from services.statistics_service import get_statistics_service
from utils.response import error_response

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/",
    response_model=StatisticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get system statistics",
    description="Get comprehensive system statistics and performance analytics",
    responses={
        200: {"description": "Statistics retrieved successfully", "model": StatisticsResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def get_statistics():
    """
    Get comprehensive system statistics.

    Returns overall system performance metrics including:
    - **Summary**: Total recommendations, pending/completed/cancelled counts,
      average performance score, liquid formation success rate
    - **By Material**: Distribution of recommendations by target material
    - **By Status**: Distribution of recommendations by status (PENDING/COMPLETED/CANCELLED)
    - **Performance Trend**: Daily aggregated performance metrics
      (avg solubility, avg performance score, experiment count, liquid formation rate)
    - **Top Formulations**: Top 10 performing formulations ranked by average performance score

    **Example Response**:
    ```json
    {
      "status": "success",
      "message": "Statistics retrieved successfully. Total: 150 recommendations, Avg Performance: 7.2/10.0",
      "data": {
        "summary": {
          "total_recommendations": 150,
          "pending_experiments": 45,
          "completed_experiments": 95,
          "cancelled": 10,
          "average_performance_score": 7.2,
          "liquid_formation_rate": 0.89
        },
        "by_material": {
          "cellulose": 80,
          "lignin": 45,
          "chitin": 25
        },
        "by_status": {
          "PENDING": 45,
          "COMPLETED": 95,
          "CANCELLED": 10
        },
        "performance_trend": [
          {
            "date": "2025-10-14",
            "avg_solubility": 6.8,
            "avg_performance_score": 7.1,
            "experiment_count": 12,
            "liquid_formation_rate": 0.92
          },
          {
            "date": "2025-10-15",
            "avg_solubility": 7.3,
            "avg_performance_score": 7.5,
            "experiment_count": 15,
            "liquid_formation_rate": 0.87
          }
        ],
        "top_formulations": [
          {
            "formulation": "Choline chloride:Urea (1:2)",
            "avg_performance": 8.5,
            "success_count": 12
          },
          {
            "formulation": "Choline chloride:Glycerol (1:2)",
            "avg_performance": 8.2,
            "success_count": 8
          }
        ]
      }
    }
    ```

    **Notes**:
    - Performance score ranges from 0-10 (based on solubility and liquid formation)
    - Liquid formation rate is the percentage of experiments that successfully formed liquid DES
    - Performance trend includes only completed experiments
    - Top formulations are calculated from completed experiments and ranked by average performance
    """
    try:
        # Get statistics from service
        stats_service = get_statistics_service()
        stats_data = stats_service.get_statistics()

        # Return success response
        return StatisticsResponse(
            status="success",
            message=(
                f"Statistics retrieved successfully. "
                f"Total: {stats_data.summary.total_recommendations} recommendations, "
                f"Avg Performance: {stats_data.summary.average_performance_score:.1f}/10.0"
            ),
            data=stats_data
        )

    except RuntimeError as e:
        logger.error(f"Failed to retrieve statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(message=str(e))
        )

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(message=f"Unexpected error: {str(e)}")
        )


@router.get(
    "/performance-trend",
    response_model=PerformanceTrendResponse,
    status_code=status.HTTP_200_OK,
    summary="Get performance trend",
    description="Get performance trend for a specific date range",
    responses={
        200: {"description": "Performance trend retrieved successfully", "model": PerformanceTrendResponse},
        400: {"description": "Validation error", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def get_performance_trend(
    start_date: str = Query(
        ...,
        description="Start date in ISO format (YYYY-MM-DD)",
        example="2025-10-01"
    ),
    end_date: str = Query(
        ...,
        description="End date in ISO format (YYYY-MM-DD)",
        example="2025-10-16"
    )
):
    """
    Get performance trend for a specific date range.

    Returns daily aggregated performance metrics for completed experiments within the date range.

    **Query Parameters**:
    - **start_date** (required): Start date in ISO format (YYYY-MM-DD)
    - **end_date** (required): End date in ISO format (YYYY-MM-DD)

    **Example Request**:
    ```
    GET /api/v1/statistics/performance-trend?start_date=2025-10-01&end_date=2025-10-16
    ```

    **Example Response**:
    ```json
    {
      "status": "success",
      "message": "Performance trend retrieved: 15 data points from 2025-10-01 to 2025-10-16",
      "data": [
        {
          "date": "2025-10-01",
          "avg_solubility": 5.8,
          "avg_performance_score": 6.5,
          "experiment_count": 8,
          "liquid_formation_rate": 0.88
        },
        {
          "date": "2025-10-02",
          "avg_solubility": 6.2,
          "avg_performance_score": 6.9,
          "experiment_count": 10,
          "liquid_formation_rate": 0.90
        }
      ]
    }
    ```

    **Notes**:
    - Only completed experiments are included in the trend
    - Dates with no completed experiments are omitted from results
    - start_date must be before or equal to end_date
    - Performance metrics are calculated as daily averages

    **Validation Rules**:
    - Date format must be YYYY-MM-DD (ISO format)
    - start_date must be before or equal to end_date
    """
    try:
        # Get performance trend from service
        stats_service = get_statistics_service()
        trend_data = stats_service.get_performance_trend(start_date, end_date)

        # Return success response
        return PerformanceTrendResponse(
            status="success",
            message=(
                f"Performance trend retrieved: {len(trend_data)} data points "
                f"from {start_date} to {end_date}"
            ),
            data=trend_data
        )

    except ValueError as e:
        # Validation error
        error_msg = str(e)
        logger.warning(f"Validation error: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(message=error_msg)
        )

    except RuntimeError as e:
        logger.error(f"Failed to retrieve performance trend: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(message=str(e))
        )

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(message=f"Unexpected error: {str(e)}")
        )
