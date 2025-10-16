"""
Memory Extractor for ReasoningBank

This module extracts generalizable reasoning strategies from agent trajectories,
converting raw execution histories into structured memory items.
"""

from typing import List, Callable, Literal
import logging

from .memory import MemoryItem, Trajectory
from ..prompts import (
    SUCCESS_EXTRACTION_PROMPT,
    FAILURE_EXTRACTION_PROMPT,
    PARALLEL_MATTS_PROMPT,
    EXPERIMENT_EXTRACTION_PROMPT,
    format_trajectory_for_extraction,
    parse_extracted_memories,
)

logger = logging.getLogger(__name__)


class MemoryExtractor:
    """
    Extracts reasoning strategies from agent trajectories.

    The extractor uses different strategies for successful vs failed trajectories:
    - Success: Extract validated strategies that led to correct formulations
    - Failure: Extract pitfalls and preventative strategies

    Attributes:
        llm_client: Function or object that calls the LLM
        temperature: Sampling temperature for extraction (default 1.0 for diversity)
        max_items_per_trajectory: Maximum memory items to extract from one trajectory
    """

    def __init__(
        self,
        llm_client: Callable[[str], str],
        temperature: float = 1.0,
        max_items_per_trajectory: int = 3,
    ):
        """
        Initialize MemoryExtractor.

        Args:
            llm_client: Function that takes a prompt (str) and returns LLM response (str)
            temperature: Sampling temperature (higher = more diverse memories)
            max_items_per_trajectory: Max memory items per trajectory
        """
        self.llm_client = llm_client
        self.temperature = temperature
        self.max_items_per_trajectory = max_items_per_trajectory
        logger.info(
            f"Initialized MemoryExtractor with temperature={temperature}, "
            f"max_items={max_items_per_trajectory}"
        )

    def extract_from_trajectory(
        self, trajectory: Trajectory, outcome: Literal["success", "failure"]
    ) -> List[MemoryItem]:
        """
        Extract memory items from a single trajectory.

        Args:
            trajectory: Trajectory object
            outcome: Whether the trajectory was successful or failed

        Returns:
            List of extracted MemoryItem objects (up to max_items_per_trajectory)
        """
        # Build extraction prompt
        prompt = self._build_extraction_prompt(trajectory, outcome)

        # Call LLM
        try:
            llm_output = self.llm_client(prompt)
            logger.debug(f"Extractor LLM output: {llm_output[:200]}...")
        except Exception as e:
            logger.error(f"LLM call failed during extraction: {e}")
            return []

        # Parse memories
        memories_data = parse_extracted_memories(llm_output)

        # Convert to MemoryItem objects
        memories = []
        for data in memories_data[: self.max_items_per_trajectory]:
            try:
                memory = MemoryItem(
                    title=data.get("title", "Untitled"),
                    description=data.get("description", ""),
                    content=data.get("content", ""),
                    source_task_id=trajectory.task_id,
                    is_from_success=(outcome == "success"),
                    metadata={
                        "target_material": trajectory.metadata.get("target_material"),
                        "extraction_type": "single_trajectory",
                    },
                )
                memories.append(memory)
                logger.info(f"Extracted memory: {memory.title}")
            except ValueError as e:
                logger.warning(f"Failed to create memory item: {e}")
                continue

        logger.info(
            f"Extracted {len(memories)} memories from {outcome} trajectory "
            f"(task_id={trajectory.task_id})"
        )

        return memories

    def extract_from_multiple_trajectories(
        self, trajectories: List[Trajectory], outcomes: List[str]
    ) -> List[MemoryItem]:
        """
        Extract memories by comparing multiple trajectories (MaTTS parallel scaling).

        Uses self-contrast to identify consistent success patterns and common pitfalls.

        Args:
            trajectories: List of Trajectory objects for the same task
            outcomes: List of outcomes ("success" or "failure") for each trajectory

        Returns:
            List of extracted MemoryItem objects (up to 5)
        """
        if not trajectories:
            logger.warning("No trajectories provided for extraction")
            return []

        # Build parallel extraction prompt
        prompt = self._build_parallel_prompt(trajectories, outcomes)

        # Call LLM
        try:
            llm_output = self.llm_client(prompt)
            logger.debug(f"Parallel extractor LLM output: {llm_output[:200]}...")
        except Exception as e:
            logger.error(f"LLM call failed during parallel extraction: {e}")
            return []

        # Parse memories
        memories_data = parse_extracted_memories(llm_output)

        # Convert to MemoryItem objects (up to 5 for parallel)
        memories = []
        task_id = trajectories[0].task_id if trajectories else "unknown"

        for data in memories_data[:5]:
            try:
                memory = MemoryItem(
                    title=data.get("title", "Untitled"),
                    description=data.get("description", ""),
                    content=data.get("content", ""),
                    source_task_id=task_id,
                    is_from_success=True,  # Parallel memories are synthesized
                    metadata={
                        "extraction_type": "parallel_matts",
                        "num_trajectories": len(trajectories),
                    },
                )
                memories.append(memory)
                logger.info(f"Extracted parallel memory: {memory.title}")
            except ValueError as e:
                logger.warning(f"Failed to create memory item: {e}")
                continue

        logger.info(
            f"Extracted {len(memories)} memories from {len(trajectories)} trajectories "
            f"using self-contrast"
        )

        return memories

    def _build_extraction_prompt(self, trajectory: Trajectory, outcome: str) -> str:
        """
        Build extraction prompt for a single trajectory.

        Args:
            trajectory: Trajectory object
            outcome: "success" or "failure"

        Returns:
            Formatted prompt string
        """
        # Choose template based on outcome
        if outcome == "success":
            template = SUCCESS_EXTRACTION_PROMPT
        else:
            template = FAILURE_EXTRACTION_PROMPT

        # Format trajectory
        trajectory_text = format_trajectory_for_extraction(
            {
                "steps": trajectory.steps,
                "tool_calls": trajectory.metadata.get("tool_calls", []),
            }
        )

        # Extract task info
        metadata = trajectory.metadata
        final_result = trajectory.final_result

        # Format constraints
        constraints = metadata.get("constraints", {})
        constraints_text = ", ".join([f"{k}: {v}" for k, v in constraints.items()])

        # Build prompt
        prompt_data = {
            "task_description": trajectory.task_description,
            "target_material": metadata.get("target_material", "N/A"),
            "target_temperature": metadata.get("target_temperature", "N/A"),
            "constraints": constraints_text if constraints_text else "None",
            "trajectory": trajectory_text,
            "final_result": str(final_result),
        }

        # Add failure-specific field
        if outcome == "failure":
            prompt_data["failure_reason"] = metadata.get("failure_reason", "Unknown")

        prompt = template.format(**prompt_data)

        return prompt

    def _build_parallel_prompt(
        self, trajectories: List[Trajectory], outcomes: List[str]
    ) -> str:
        """
        Build prompt for parallel trajectory extraction.

        Args:
            trajectories: List of Trajectory objects
            outcomes: List of outcomes

        Returns:
            Formatted prompt string
        """
        # Format all trajectories
        trajectories_text = ""
        for i, (traj, outcome) in enumerate(zip(trajectories, outcomes), 1):
            traj_text = format_trajectory_for_extraction(
                {"steps": traj.steps, "tool_calls": traj.metadata.get("tool_calls", [])}
            )

            trajectories_text += f"\n## Trajectory {i} ({outcome.upper()})\n"
            trajectories_text += f"**Final Result:** {traj.final_result}\n"
            trajectories_text += traj_text
            trajectories_text += "\n---\n"

        # Get task description from first trajectory
        task_desc = trajectories[0].task_description

        # Build prompt
        prompt = PARALLEL_MATTS_PROMPT.format(
            task_description=task_desc, trajectories=trajectories_text
        )

        return prompt

    def extract_from_experiment(
        self, trajectory: Trajectory, experiment_result
    ) -> List[MemoryItem]:
        """
        Extract memory items from experimental feedback (NEW: Replaces binary classification).

        Instead of extracting from "success" or "failure", this method extracts
        data-driven insights from actual experimental measurements.

        Extraction Focus:
        - Formulation-condition-performance mappings
        - Quantitative relationships (e.g., "ChCl:Urea 1:2 → 6.5 g/L solubility")
        - Component effects on performance
        - Molar ratio effects
        - Temperature effects on DES formation

        Args:
            trajectory: Trajectory object
            experiment_result: ExperimentResult object with lab measurements

        Returns:
            List of extracted MemoryItem objects (up to max_items_per_trajectory)
        """
        # Build experiment extraction prompt
        prompt = self._build_experiment_extraction_prompt(trajectory, experiment_result)

        # Call LLM
        try:
            llm_output = self.llm_client(prompt)
            logger.debug(f"Experiment extractor LLM output: {llm_output[:200]}...")
        except Exception as e:
            logger.error(f"LLM call failed during experiment extraction: {e}")
            return []

        # Parse memories
        memories_data = parse_extracted_memories(llm_output)

        # Convert to MemoryItem objects
        memories = []
        for data in memories_data[: self.max_items_per_trajectory]:
            try:
                memory = MemoryItem(
                    title=data.get("title", "Untitled"),
                    description=data.get("description", ""),
                    content=data.get("content", ""),
                    source_task_id=trajectory.task_id,
                    is_from_success=True,  # Not used in new design (keep for compatibility)
                    metadata={
                        "target_material": trajectory.metadata.get("target_material"),
                        "extraction_type": "experiment_feedback",
                        "performance_score": experiment_result.get_performance_score(),
                    },
                )
                memories.append(memory)
                logger.info(f"Extracted experimental memory: {memory.title}")
            except ValueError as e:
                logger.warning(f"Failed to create memory item: {e}")
                continue

        logger.info(
            f"Extracted {len(memories)} memories from experiment "
            f"(performance_score: {experiment_result.get_performance_score():.1f}/10.0)"
        )

        return memories

    def _build_experiment_extraction_prompt(
        self, trajectory: Trajectory, experiment_result
    ) -> str:
        """
        Build extraction prompt for experimental feedback.

        Args:
            trajectory: Trajectory object
            experiment_result: ExperimentResult object

        Returns:
            Formatted prompt string
        """
        # Format trajectory
        trajectory_text = format_trajectory_for_extraction(
            {
                "steps": trajectory.steps,
                "tool_calls": trajectory.metadata.get("tool_calls", []),
            }
        )

        # Extract task info
        metadata = trajectory.metadata
        final_result = trajectory.final_result

        # Build experiment results summary
        exp_summary = f"""**Experimental Results:**
- DES Formation: {"✓ Yes (liquid formed)" if experiment_result.is_liquid_formed else "✗ No (remained solid/semi-solid)"}
- Solubility: {experiment_result.solubility} {experiment_result.solubility_unit if experiment_result.solubility is not None else "N/A (DES not formed)"}
- Performance Score: {experiment_result.get_performance_score():.1f}/10.0
"""

        # Add optional properties
        if experiment_result.properties:
            exp_summary += "\n**Additional Properties:**\n"
            for key, value in experiment_result.properties.items():
                exp_summary += f"- {key}: {value}\n"

        if experiment_result.notes:
            exp_summary += f"\n**Experimental Notes:** {experiment_result.notes}\n"

        # Build prompt using EXPERIMENT_EXTRACTION_PROMPT template
        prompt = EXPERIMENT_EXTRACTION_PROMPT.format(
            task_description=trajectory.task_description,
            target_material=metadata.get("target_material", "N/A"),
            target_temperature=metadata.get("target_temperature", "N/A"),
            trajectory=trajectory_text,
            formulation=str(final_result.get("formulation", {})),
            experiment_summary=exp_summary,
        )

        return prompt


# Example usage
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)

    # Mock LLM client
    def mock_llm(prompt: str) -> str:
        # Simple mock that returns a sample memory
        return """
# Memory Item 1
## Title: Prioritize Hydrogen Bond Network Analysis
## Description: When designing DES for polar materials, analyze H-bond strength first
## Content: For dissolving polar polymers like cellulose, the hydrogen bond donating/accepting capability of DES components is the primary factor. Use CoreRAG to retrieve H-bond parameters before exploring molar ratios.

# Memory Item 2
## Title: Verify Component Compatibility Early
## Description: Check for known incompatibilities before proposing formulations
## Content: Certain HBD-HBA combinations are known to cause decomposition or phase separation. Query LargeRAG for reported incompatibilities early in the design process to avoid invalid formulations.
"""

    # Create extractor
    extractor = MemoryExtractor(llm_client=mock_llm, temperature=1.0)

    # Create sample trajectory
    trajectory = Trajectory(
        task_id="task_001",
        task_description="Design DES for dissolving cellulose at room temperature",
        steps=[
            {
                "action": "Query CoreRAG",
                "reasoning": "Need H-bond theory",
                "tool": "CoreRAG",
                "tool_output": "H-bond parameters retrieved",
            },
            {"action": "Propose formulation", "reasoning": "Based on H-bond analysis"},
        ],
        outcome="success",
        final_result={
            "formulation": {
                "HBD": "Urea",
                "HBA": "Choline chloride",
                "molar_ratio": "1:2",
            }
        },
        metadata={
            "target_material": "cellulose",
            "target_temperature": 25,
            "tool_calls": [],
        },
    )

    # Extract memories
    memories = extractor.extract_from_trajectory(trajectory, outcome="success")

    print("\n" + "=" * 60)
    print("EXTRACTED MEMORIES")
    print("=" * 60)
    for memory in memories:
        print(f"\n{memory.to_detailed_string()}")
