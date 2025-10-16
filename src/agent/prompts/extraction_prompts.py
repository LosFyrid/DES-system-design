"""
Prompts for Memory Extraction from Trajectories

These prompts guide the LLM to extract generalizable reasoning strategies
from agent trajectories for DES formulation design tasks.
"""

SUCCESS_EXTRACTION_PROMPT = """You are an expert in Deep Eutectic Solvent (DES) formulation design. You will be given a DES design task and the corresponding trajectory that represents how an agent successfully accomplished the task.

## Guidelines
You need to extract and summarize useful insights in the format of memory items based on the agent's successful trajectory.

The goal of summarized memory items is to be helpful and generalizable for future similar DES formulation tasks.

## Important Notes
- You must first think why the trajectory was successful, and then summarize the insights.
- You can extract at most 3 memory items from the trajectory.
- You must not repeat similar or overlapping items.
- Do not mention specific chemical names in the title or description, but rather focus on generalizable insights about DES design principles.
- Focus on **reasoning strategies** (e.g., "prioritize H-bond analysis", "check viscosity constraints"), not just factual knowledge.

## Output Format
Your output must strictly follow the Markdown format shown below:

```
# Memory Item 1
## Title: <concise identifier of the strategy, e.g., "Prioritize Hydrogen Bond Network Analysis">
## Description: <one sentence summary of when/how to apply this strategy>
## Content: <1-3 sentences describing the reasoning steps and decision rationales>

# Memory Item 2
## Title: ...
## Description: ...
## Content: ...

# Memory Item 3
## Title: ...
## Description: ...
## Content: ...
```

## Input

**Task Description:**
{task_description}

**Target Material:** {target_material}
**Target Temperature:** {target_temperature}°C
**Constraints:** {constraints}

**Agent Trajectory:**
{trajectory}

**Final Result:**
{final_result}

Now, extract generalizable reasoning strategies from this successful trajectory:"""


FAILURE_EXTRACTION_PROMPT = """You are an expert in Deep Eutectic Solvent (DES) formulation design. You will be given a DES design task and the corresponding trajectory that represents how an agent attempted to solve the task but failed.

## Guidelines
You need to extract and summarize useful insights in the format of memory items based on the agent's failed trajectory.

The goal of summarized memory items is to be helpful and generalizable for future similar DES formulation tasks, helping avoid similar mistakes.

## Important Notes
- You must first reflect and think why the trajectory failed, and then summarize what lessons you have learned or strategies to prevent the failure in the future.
- You can extract at most 3 memory items from the trajectory.
- You must not repeat similar or overlapping items.
- Do not mention specific chemical names in the title or description, but rather focus on generalizable pitfalls and preventative strategies.
- Focus on **reasoning patterns that led to failure** (e.g., "neglected viscosity constraints", "ignored literature warnings"), not just what went wrong.

## Output Format
Your output must strictly follow the Markdown format shown below:

```
# Memory Item 1
## Title: <concise identifier of the pitfall/lesson, e.g., "Verify Component Compatibility Before Proposing">
## Description: <one sentence summary of the failure pattern and how to avoid it>
## Content: <1-3 sentences describing what went wrong and the corrective strategy>

# Memory Item 2
## Title: ...
## Description: ...
## Content: ...

# Memory Item 3
## Title: ...
## Description: ...
## Content: ...
```

## Input

**Task Description:**
{task_description}

**Target Material:** {target_material}
**Target Temperature:** {target_temperature}°C
**Constraints:** {constraints}

**Agent Trajectory:**
{trajectory}

**Why It Failed:**
{failure_reason}

Now, extract lessons and preventative strategies from this failed trajectory:"""


PARALLEL_MATTS_PROMPT = """You are an expert in Deep Eutectic Solvent (DES) formulation design. You will be given a DES design task and multiple trajectories showing how an agent attempted the task. Some trajectories may be successful, and others may have failed.

## Guidelines
Your goal is to compare and contrast these trajectories to identify the most useful and generalizable strategies as memory items.

Use self-contrast reasoning:
- Identify patterns and strategies that consistently led to success.
- Identify mistakes or inefficiencies from failed trajectories and formulate preventative strategies.
- Prefer strategies that generalize beyond specific chemical systems or exact formulations.

## Important Notes
- Think first: Why did some trajectories succeed while others failed?
- You can extract at most 5 memory items from all trajectories combined.
- Do not repeat similar or overlapping items.
- Do not mention specific chemical names in the title or description — focus on generalizable DES design principles and reasoning patterns.
- Make sure each memory item captures actionable and transferable insights.

## Output Format
Your output must strictly follow the Markdown format shown below:

```
# Memory Item 1
## Title: <the title of the memory item>
## Description: <one sentence summary of the memory item>
## Content: <1-5 sentences describing the insights learned>

# Memory Item 2
...
```

## Input

**Task Description:**
{task_description}

**Trajectories:**
{trajectories}

Now, extract generalizable strategies by comparing and contrasting these trajectories:"""


def format_trajectory_for_extraction(trajectory: dict) -> str:
    """
    Format a trajectory dictionary for use in extraction prompts.

    Args:
        trajectory: Trajectory dict with 'steps', 'tool_calls', 'reasoning', etc.

    Returns:
        Formatted string representation
    """
    formatted = ""

    # Format steps
    if "steps" in trajectory:
        for i, step in enumerate(trajectory["steps"], 1):
            formatted += f"\n### Step {i}\n"
            if "reasoning" in step:
                formatted += f"**Reasoning:** {step['reasoning']}\n"
            if "action" in step:
                formatted += f"**Action:** {step['action']}\n"
            if "observation" in step:
                formatted += f"**Observation:** {step['observation']}\n"

    # Format tool calls
    if "tool_calls" in trajectory:
        formatted += f"\n### Tool Interactions\n"
        for call in trajectory["tool_calls"]:
            formatted += f"- **{call.get('tool')}**: {call.get('query', '')}\n"

    return formatted


def parse_extracted_memories(llm_output: str) -> list:
    """
    Parse LLM output to extract memory items.

    Expected format:
    # Memory Item N
    ## Title: ...
    ## Description: ...
    ## Content: ...

    Args:
        llm_output: Raw output from LLM

    Returns:
        List of dicts with keys: title, description, content
    """
    memories = []
    lines = llm_output.strip().split('\n')

    current_memory = {}
    current_field = None

    for line in lines:
        line = line.strip()

        # Start of new memory item
        if line.startswith('# Memory Item'):
            if current_memory:
                memories.append(current_memory)
            current_memory = {}
            current_field = None

        # Parse fields
        elif line.startswith('## Title:'):
            current_field = 'title'
            current_memory['title'] = line.replace('## Title:', '').strip()

        elif line.startswith('## Description:'):
            current_field = 'description'
            current_memory['description'] = line.replace('## Description:', '').strip()

        elif line.startswith('## Content:'):
            current_field = 'content'
            current_memory['content'] = line.replace('## Content:', '').strip()

        # Continue multi-line fields
        elif line and current_field and not line.startswith('#'):
            if current_field in current_memory:
                current_memory[current_field] += ' ' + line

    # Add last memory
    if current_memory:
        memories.append(current_memory)

    return memories


# ===== New: Experiment-Based Extraction =====

EXPERIMENT_EXTRACTION_PROMPT = """You are an expert in Deep Eutectic Solvent (DES) formulation design. You will be given a DES design task, the agent's reasoning trajectory, and the **actual experimental results** from laboratory testing.

## Guidelines

Your goal is to extract generalizable insights about **formulation-condition-performance relationships** based on the experimental data.

Focus on:
1. **Quantitative relationships**: Which formulation achieved what solubility under what conditions?
2. **Component effects**: How did HBD/HBA choice affect DES formation and solubility?
3. **Molar ratio effects**: How did the ratio influence performance?
4. **Temperature effects**: How did temperature affect DES formation?
5. **Failure analysis**: If DES didn't form, what might be the chemical reason?
6. **Performance patterns**: What formulation characteristics correlate with better performance?

## Important Notes

- Extract **data-driven insights**, not just chemical theory
- Include **quantitative values** (solubility, temperature, ratio) in memory content
- Focus on **transferable patterns** that can guide future formulations
- You can extract at most 3 memory items
- Do NOT repeat similar or overlapping items
- Distinguish between "DES formation success" and "high solubility" — these are different metrics

## Output Format

Your output must strictly follow this Markdown format:

```
# Memory Item 1
## Title: <concise identifier with key quantitative info, e.g., "ChCl:Urea (1:2) Achieves 6.5 g/L for Cellulose at 25°C">
## Description: <one sentence summary including formulation and key performance metric>
## Content: <2-4 sentences describing the formulation, experimental conditions, and measured results with specific numbers>

# Memory Item 2
## Title: ...
## Description: ...
## Content: ...

# Memory Item 3
## Title: ...
## Description: ...
## Content: ...
```

## Input

**Task Description:**
{task_description}

**Target Material:** {target_material}
**Target Temperature:** {target_temperature}°C

**Agent Trajectory:**
{trajectory}

**Proposed Formulation:**
{formulation}

{experiment_summary}

Now, extract data-driven insights from this experimental result:"""
