"""
Feedback Service

Business logic for submitting and processing experimental feedback.
"""

import logging
from typing import Dict, Any
from datetime import datetime

from models.schemas import ExperimentResultRequest, FeedbackData
from utils.agent_loader import get_agent, get_rec_manager

logger = logging.getLogger(__name__)


class FeedbackService:
    """Service for managing experimental feedback"""

    def __init__(self):
        """Initialize feedback service"""
        pass

    def submit_feedback(
        self,
        recommendation_id: str,
        experiment_result: ExperimentResultRequest
    ) -> FeedbackData:
        """
        Submit experimental feedback for a recommendation.

        This method:
        1. Validates the experiment result data
        2. Converts to ExperimentResult (agent format)
        3. Calls agent.submit_experiment_feedback()
        4. Returns processing results

        Args:
            recommendation_id: ID of the recommendation
            experiment_result: Experimental result data

        Returns:
            FeedbackData with processing results

        Raises:
            ValueError: If validation fails or recommendation not found
            RuntimeError: If feedback processing fails
        """
        logger.info(f"Submitting feedback for recommendation: {recommendation_id}")

        try:
            # Validate recommendation exists and is in valid state
            rec_manager = get_rec_manager()
            rec = rec_manager.get_recommendation(recommendation_id)

            if not rec:
                raise ValueError(f"Recommendation {recommendation_id} not found")

            if rec.status == "CANCELLED":
                raise ValueError(
                    f"Cannot submit feedback for cancelled recommendation {recommendation_id}"
                )

            if rec.status == "COMPLETED":
                logger.warning(
                    f"Recommendation {recommendation_id} already has feedback. "
                    "This will update the existing feedback."
                )

            # Validate experiment result
            self._validate_experiment_result(experiment_result)

            # Convert to agent's ExperimentResult format
            from agent.reasoningbank import ExperimentResult

            agent_exp_result = ExperimentResult(
                is_liquid_formed=experiment_result.is_liquid_formed,
                solubility=experiment_result.solubility,
                solubility_unit=experiment_result.solubility_unit,
                properties=experiment_result.properties or {},
                experimenter=experiment_result.experimenter,
                experiment_date=datetime.now().isoformat(),
                notes=experiment_result.notes
            )

            logger.info(
                f"Experiment result: liquid_formed={agent_exp_result.is_liquid_formed}, "
                f"solubility={agent_exp_result.solubility} {agent_exp_result.solubility_unit}"
            )

            # Call agent to process feedback
            agent = get_agent()
            result = agent.submit_experiment_feedback(
                recommendation_id,
                agent_exp_result
            )

            # Check if processing succeeded
            if result["status"] != "success":
                raise RuntimeError(f"Feedback processing failed: {result.get('message')}")

            logger.info(
                f"Feedback processed: performance={result['performance_score']:.1f}/10.0, "
                f"memories={len(result['memories_extracted'])}"
            )

            # Build response data
            feedback_data = FeedbackData(
                recommendation_id=recommendation_id,
                performance_score=result["performance_score"],
                memories_extracted=result["memories_extracted"],
                num_memories=len(result["memories_extracted"])
            )

            return feedback_data

        except ValueError as e:
            # Re-raise validation errors
            raise
        except Exception as e:
            logger.error(f"Failed to submit feedback: {e}", exc_info=True)
            raise RuntimeError(f"Failed to submit feedback: {str(e)}")

    def _validate_experiment_result(self, exp_result: ExperimentResultRequest) -> None:
        """
        Validate experiment result data.

        Args:
            exp_result: Experiment result to validate

        Raises:
            ValueError: If validation fails
        """
        # Check: if liquid formed, solubility must be provided
        if exp_result.is_liquid_formed and exp_result.solubility is None:
            raise ValueError(
                "Solubility is required when is_liquid_formed=True"
            )

        # Check: if not formed, solubility should be None or 0
        if not exp_result.is_liquid_formed and exp_result.solubility and exp_result.solubility > 0:
            logger.warning(
                "Solubility provided but is_liquid_formed=False. "
                "Setting solubility to None."
            )
            exp_result.solubility = None

        # Validate solubility range
        if exp_result.solubility is not None:
            if exp_result.solubility < 0:
                raise ValueError("Solubility cannot be negative")

            if exp_result.solubility > 1000:
                logger.warning(
                    f"Very high solubility value: {exp_result.solubility} {exp_result.solubility_unit}. "
                    "Please verify this is correct."
                )


# Singleton instance
_service: FeedbackService = None


def get_feedback_service() -> FeedbackService:
    """Get feedback service singleton"""
    global _service
    if _service is None:
        _service = FeedbackService()
    return _service
