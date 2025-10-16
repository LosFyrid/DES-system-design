"""
Task Service

Business logic for creating and managing DES formulation tasks.
"""

import logging
from typing import Dict, Any
from datetime import datetime

from models.schemas import TaskRequest, TaskData, FormulationData
from utils.agent_loader import get_agent

logger = logging.getLogger(__name__)


class TaskService:
    """Service for managing DES formulation tasks"""

    def __init__(self):
        """Initialize task service"""
        pass

    def create_task(self, task_request: TaskRequest) -> TaskData:
        """
        Create a DES formulation task and generate recommendation.

        Args:
            task_request: Validated task request

        Returns:
            TaskData with recommendation

        Raises:
            RuntimeError: If agent call fails
        """
        logger.info(f"Creating task for material: {task_request.target_material}")

        try:
            # Get agent instance
            agent = get_agent()

            # Build task dictionary for agent
            task_dict = {
                "description": task_request.description,
                "target_material": task_request.target_material,
                "target_temperature": task_request.target_temperature,
                "constraints": task_request.constraints or {}
            }

            if task_request.task_id:
                task_dict["task_id"] = task_request.task_id

            # Call agent to solve task
            logger.info("Calling DESAgent.solve_task()...")
            result = agent.solve_task(task_dict)

            logger.info(f"Task completed: {result.get('recommendation_id')}")

            # Convert agent result to API response format
            task_data = self._convert_agent_result(result)

            return task_data

        except Exception as e:
            logger.error(f"Failed to create task: {e}", exc_info=True)
            raise RuntimeError(f"Task creation failed: {str(e)}")

    def _convert_agent_result(self, result: Dict[str, Any]) -> TaskData:
        """
        Convert agent result to TaskData format.

        Args:
            result: Agent solve_task() result

        Returns:
            TaskData instance
        """
        # Extract formulation
        formulation_dict = result.get("formulation", {})
        formulation = FormulationData(
            HBD=formulation_dict.get("HBD", "Unknown"),
            HBA=formulation_dict.get("HBA", "Unknown"),
            molar_ratio=formulation_dict.get("molar_ratio", "Unknown")
        )

        # Build TaskData
        task_data = TaskData(
            task_id=result.get("task_id", "unknown"),
            recommendation_id=result.get("recommendation_id", "unknown"),
            formulation=formulation,
            reasoning=result.get("reasoning", "No reasoning provided"),
            confidence=result.get("confidence", 0.5),
            supporting_evidence=result.get("supporting_evidence", []),
            status=result.get("status", "PENDING"),
            created_at=datetime.now().isoformat(),
            memories_used=result.get("memories_used", []),
            next_steps=result.get("next_steps")
        )

        return task_data


# Singleton instance
_service: TaskService = None


def get_task_service() -> TaskService:
    """Get task service singleton"""
    global _service
    if _service is None:
        _service = TaskService()
    return _service
