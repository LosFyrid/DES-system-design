"""
Task API endpoints

Handles task creation for DES formulation recommendations.
"""

import logging
from fastapi import APIRouter, HTTPException, status

from models.schemas import (
    TaskRequest,
    TaskResponse,
    TaskData,
    ErrorResponse
)
from services.task_service import get_task_service
from utils.response import success_response, error_response

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create DES formulation task",
    description="Submit a task to generate DES formulation recommendation",
    responses={
        201: {"description": "Task created successfully", "model": TaskResponse},
        400: {"description": "Validation error", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def create_task(task_request: TaskRequest):
    """
    Create a DES formulation task and generate recommendation.

    This endpoint:
    1. Validates the task request
    2. Calls DESAgent to generate formulation
    3. Creates a PENDING recommendation record
    4. Returns the recommendation for user review

    Request body should include:
    - description: Task description (10-1000 chars)
    - target_material: Material to dissolve (e.g., cellulose)
    - target_temperature: Target temperature in Celsius (optional, default: 25)
    - constraints: Additional constraints (optional dictionary)
    """
    try:
        # Call task service
        task_service = get_task_service()
        task_data = task_service.create_task(task_request)

        # Return success response
        return TaskResponse(
            status="success",
            message=f"Recommendation {task_data.recommendation_id} created successfully",
            data=task_data
        )

    except RuntimeError as e:
        logger.error(f"Task creation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                message=str(e)
            )
        )
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                message=f"Unexpected error: {str(e)}"
            )
        )
