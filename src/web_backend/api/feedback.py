"""
Feedback API endpoints

Handles experimental feedback submission for recommendations.
"""

import logging
from fastapi import APIRouter, HTTPException, status

from models.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    ErrorResponse
)
from services.feedback_service import get_feedback_service
from utils.response import error_response

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/",
    response_model=FeedbackResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit experimental feedback",
    description="Submit real laboratory experiment results for a recommendation",
    responses={
        200: {"description": "Feedback processed successfully", "model": FeedbackResponse},
        400: {"description": "Validation error", "model": ErrorResponse},
        404: {"description": "Recommendation not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def submit_feedback(feedback_request: FeedbackRequest):
    """
    Submit experimental feedback for a recommendation.

    This endpoint completes the async feedback loop:
    1. User provides real laboratory measurements
    2. System validates the experimental data
    3. System updates recommendation status to COMPLETED
    4. System extracts data-driven memories from the experiment
    5. System consolidates new memories into ReasoningBank

    **Required fields**:
    - recommendation_id: ID of the recommendation to update
    - experiment_result.is_liquid_formed: Whether DES formed liquid phase
    - experiment_result.solubility: Solubility (required if liquid formed)

    **Optional fields**:
    - experiment_result.properties: Additional measurements (dict)
    - experiment_result.experimenter: Who performed the experiment
    - experiment_result.notes: Experimental notes

    **Validation rules**:
    - If is_liquid_formed=True, solubility MUST be provided
    - If is_liquid_formed=False, solubility should be None/0
    - Solubility must be non-negative

    **Example request**:
    ```json
    {
      "recommendation_id": "REC_20251016_123456_task_001",
      "experiment_result": {
        "is_liquid_formed": true,
        "solubility": 6.5,
        "solubility_unit": "g/L",
        "properties": {
          "viscosity": "45 cP",
          "density": "1.15 g/mL",
          "appearance": "clear liquid"
        },
        "experimenter": "Dr. Zhang",
        "notes": "DES formed successfully at room temperature. Clear homogeneous liquid observed."
      }
    }
    ```

    **Returns**:
    - Performance score (0-10) based on experimental results
    - Number of memories extracted
    - Titles of extracted memories
    """
    try:
        # Call feedback service
        feedback_service = get_feedback_service()
        feedback_data = feedback_service.submit_feedback(
            feedback_request.recommendation_id,
            feedback_request.experiment_result
        )

        # Return success response
        return FeedbackResponse(
            status="success",
            message=(
                f"Experimental feedback processed successfully. "
                f"Performance: {feedback_data.performance_score:.1f}/10.0. "
                f"Extracted {feedback_data.num_memories} new memories."
            ),
            data=feedback_data
        )

    except ValueError as e:
        # Validation error or not found
        error_msg = str(e)
        if "not found" in error_msg.lower():
            logger.warning(f"Recommendation not found: {feedback_request.recommendation_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(message=error_msg)
            )
        else:
            logger.warning(f"Validation error: {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(message=error_msg)
            )

    except RuntimeError as e:
        logger.error(f"Failed to process feedback: {e}")
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
