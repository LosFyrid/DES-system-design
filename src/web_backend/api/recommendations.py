"""
Recommendation API endpoints

Handles listing, viewing, and managing DES formulation recommendations.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Path, status

from models.schemas import (
    RecommendationListResponse,
    RecommendationDetailResponse,
    BaseResponse,
    ErrorResponse
)
from services.recommendation_service import get_recommendation_service
from utils.response import error_response

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/statistics",
    summary="Get recommendation statistics",
    description="Get lightweight statistics (fast - index only)",
    responses={
        200: {"description": "Statistics retrieved successfully"},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def get_statistics(
    material: Optional[str] = Query(
        None,
        description="Filter by target material",
        example="cellulose"
    )
):
    """
    Get lightweight statistics from index only (no file I/O).

    Query parameters:
    - material: Optional filter by target material

    Returns counts by status: all, GENERATING, PENDING, COMPLETED, FAILED, CANCELLED
    """
    try:
        # Call service
        rec_service = get_recommendation_service()
        stats = rec_service.get_statistics_fast(material=material)

        # Return success response
        return {
            "status": "success",
            "data": stats
        }

    except RuntimeError as e:
        logger.error(f"Failed to get statistics: {e}")
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
    "/",
    response_model=RecommendationListResponse,
    summary="List recommendations",
    description="Get paginated list of recommendations with optional filters",
    responses={
        200: {"description": "Recommendations retrieved successfully", "model": RecommendationListResponse},
        400: {"description": "Invalid parameters", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def list_recommendations(
    status: Optional[str] = Query(
        None,
        description="Filter by status (GENERATING, PENDING, COMPLETED, CANCELLED, FAILED)",
        example="PENDING"
    ),
    material: Optional[str] = Query(
        None,
        description="Filter by target material (e.g., cellulose, lignin)",
        example="cellulose"
    ),
    page: int = Query(
        1,
        ge=1,
        description="Page number (1-indexed)",
        example=1
    ),
    page_size: int = Query(
        20,
        ge=1,
        le=100,
        description="Number of items per page (1-100)",
        example=20
    )
):
    """
    Get paginated list of recommendations.

    Query parameters:
    - status: Filter by recommendation status
    - material: Filter by target material
    - page: Page number (starts from 1)
    - page_size: Items per page (max 100)

    Returns a list of recommendation summaries with pagination info.
    """
    try:
        # Validate status if provided
        valid_statuses = ["GENERATING", "PENDING", "COMPLETED", "CANCELLED", "FAILED"]
        if status and status not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    message=f"Invalid status: {status}. Must be one of: {', '.join(valid_statuses)}"
                )
            )

        # Call service
        rec_service = get_recommendation_service()
        list_data = rec_service.list_recommendations(
            status=status,
            material=material,
            page=page,
            page_size=page_size
        )

        # Return success response
        return RecommendationListResponse(
            status="success",
            data=list_data
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except RuntimeError as e:
        logger.error(f"Failed to list recommendations: {e}")
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
    "/{recommendation_id}",
    response_model=RecommendationDetailResponse,
    summary="Get recommendation detail",
    description="Get detailed information for a specific recommendation",
    responses={
        200: {"description": "Recommendation retrieved successfully", "model": RecommendationDetailResponse},
        404: {"description": "Recommendation not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def get_recommendation_detail(
    recommendation_id: str = Path(
        ...,
        description="Recommendation ID",
        example="REC_20251016_123456_task_001"
    )
):
    """
    Get detailed information for a recommendation.

    Path parameters:
    - recommendation_id: The ID of the recommendation

    Returns complete recommendation details including:
    - Formulation details
    - Reasoning and supporting evidence
    - Full trajectory of generation process
    - Experimental results (if feedback submitted)
    """
    try:
        # Call service
        rec_service = get_recommendation_service()
        detail = rec_service.get_recommendation_detail(recommendation_id)

        # Return success response
        return RecommendationDetailResponse(
            status="success",
            data=detail
        )

    except ValueError as e:
        # Recommendation not found
        logger.warning(f"Recommendation not found: {recommendation_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response(message=str(e))
        )
    except RuntimeError as e:
        logger.error(f"Failed to get recommendation detail: {e}")
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


@router.patch(
    "/{recommendation_id}/cancel",
    response_model=BaseResponse,
    summary="Cancel recommendation",
    description="Cancel a pending recommendation",
    responses={
        200: {"description": "Recommendation cancelled successfully", "model": BaseResponse},
        400: {"description": "Cannot cancel (already completed)", "model": ErrorResponse},
        404: {"description": "Recommendation not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def cancel_recommendation(
    recommendation_id: str = Path(
        ...,
        description="Recommendation ID",
        example="REC_20251016_123456_task_001"
    )
):
    """
    Cancel a recommendation.

    Path parameters:
    - recommendation_id: The ID of the recommendation to cancel

    Only PENDING recommendations can be cancelled.
    Returns an error if the recommendation is already COMPLETED or CANCELLED.
    """
    try:
        # Call service
        rec_service = get_recommendation_service()
        result = rec_service.cancel_recommendation(recommendation_id)

        # Return success response
        return BaseResponse(
            status="success",
            message=f"Recommendation {recommendation_id} cancelled successfully"
        )

    except ValueError as e:
        # Not found or cannot cancel
        error_msg = str(e)
        if "not found" in error_msg.lower():
            logger.warning(f"Recommendation not found: {recommendation_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(message=error_msg)
            )
        else:
            logger.warning(f"Cannot cancel recommendation: {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(message=error_msg)
            )
    except RuntimeError as e:
        logger.error(f"Failed to cancel recommendation: {e}")
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
