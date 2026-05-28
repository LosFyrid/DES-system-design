"""
Memory Extractor for ReasoningBank

This module extracts generalizable reasoning strategies from agent trajectories,
converting raw execution histories into structured memory items.
"""

from collections import defaultdict
from typing import List, Callable, Literal, Dict, Any, Optional, Tuple
import json
import logging

from .memory import MemoryItem, Trajectory
from .experience_analysis import (
    build_experience_profile,
    compact_profile_for_metadata,
)
from .experience_history_tools import ExperienceHistoryTools, dumps_tool_result
from ..utils.json_extract import loads_json_from_text
from ..prompts import (
    SUCCESS_EXTRACTION_PROMPT,
    FAILURE_EXTRACTION_PROMPT,
    PARALLEL_MATTS_PROMPT,
    EXPERIMENT_EXTRACTION_PROMPT,
    format_trajectory_for_extraction,
    parse_extracted_memories,
)

logger = logging.getLogger(__name__)


def _to_dict(obj: Any) -> Dict[str, Any]:
    """Safely convert pydantic/dataclass/dict-ish objects to dict."""
    if obj is None:
        return {}
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return obj
    try:
        return dict(obj)  # type: ignore[arg-type]
    except Exception:
        return {}


def format_experiment_for_llm(experiment_result) -> str:
    """
    Reformat raw experimental feedback into an LLM-friendly textual structure.

    - Shows experimental conditions (temperature, solid–liquid mass ratio as g:g)
    - Groups leaching efficiency measurements by target material and orders by time
    - Includes optional properties and notes without pre-aggregating or summarizing
    """
    lines: List[str] = []

    # Overview
    status_text = "Yes (liquid formed)" if experiment_result.is_liquid_formed else "No (not formed)"
    lines.append("**Experimental Result Overview**")
    lines.append(f"- DES liquid phase formed: {status_text}")
    lines.append("")

    # Conditions
    conditions = _to_dict(getattr(experiment_result, "conditions", {}))
    solid_liquid_ratio = _to_dict(conditions.get("solid_liquid_ratio", {}))

    temp_C = conditions.get("temperature_C")
    solid_mass_g = solid_liquid_ratio.get("solid_mass_g")
    # Treat liquid_volume_ml value as liquid mass in grams for presentation (per product decision)
    liquid_mass_g = solid_liquid_ratio.get("liquid_volume_ml")
    ratio_text = solid_liquid_ratio.get("ratio_text")

    lines.append("**Experimental Conditions**")
    if temp_C is not None:
        lines.append(f"- Temperature: {temp_C} °C")

    if solid_mass_g is not None or liquid_mass_g is not None or ratio_text:
        if solid_mass_g is not None and liquid_mass_g is not None:
            lines.append(f"- Solid–liquid mass ratio: {solid_mass_g} g : {liquid_mass_g} g")
        elif ratio_text:
            lines.append(f"- Solid–liquid mass ratio: {ratio_text}")
        else:
            if solid_mass_g is not None:
                lines.append(f"- Solid mass: {solid_mass_g} g")
            if liquid_mass_g is not None:
                lines.append(f"- Liquid mass: {liquid_mass_g} g")

        if ratio_text and (solid_mass_g is not None or liquid_mass_g is not None):
            lines.append(f"  (Text ratio: {ratio_text})")
    else:
        lines.append("- (No explicit experimental conditions provided)")

    lines.append("")

    # Measurements grouped by target material
    measurements = getattr(experiment_result, "measurements", []) or []
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for m in measurements:
        target = m.get("target_material") or "Unknown"
        grouped[target].append(m)

    lines.append("**Leaching Measurements (time series by target)**")
    if not grouped:
        lines.append("- (No leaching measurements provided)")
    else:
        for target, rows in grouped.items():
            rows_sorted = sorted(
                rows,
                key=lambda r: (
                    r.get("time_h") is None,
                    r.get("time_h") if r.get("time_h") is not None else 0.0,
                ),
            )
            lines.append(f"- Target material: {target}")
            for row in rows_sorted:
                t = row.get("time_h")
                eff = row.get("leaching_efficiency")
                unit = row.get("unit") or "%"
                obs = row.get("observation")

                time_text = "time = N/A" if t is None else f"{t} h"
                if eff is None:
                    if obs:
                        eff_text = f"N/A (note: {obs})"
                    else:
                        eff_text = "N/A"
                else:
                    eff_text = f"{eff} {unit}"

                lines.append(f"  - {time_text}: {eff_text}")
            lines.append("")  # blank line between targets

    # Additional properties
    properties = getattr(experiment_result, "properties", {}) or {}
    if properties:
        lines.append("**Additional Measured Properties**")
        for k, v in properties.items():
            lines.append(f"- {k}: {v}")
        lines.append("")

    # Notes
    notes = getattr(experiment_result, "notes", "")
    if notes:
        lines.append("**Experimental Notes**")
        lines.append(notes)
        lines.append("")

    return "\n".join(lines).strip()


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
        config: Optional[Dict[str, Any]] = None,
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
        self.config = config or {}
        self.last_extraction_audit: Dict[str, Any] = {}
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
            llm_output = self._call_extractor_llm(prompt)
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
            llm_output = self._call_extractor_llm(prompt)
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
        self,
        trajectory: Trajectory,
        experiment_result,
        history_tools: Optional[ExperienceHistoryTools] = None,
    ) -> List[MemoryItem]:
        """
        Extract memory items from experimental feedback (NEW: Replaces binary classification).

        Instead of extracting from "success" or "failure", this method extracts
        data-driven insights from actual experimental measurements.

        Extraction Focus:
        - Formulation-condition-performance mappings
        - Quantitative relationships (e.g., "ChCl:Urea 1:2 → 6.5 g/L leaching efficiency")
        - Component effects on performance
        - Molar ratio effects
        - Temperature effects on DES formation

        Args:
            trajectory: Trajectory object
            experiment_result: ExperimentResult object with lab measurements

        Returns:
            List of extracted MemoryItem objects (up to max_items_per_trajectory)
        """
        extractor_cfg = self._extractor_config()
        react_enabled = bool(extractor_cfg.get("react_enabled", True))

        profile = build_experience_profile(
            trajectory=trajectory,
            experiment_result=experiment_result,
            history_recommendations=[],
            config=extractor_cfg,
        )
        metadata_profile = compact_profile_for_metadata(profile)

        if react_enabled:
            memories, audit = self._extract_from_experiment_react(
                trajectory=trajectory,
                experiment_result=experiment_result,
                history_tools=history_tools,
                profile=profile or {},
            )
            self.last_extraction_audit = audit
            if memories:
                logger.info(
                    "Extracted %s memories from experiment via ReAct extractor",
                    len(memories),
                )
                return memories

            logger.warning(
                "ReAct experiment extractor produced 0 memories; falling back to deterministic summary."
            )
            fallback_memories = self._build_deterministic_experiment_memories(
                trajectory=trajectory,
                experiment_result=experiment_result,
                profile=profile or {},
                audit=audit,
            )
            self.last_extraction_audit = {
                **audit,
                "fallback_used": True,
                "fallback_count": len(fallback_memories),
            }
            return fallback_memories

        # Build experiment extraction prompt (legacy path)
        prompt = self._build_experiment_extraction_prompt(trajectory, experiment_result)

        # Call LLM
        try:
            llm_output = self._call_extractor_llm(prompt)
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
                    is_from_success=experiment_result.is_liquid_formed,
                    metadata={
                        "target_material": trajectory.metadata.get("target_material"),
                        "extraction_type": "experiment_feedback",
                        "is_liquid_formed": experiment_result.is_liquid_formed,
                        "measurements": experiment_result.measurements,
                        "extractor_profile": metadata_profile,
                    },
                )
                memories.append(memory)
                logger.info(f"Extracted experimental memory: {memory.title}")
            except ValueError as e:
                logger.warning(f"Failed to create memory item: {e}")
                continue

        # Log using summary of measurements
        if experiment_result.measurements:
            max_eff = max(
                [m.get("leaching_efficiency") or 0 for m in experiment_result.measurements if m.get("leaching_efficiency") is not None],
                default=0
            )
            solubility_str = f"max_leaching_efficiency={max_eff}%"
        else:
            solubility_str = "N/A (no measurements)"
        logger.info(
            f"Extracted {len(memories)} memories from experiment "
            f"({solubility_str})"
        )

        return memories

    def _extractor_config(self) -> Dict[str, Any]:
        cfg = self.config.get("extractor", {}) if isinstance(self.config, dict) else {}
        return cfg if isinstance(cfg, dict) else {}

    def _call_extractor_llm(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        response_format: Optional[Dict[str, Any]] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        cfg = self._extractor_config()
        reasoning_effort = str(cfg.get("structured_reasoning_effort", "xhigh"))
        temperature = cfg.get("structured_temperature")
        if temperature is not None:
            temperature = float(temperature)
        effective_max_tokens = int(
            max_tokens
            or cfg.get("structured_max_tokens")
            or cfg.get("max_tokens")
            or 16000
        )

        if hasattr(self.llm_client, "chat"):
            try:
                kwargs = {
                    "prompt": prompt,
                    "system_prompt": system_prompt,
                    "max_tokens": effective_max_tokens,
                    "reasoning_effort": reasoning_effort,
                    "response_format": response_format,
                }
                if temperature is not None:
                    kwargs["temperature"] = temperature
                return self.llm_client.chat(**kwargs)
            except TypeError:
                logger.debug("Extractor llm_client.chat rejected kwargs; using callable fallback")

        return self.llm_client(prompt)

    @staticmethod
    def _json_response_format(name: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": name,
                "strict": True,
                "schema": schema,
            },
        }

    @staticmethod
    def _react_action_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "reasoning": {"type": "string"},
                "action": {
                    "type": "string",
                    "enum": [
                        "search_similar_memories",
                        "search_memories",
                        "list_memory_field_values",
                        "search_recommendations",
                        "list_recommendation_field_values",
                        "inspect_recommendation",
                        "finish",
                    ],
                },
                "args": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer"},
                        "where": {"type": "string"},
                        "field": {"type": "string"},
                        "component": {"type": "string"},
                        "performance_band": {"type": "string"},
                        "include_pending": {"type": "boolean"},
                        "limit": {"type": "integer"},
                        "order_by": {"type": "string"},
                        "scope": {"type": "string", "enum": ["comparable", "all"]},
                        "recommendation_id": {"type": "string"},
                    },
                    "required": [
                        "query",
                        "top_k",
                        "where",
                        "field",
                        "component",
                        "performance_band",
                        "include_pending",
                        "limit",
                        "order_by",
                        "scope",
                        "recommendation_id",
                    ],
                },
            },
            "required": ["reasoning", "action", "args"],
        }

    @staticmethod
    def _final_payload_schema() -> Dict[str, Any]:
        component_implication = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "component": {"type": "string"},
                "action": {
                    "type": "string",
                    "enum": [
                        "promote",
                        "use_with_rationale",
                        "avoid_unless_changed",
                        "insufficient_evidence",
                        "neutral",
                    ],
                },
                "rationale": {"type": "string"},
            },
            "required": ["component", "action", "rationale"],
        }
        memory_item = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "content": {"type": "string"},
                "memory_kind": {
                    "type": "string",
                    "enum": [
                        "performance_mapping",
                        "relative_benchmark",
                        "component_signal",
                        "boundary_condition",
                        "negative_constraint",
                    ],
                },
                "evidence_strength": {
                    "type": "string",
                    "enum": ["high", "moderate", "weak"],
                },
                "performance_band": {
                    "type": "string",
                    "enum": [
                        "high",
                        "moderate",
                        "low",
                        "no_liquid",
                        "formation_only",
                    ],
                },
                "component_implications": {
                    "type": "array",
                    "items": component_implication,
                },
                "source_evidence": {"type": "array", "items": {"type": "string"}},
                "avoid_absolute_language": {"type": "boolean"},
            },
            "required": [
                "title",
                "description",
                "content",
                "memory_kind",
                "evidence_strength",
                "performance_band",
                "component_implications",
                "source_evidence",
                "avoid_absolute_language",
            ],
        }
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "memories": {"type": "array", "items": memory_item},
                "audit": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "history_used": {"type": "boolean"},
                        "notes": {"type": "string"},
                    },
                    "required": ["history_used", "notes"],
                },
            },
            "required": ["memories", "audit"],
        }

    def _build_experiment_react_prompt(
        self,
        *,
        trajectory: Trajectory,
        experiment_result: Any,
        profile: Dict[str, Any],
        tool_results: List[Dict[str, Any]],
        actions_taken: List[str],
        can_finish: bool,
        history_tools: Optional[ExperienceHistoryTools],
    ) -> str:
        trajectory_text = format_trajectory_for_extraction(
            {
                "steps": trajectory.steps,
                "tool_calls": trajectory.metadata.get("tool_calls", []),
            }
        )
        exp_summary = format_experiment_for_llm(experiment_result)
        tools_text = history_tools.tool_specs_text() if history_tools else "No history tools are available; use finish."
        results_text = json.dumps(tool_results[-5:], ensure_ascii=False, indent=2)
        if len(results_text) > 30000:
            results_text = results_text[-30000:]

        finish_rule = (
            "You may choose finish now."
            if can_finish
            else "Do NOT choose finish yet. You must inspect required memory and recommendation history first."
        )

        return f"""You are an agent that extracts durable experimental experience memories for a DES recommendation system.

Your job is not to summarize every measurement. Create a few memories that future recommendation agents can use correctly.

Critical requirements:
- Use historical context, not only the current record.
- Avoid redundant memories that all say the same metric in different words.
- Do not over-emphasize conditions that are constant across history, such as a common solid-liquid ratio.
- Preserve relative merit: a low or moderate result can still be useful if it improves over worse baselines.
- Avoid absolute language such as "not suitable" unless history and evidence justify it.
- Convert weak/low evidence into calibrated reuse constraints, e.g. "reuse only with a mechanistic change" rather than a blanket ban.
- Final output must be JSON following the provided schema.
- Prefer field-value listing tools before structured filtering when you are unsure how a field is represented.
- Use semantic memory search for fuzzy similarity and structured memory search for exact metadata checks.

{tools_text}

{finish_rule}

Task:
- description: {trajectory.task_description}
- target_material: {trajectory.metadata.get("target_material")}
- target_temperature_C: {trajectory.metadata.get("target_temperature")}

Proposed formulation:
{trajectory.final_result.get("formulation", {}) if isinstance(trajectory.final_result, dict) else trajectory.final_result}

Agent trajectory:
{trajectory_text}

Current experiment:
{exp_summary}

Actions taken so far: {actions_taken}

Recent tool results:
{results_text}

Return ONLY a JSON object with:
{{
  "reasoning": "...",
  "action": "search_similar_memories|search_memories|list_memory_field_values|search_recommendations|list_recommendation_field_values|inspect_recommendation|finish",
  "args": {{
    "query": "",
    "top_k": 5,
    "where": "",
    "field": "",
    "component": "",
    "performance_band": "",
    "include_pending": false,
    "limit": 8,
    "order_by": "-created_at",
    "scope": "comparable",
    "recommendation_id": ""
  }}
}}
"""

    def _build_final_extraction_prompt(
        self,
        *,
        trajectory: Trajectory,
        experiment_result: Any,
        profile: Dict[str, Any],
        tool_results: List[Dict[str, Any]],
    ) -> str:
        exp_summary = format_experiment_for_llm(experiment_result)
        results_text = json.dumps(tool_results, ensure_ascii=False, indent=2)
        if len(results_text) > 48000:
            results_text = results_text[-48000:]

        return f"""Extract final DES experimental memories as strict JSON.

Memory quality rules:
- Produce at most {self.max_items_per_trajectory} memories.
- Prefer 1-2 discriminative memories over 3 redundant ones.
- Every memory must include concrete quantitative evidence from the current experiment.
- Every memory must include how history changes the interpretation when history is available.
- If performance is low/moderate, state what remains useful and what should require caution.
- If a field was constant across history, do not make it the central lesson.
- Do not claim a formulation or component is categorically unsuitable unless the evidence shows that across comparable history.

Task:
- description: {trajectory.task_description}
- target_material: {trajectory.metadata.get("target_material")}
- target_temperature_C: {trajectory.metadata.get("target_temperature")}

Proposed formulation:
{trajectory.final_result.get("formulation", {}) if isinstance(trajectory.final_result, dict) else trajectory.final_result}

Current experiment:
{exp_summary}

Tool evidence:
{results_text}

Return ONLY JSON matching:
{{
  "memories": [
    {{
      "title": "...",
      "description": "...",
      "content": "...",
      "memory_kind": "performance_mapping|relative_benchmark|component_signal|boundary_condition|negative_constraint",
      "evidence_strength": "high|moderate|weak",
      "performance_band": "high|moderate|low|no_liquid|formation_only",
      "component_implications": [
        {{"component": "...", "action": "promote|use_with_rationale|avoid_unless_changed|insufficient_evidence|neutral", "rationale": "..."}}
      ],
      "source_evidence": ["..."],
      "avoid_absolute_language": true
    }}
  ],
  "audit": {{"history_used": true, "notes": "..."}}
}}
"""

    def _default_tool_args(
        self,
        action: str,
        *,
        trajectory: Trajectory,
        profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        if action == "search_similar_memories":
            query = " ".join(
                [
                    str(trajectory.task_description or ""),
                    str(profile.get("formulation_summary") or ""),
                    str(trajectory.metadata.get("target_material") or ""),
                    "leaching efficiency experiment feedback component performance",
                ]
            ).strip()
            return {"query": query, "top_k": 6}
        if action == "search_memories":
            return {"where": "", "limit": 12, "order_by": "-created_at"}
        if action == "list_memory_field_values":
            return {"field": "metadata.performance_band", "limit": 50}
        if action == "search_recommendations":
            return {"limit": 8, "include_pending": False, "scope": "comparable", "order_by": "-created_at"}
        if action == "list_recommendation_field_values":
            return {"field": "performance_band", "limit": 50, "include_pending": False, "scope": "comparable"}
        return {}

    def _parse_react_action(self, output: str) -> Dict[str, Any]:
        data = loads_json_from_text(output)
        if not isinstance(data, dict):
            return {"reasoning": "Failed to parse action JSON", "action": "finish", "args": {}}
        action = str(data.get("action") or "finish").strip()
        args = data.get("args")
        if not isinstance(args, dict):
            args = {}
        return {
            "reasoning": str(data.get("reasoning") or "").strip(),
            "action": action,
            "args": args,
        }

    def _parse_final_payload(self, output: str) -> Dict[str, Any]:
        data = loads_json_from_text(output)
        if isinstance(data, dict):
            return data

        # Backward-compatible Markdown fallback: useful if response_format was ignored.
        memories = parse_extracted_memories(output or "")
        return {"memories": memories, "audit": {"parser": "markdown_fallback"}}

    def _extract_from_experiment_react(
        self,
        *,
        trajectory: Trajectory,
        experiment_result: Any,
        history_tools: Optional[ExperienceHistoryTools],
        profile: Dict[str, Any],
    ) -> Tuple[List[MemoryItem], Dict[str, Any]]:
        cfg = self._extractor_config()
        max_steps = int(cfg.get("react_max_steps", 20))
        require_history_tools = bool(cfg.get("require_history_tools", True))
        required = ["search_similar_memories", "search_recommendations"] if history_tools and require_history_tools else []

        tool_results: List[Dict[str, Any]] = []
        actions_taken: List[str] = []
        audit: Dict[str, Any] = {
            "mode": "react",
            "required_history_tools": required,
            "tool_calls": [],
            "fallback_used": False,
        }

        # Keep deterministic profiling out of the ReAct evidence stream. It remains
        # available for metadata/fallback, but extraction conclusions should come
        # from raw experiment text plus explicit history queries.
        audit["profile"] = compact_profile_for_metadata(profile)

        for _step in range(max_steps):
            missing = [name for name in required if name not in actions_taken]
            can_finish = not missing
            prompt = self._build_experiment_react_prompt(
                trajectory=trajectory,
                experiment_result=experiment_result,
                profile=profile,
                tool_results=tool_results,
                actions_taken=actions_taken,
                can_finish=can_finish,
                history_tools=history_tools,
            )
            try:
                action_output = self._call_extractor_llm(
                    prompt,
                    system_prompt="You are a careful ReAct extraction planner. Return strict JSON only.",
                    response_format=self._json_response_format(
                        "experience_extractor_action_v1",
                        self._react_action_schema(),
                    ),
                    max_tokens=int(cfg.get("react_action_max_tokens", 16000)),
                )
            except Exception as e:
                logger.warning("Experiment extractor ReAct action call failed: %s", e)
                break

            action_data = self._parse_react_action(action_output)
            action = action_data.get("action", "finish")
            args = action_data.get("args", {})

            if missing and (
                action == "finish"
                or action in actions_taken
                or action not in {
                    "search_similar_memories",
                    "search_memories",
                    "list_memory_field_values",
                    "search_recommendations",
                    "list_recommendation_field_values",
                    "inspect_recommendation",
                }
            ):
                action = missing[0]
                args = self._default_tool_args(action, trajectory=trajectory, profile=profile)

            if action == "finish":
                break

            if history_tools is None:
                break

            if not isinstance(args, dict):
                args = {}
            default_args = self._default_tool_args(
                action, trajectory=trajectory, profile=profile
            )
            for key, value in default_args.items():
                raw_value = args.get(key)
                if raw_value is None or raw_value == "" or raw_value == 0:
                    args[key] = value

            result = history_tools.run(
                action,
                args,
                trajectory=trajectory,
                experiment_result=experiment_result,
            )
            tool_record = {
                "tool": action,
                "args": args,
                "reasoning": action_data.get("reasoning", ""),
                "result": result,
            }
            tool_results.append(tool_record)
            actions_taken.append(action)
            audit["tool_calls"].append(
                {
                    "tool": action,
                    "args": args,
                    "ok": bool(result.get("ok")) if isinstance(result, dict) else False,
                    "result_size": len(dumps_tool_result(result, max_chars=100000)),
                }
            )

        try:
            final_output = self._call_extractor_llm(
                self._build_final_extraction_prompt(
                    trajectory=trajectory,
                    experiment_result=experiment_result,
                    profile=profile,
                    tool_results=tool_results,
                ),
                system_prompt="You extract calibrated DES experiment memories. Return strict JSON only.",
                response_format=self._json_response_format(
                    "experience_extractor_final_v1",
                    self._final_payload_schema(),
                ),
                max_tokens=int(cfg.get("final_max_tokens", 16000)),
            )
        except Exception as e:
            logger.error("Experiment extractor final call failed: %s", e)
            audit["error"] = str(e)
            return [], audit

        payload = self._parse_final_payload(final_output)
        audit["actions_taken"] = actions_taken
        audit["final_payload_audit"] = payload.get("audit") if isinstance(payload, dict) else {}
        audit["history_used"] = any(
            a in actions_taken for a in (
                "search_similar_memories",
                "search_memories",
                "list_memory_field_values",
                "search_recommendations",
                "list_recommendation_field_values",
                "inspect_recommendation",
            )
        )

        return self._memory_items_from_payload(
            payload=payload,
            trajectory=trajectory,
            experiment_result=experiment_result,
            profile=profile,
            audit=audit,
            extraction_type="experiment_feedback_react",
        ), audit

    def _memory_items_from_payload(
        self,
        *,
        payload: Dict[str, Any],
        trajectory: Trajectory,
        experiment_result: Any,
        profile: Dict[str, Any],
        audit: Dict[str, Any],
        extraction_type: str,
    ) -> List[MemoryItem]:
        if not isinstance(payload, dict):
            return []
        raw_items = payload.get("memories")
        if not isinstance(raw_items, list):
            return []

        perf = profile.get("performance_profile") if isinstance(profile, dict) else {}
        if not isinstance(perf, dict):
            perf = {}
        band = str(perf.get("performance_band") or "")
        relative = str(perf.get("relative_interpretation") or "")

        # Binary compatibility: the legacy field now tracks whether the DES
        # formed a liquid. Use performance metadata for strength/usefulness.
        is_positive_signal = band in {"high", "moderate"} or relative in {
            "best_so_far",
            "partial_positive",
        }
        is_liquid_formed = bool(getattr(experiment_result, "is_liquid_formed", False))

        memories: List[MemoryItem] = []
        seen_titles: set[str] = set()
        for data in raw_items[: self.max_items_per_trajectory]:
            if not isinstance(data, dict):
                continue
            title = str(data.get("title") or "").strip()
            description = str(data.get("description") or "").strip()
            content = str(data.get("content") or "").strip()
            if not title or not description or not content:
                continue
            title_key = title.lower()
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)

            try:
                memory = MemoryItem(
                    title=title,
                    description=description,
                    content=content,
                    source_task_id=trajectory.task_id,
                    is_from_success=is_liquid_formed,
                    metadata={
                        "target_material": trajectory.metadata.get("target_material"),
                        "extraction_type": extraction_type,
                        "is_liquid_formed": experiment_result.is_liquid_formed,
                        "measurements": experiment_result.measurements,
                        "extractor_profile": compact_profile_for_metadata(profile),
                        "performance_band": data.get("performance_band") or band,
                        "relative_interpretation": relative,
                        "is_positive_signal": is_positive_signal,
                        "memory_kind": data.get("memory_kind"),
                        "evidence_strength": data.get("evidence_strength"),
                        "component_implications": data.get("component_implications") or [],
                        "source_evidence": data.get("source_evidence") or [],
                        "avoid_absolute_language": bool(data.get("avoid_absolute_language", True)),
                        "extractor_audit": {
                            "mode": audit.get("mode"),
                            "history_used": audit.get("history_used"),
                            "tool_calls": audit.get("tool_calls", []),
                            "fallback_used": audit.get("fallback_used", False),
                        },
                    },
                )
                memories.append(memory)
                logger.info("Extracted experimental memory: %s", memory.title)
            except ValueError as e:
                logger.warning("Failed to create memory item: %s", e)

        return memories

    def _build_deterministic_experiment_memories(
        self,
        *,
        trajectory: Trajectory,
        experiment_result: Any,
        profile: Dict[str, Any],
        audit: Dict[str, Any],
    ) -> List[MemoryItem]:
        perf = profile.get("performance_profile") if isinstance(profile, dict) else {}
        perf = perf if isinstance(perf, dict) else {}
        stats = perf.get("measurement_stats") if isinstance(perf.get("measurement_stats"), dict) else {}
        implications = (
            profile.get("recommendation_implications")
            if isinstance(profile.get("recommendation_implications"), dict)
            else {}
        )
        band = str(perf.get("performance_band") or "formation_only")
        relative = str(perf.get("relative_interpretation") or "no_history")
        max_val = stats.get("max_value")
        avg_val = stats.get("avg_value")
        unit = stats.get("unit") or "%"
        formulation_summary = str(profile.get("formulation_summary") or "Tested DES formulation")
        low_info = implications.get("low_information_fields") or []
        require_change = implications.get("requires_mechanistic_change_before_reuse") or []

        if relative == "partial_positive":
            qualifier = "has relative merit versus weaker history"
        elif relative == "best_so_far":
            qualifier = "is the best comparable result available in history"
        elif band == "low":
            qualifier = "is a low-performance result and should not be reused blindly"
        elif band == "moderate":
            qualifier = "is a moderate result that may guide refinement"
        elif band == "high":
            qualifier = "is a strong positive experimental signal"
        else:
            qualifier = "mainly records formation and boundary-condition evidence"

        condition_note = ""
        if low_info:
            condition_note = (
                " Conditions such as "
                + ", ".join(str(x) for x in low_info)
                + " appear low-information across comparable history and should not be the main lesson."
            )

        reuse_note = ""
        if require_change:
            reuse_note = (
                " Reusing "
                + ", ".join(str(x) for x in require_change[:5])
                + " should require a mechanistic or compositional change."
            )

        data = {
            "memories": [
                {
                    "title": f"{formulation_summary} gives max {max_val} {unit} ({band})",
                    "description": (
                        f"This experiment {qualifier} with max leaching efficiency {max_val} {unit} "
                        f"and average {avg_val} {unit}."
                    ),
                    "content": (
                        f"Under the submitted conditions, {formulation_summary} formed a liquid={experiment_result.is_liquid_formed} "
                        f"and reached max leaching efficiency {max_val} {unit} (average {avg_val} {unit}). "
                        f"The calibrated interpretation is `{band}` with relative context `{relative}`, so future agents should preserve "
                        f"the quantitative evidence while avoiding a blanket good/bad label.{condition_note}{reuse_note}"
                    ),
                    "memory_kind": "performance_mapping",
                    "evidence_strength": "moderate",
                    "performance_band": band,
                    "component_implications": [],
                    "source_evidence": [
                        f"max_leaching_efficiency={max_val}{unit}",
                        f"relative_interpretation={relative}",
                    ],
                    "avoid_absolute_language": True,
                }
            ],
            "audit": {"parser": "deterministic_fallback"},
        }
        fallback_audit = {**audit, "mode": "deterministic_fallback", "history_used": audit.get("history_used", False)}
        return self._memory_items_from_payload(
            payload=data,
            trajectory=trajectory,
            experiment_result=experiment_result,
            profile=profile,
            audit=fallback_audit,
            extraction_type="experiment_feedback_deterministic_fallback",
        )

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

        # Build rich experiment summary for LLM (no aggregation, just formatting)
        exp_summary = format_experiment_for_llm(experiment_result)

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
