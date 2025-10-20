"""
Feedback Service

Business logic for submitting and processing experimental feedback.
Supports both synchronous and asynchronous (background) processing.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import threading

from models.schemas import ExperimentResultRequest, FeedbackData
from utils.agent_loader import get_agent, get_rec_manager

logger = logging.getLogger(__name__)


class FeedbackService:
    """Service for managing experimental feedback"""

    def __init__(self, max_workers: int = 2):
        """
        Initialize feedback service with background processing support.

        Args:
            max_workers: Maximum number of concurrent background tasks
        """
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="feedback")
        self.processing_status = {}  # {rec_id: {"status": "processing|completed|failed", "result": ...}}
        self.status_lock = threading.Lock()
        logger.info(f"Initialized FeedbackService with {max_workers} worker threads")

    def submit_feedback(
        self,
        recommendation_id: str,
        experiment_result: ExperimentResultRequest,
        async_processing: bool = True
    ) -> Dict[str, Any]:
        """
        Submit experimental feedback for a recommendation.

        Args:
            recommendation_id: ID of the recommendation
            experiment_result: Experimental result data
            async_processing: If True, process in background and return immediately
                             If False, process synchronously (blocks until done)

        Returns:
            If async_processing=True: {"status": "accepted", "processing": "started"}
            If async_processing=False: FeedbackData with complete results

        Raises:
            ValueError: If validation fails or recommendation not found
            RuntimeError: If feedback processing fails (sync mode only)
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

            # Decide: async or sync processing
            if async_processing:
                return self._submit_feedback_async(recommendation_id, agent_exp_result)
            else:
                return self._submit_feedback_sync(recommendation_id, agent_exp_result)

        except ValueError as e:
            # Re-raise validation errors
            raise
        except Exception as e:
            logger.error(f"Failed to submit feedback: {e}", exc_info=True)
            raise RuntimeError(f"Failed to submit feedback: {str(e)}")

    def _submit_feedback_sync(self, recommendation_id: str, agent_exp_result) -> FeedbackData:
        """Synchronous feedback processing (blocks until complete)"""
        agent = get_agent()
        result = agent.submit_experiment_feedback(recommendation_id, agent_exp_result)

        # Check if processing succeeded
        if result["status"] != "success":
            raise RuntimeError(f"Feedback processing failed: {result.get('message')}")

        # Log using raw solubility
        solubility_str = (
            f"{result.get('solubility')} {result.get('solubility_unit')}"
            if result.get('solubility') is not None else "N/A"
        )
        logger.info(f"Feedback processed: solubility={solubility_str}, memories={len(result['memories_extracted'])}")

        # Build response data
        return FeedbackData(
            recommendation_id=recommendation_id,
            solubility=result.get("solubility"),
            solubility_unit=result.get("solubility_unit"),
            is_liquid_formed=result.get("is_liquid_formed"),
            memories_extracted=result["memories_extracted"],
            num_memories=len(result["memories_extracted"])
        )

    def _submit_feedback_async(self, recommendation_id: str, agent_exp_result) -> Dict[str, Any]:
        """Asynchronous feedback processing (returns immediately)"""
        # Update recommendation status to PROCESSING
        rec_manager = get_rec_manager()
        rec_manager.update_status(recommendation_id, "PROCESSING")

        # Initialize processing status
        with self.status_lock:
            self.processing_status[recommendation_id] = {
                "status": "processing",
                "started_at": datetime.now().isoformat(),
                "result": None,
                "error": None
            }

        # Submit to thread pool
        future = self.executor.submit(
            self._background_process_feedback,
            recommendation_id,
            agent_exp_result
        )

        logger.info(f"Submitted feedback processing for {recommendation_id} to background thread")

        return {
            "status": "accepted",
            "recommendation_id": recommendation_id,
            "processing": "started",
            "message": "Feedback accepted and processing in background"
        }

    def _background_process_feedback(self, recommendation_id: str, agent_exp_result):
        """Background task to process feedback (runs in thread pool)"""
        try:
            logger.info(f"[Background] Processing feedback for {recommendation_id}")

            # Call agent to process feedback
            agent = get_agent()
            result = agent.submit_experiment_feedback(recommendation_id, agent_exp_result)

            # Check if processing succeeded
            if result["status"] != "success":
                raise RuntimeError(f"Feedback processing failed: {result.get('message')}")

            # Update status to completed
            with self.status_lock:
                self.processing_status[recommendation_id] = {
                    "status": "completed",
                    "started_at": self.processing_status[recommendation_id]["started_at"],
                    "completed_at": datetime.now().isoformat(),
                    "result": {
                        "solubility": result.get("solubility"),
                        "solubility_unit": result.get("solubility_unit"),
                        "is_liquid_formed": result.get("is_liquid_formed"),
                        "memories_extracted": result["memories_extracted"],
                        "num_memories": len(result["memories_extracted"]),
                        "is_update": result.get("is_update", False),
                        "deleted_memories": result.get("deleted_memories", 0)
                    },
                    "error": None
                }

            logger.info(f"[Background] Completed feedback processing for {recommendation_id}")

        except Exception as e:
            logger.error(f"[Background] Failed to process feedback for {recommendation_id}: {e}", exc_info=True)

            # Update recommendation status to FAILED
            rec_manager = get_rec_manager()
            rec_manager.update_status(recommendation_id, "FAILED")

            # Update processing status
            with self.status_lock:
                self.processing_status[recommendation_id] = {
                    "status": "failed",
                    "started_at": self.processing_status[recommendation_id]["started_at"],
                    "failed_at": datetime.now().isoformat(),
                    "result": None,
                    "error": str(e)
                }

    def check_processing_status(self, recommendation_id: str) -> Optional[Dict[str, Any]]:
        """
        Check the processing status of a feedback submission.

        Args:
            recommendation_id: Recommendation ID to check

        Returns:
            Dict with status info, or None if not found

        Example:
            {
                "status": "processing|completed|failed",
                "started_at": "2025-10-20T14:30:00",
                "completed_at": "2025-10-20T14:30:45",  # if completed
                "result": {...},  # if completed
                "error": "..."    # if failed
            }
        """
        with self.status_lock:
            return self.processing_status.get(recommendation_id)

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
