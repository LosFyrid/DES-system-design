"""
LLM-as-a-Judge for evaluating trajectory outcomes

This module uses an LLM to determine whether a DES formulation task
was successfully completed or failed, without requiring ground-truth labels.
"""

from typing import Dict, Optional, Callable
import logging

from .memory import Trajectory
from ..prompts import JUDGE_PROMPT, parse_judge_output

logger = logging.getLogger(__name__)


class LLMJudge:
    """
    LLM-based evaluator for trajectory outcomes.

    Uses an LLM to classify trajectories as SUCCESS or FAILURE based on:
    - Chemical validity of the proposed formulation
    - Scientific soundness of the reasoning
    - Satisfaction of task constraints

    This enables test-time learning without ground-truth labels.

    Attributes:
        llm_client: Function or object that calls the LLM
        temperature: Sampling temperature (0.0 for deterministic)
    """

    def __init__(self, llm_client: Callable[[str], str], temperature: float = 0.0):
        """
        Initialize LLMJudge.

        Args:
            llm_client: Function that takes a prompt (str) and returns LLM response (str)
            temperature: Sampling temperature (default 0.0 for deterministic evaluation)
        """
        self.llm_client = llm_client
        self.temperature = temperature
        logger.info(f"Initialized LLMJudge with temperature={temperature}")

    def evaluate(self, trajectory: Trajectory) -> Dict:
        """
        Evaluate whether a trajectory resulted in success or failure.

        Args:
            trajectory: Trajectory object containing task info and agent actions

        Returns:
            Dict with keys:
                - status: "success" or "failure"
                - thoughts: Judge's reasoning
                - reason: Explanation if failure (empty string if success)
                - confidence: Optional confidence score (not implemented yet)
        """
        # Build prompt
        prompt = self._build_judge_prompt(trajectory)

        # Call LLM
        try:
            llm_output = self.llm_client(prompt)
            logger.debug(f"Judge LLM output: {llm_output[:200]}...")
        except Exception as e:
            logger.error(f"LLM call failed during judging: {e}")
            # Default to failure if judge cannot run
            return {
                "status": "failure",
                "thoughts": f"Judge error: {str(e)}",
                "reason": "Unable to evaluate due to LLM error",
            }

        # Parse output
        result = parse_judge_output(llm_output)

        logger.info(
            f"Task {trajectory.task_id} evaluated as {result['status'].upper()}"
        )

        return result

    def _build_judge_prompt(self, trajectory: Trajectory) -> str:
        """
        Build the judge prompt from a trajectory.

        Args:
            trajectory: Trajectory object

        Returns:
            Formatted prompt string
        """
        # Extract task information
        task_desc = trajectory.task_description
        metadata = trajectory.metadata

        # Extract result information
        final_result = trajectory.final_result
        hbd = final_result.get("formulation", {}).get("HBD", "N/A")
        hba = final_result.get("formulation", {}).get("HBA", "N/A")
        molar_ratio = final_result.get("formulation", {}).get("molar_ratio", "N/A")
        solubility = final_result.get("predicted_solubility", "N/A")
        reasoning = final_result.get("reasoning", "N/A")

        # Format trajectory
        trajectory_text = self._format_trajectory_steps(trajectory.steps)

        # Fill prompt template
        prompt = JUDGE_PROMPT.format(
            task_description=task_desc,
            target_material=metadata.get("target_material", "N/A"),
            target_temperature=metadata.get("target_temperature", "N/A"),
            constraints=metadata.get("constraints", {}),
            trajectory=trajectory_text,
            hbd=hbd,
            hba=hba,
            molar_ratio=molar_ratio,
            solubility=solubility,
            reasoning=reasoning,
        )

        return prompt

    def _format_trajectory_steps(self, steps: list) -> str:
        """
        Format trajectory steps for display in prompt.

        Args:
            steps: List of step dicts

        Returns:
            Formatted string
        """
        if not steps:
            return "No steps recorded"

        formatted = ""
        for i, step in enumerate(steps, 1):
            formatted += f"\n### Step {i}\n"

            if "action" in step:
                formatted += f"**Action:** {step['action']}\n"

            if "reasoning" in step:
                formatted += f"**Reasoning:** {step['reasoning']}\n"

            if "tool" in step and "tool_output" in step:
                formatted += f"**Tool Used:** {step['tool']}\n"
                formatted += f"**Tool Output:** {step['tool_output'][:200]}...\n"

        return formatted


# Example usage
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)

    # Mock LLM client
    def mock_llm(prompt: str) -> str:
        # Simple mock that returns SUCCESS for demo
        return """Thoughts: The agent proposed a valid DES formulation with choline chloride (HBA) and urea (HBD) at a 1:2 molar ratio, which is a well-known eutectic system. The reasoning considers hydrogen bonding, which is appropriate for cellulose dissolution.
Status: SUCCESS"""

    # Create judge
    judge = LLMJudge(llm_client=mock_llm, temperature=0.0)

    # Create sample trajectory
    trajectory = Trajectory(
        task_id="task_001",
        task_description="Design DES for dissolving cellulose at room temperature",
        steps=[
            {
                "action": "Query CoreRAG for H-bond theory",
                "reasoning": "Need to understand hydrogen bonding for cellulose",
                "tool": "CoreRAG",
                "tool_output": "Cellulose has strong H-bond accepting groups...",
            },
            {
                "action": "Propose formulation",
                "reasoning": "Choline chloride + urea forms strong H-bonds",
            },
        ],
        outcome="unknown",  # Will be determined by judge
        final_result={
            "formulation": {
                "HBD": "Urea",
                "HBA": "Choline chloride",
                "molar_ratio": "1:2",
            },
            "predicted_solubility": "High",
            "reasoning": "Strong H-bond network suitable for cellulose",
        },
        metadata={
            "target_material": "cellulose",
            "target_temperature": 25,
            "constraints": {},
        },
    )

    # Evaluate
    result = judge.evaluate(trajectory)

    print("\n" + "=" * 60)
    print("JUDGE EVALUATION RESULT")
    print("=" * 60)
    print(f"Status: {result['status'].upper()}")
    print(f"Thoughts: {result['thoughts']}")
    if result.get("reason"):
        print(f"Reason: {result['reason']}")
