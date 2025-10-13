# 问题2: Query生成策略？

## 背景

PolicyNetwork决定"调用哪个工具"后，需要生成具体的查询语句。

## 具体例子

假设PolicyNetwork决定调用LargeRAG，但需要确定查询内容：

**任务**: "Design ChCl-based DES to dissolve cellulose at -20°C"

**当前状态**:
- 已从CoreRAG获得理论：氢键网络机制
- 还没有具体实验案例

**需要生成查询**:
- 查询1: "ChCl DES cellulose solubility"
- 查询2: "deep eutectic solvent low temperature cellulose dissolution"
- 查询3: "ChCl-Urea cellulose experimental data"

哪个查询更好？如何生成？

---

## 方案A: 固定模板（简单） ⭐ 推荐

### 原理

根据**任务类型**和**已有知识**填充模板：

```python
# 预定义的查询模板
QUERY_TEMPLATES = {
    "CoreRAG": {
        "dissolve_material": [
            "mechanism of dissolving {material} in DES",
            "DES formation theory for {material} dissolution",
            "hydrogen bonding in DES {material} interaction"
        ],
        "optimize_viscosity": [
            "DES viscosity reduction methods",
            "temperature effect on DES viscosity"
        ]
    },
    "LargeRAG": {
        "dissolve_material": [
            "{component} DES {material} solubility",
            "{component} based DES {material} dissolution experimental",
            "DES {material} low temperature performance"
        ]
    }
}

def generate_query(tool, task_type, task_info, iteration):
    """根据模板生成查询"""
    # 提取任务关键信息
    component = extract_component(task_info.task)  # "ChCl"
    material = extract_material(task_info.task)    # "cellulose"
    temperature = extract_temperature(task_info.task)  # "-20°C"

    # 选择模板
    templates = QUERY_TEMPLATES[tool][task_type]
    template = templates[iteration % len(templates)]  # 轮换模板

    # 填充模板
    query = template.format(
        component=component,
        material=material,
        temperature=temperature
    )

    return query

# 示例
query1 = generate_query("LargeRAG", "dissolve_material", task, 0)
# 输出: "ChCl DES cellulose solubility"

query2 = generate_query("LargeRAG", "dissolve_material", task, 1)
# 输出: "ChCl based DES cellulose dissolution experimental"
```

### 改进：根据已有知识调整

```python
def generate_query_with_context(tool, task_info, state):
    """考虑已有知识"""
    # 基础查询
    base_query = generate_query(tool, task_info.task_type, task_info, state.iteration)

    # 如果已经有理论，查询更具体
    if len(state.corerag_results) > 0:
        # 添加理论相关关键词
        theory_keywords = extract_keywords(state.corerag_results)
        query = f"{base_query} {theory_keywords[0]}"

    # 如果已经有文献，查询补充信息
    if len(state.largerag_results) > 5:
        # 查询不同方面
        query = f"{base_query} viscosity temperature"

    return query
```

### 优点
- ✅ 实现简单（50行代码）
- ✅ 可控（知道查询内容）
- ✅ 快速启动（不需要训练）
- ✅ 易调试（直接看模板）

### 缺点
- ❌ 不灵活（模板固定）
- ❌ 需要人工设计模板
- ❌ 无法学习最优查询

---

## 方案B: LLM生成（中等复杂度）

### 原理

用LLM根据当前状态动态生成查询：

```python
def generate_query_with_llm(tool, task_info, state):
    """用LLM生成查询"""

    # 构建Prompt
    prompt = f"""
    Task: {task_info.task}

    Current research state:
    - Iteration: {state.iteration}
    - Tools called: {[c.tool for c in state.tool_history]}
    - CoreRAG results: {summarize(state.corerag_results)}
    - LargeRAG results: {len(state.largerag_results)} documents

    Next tool to call: {tool}

    Generate a specific query for {tool} that addresses knowledge gaps.
    Focus on information not yet obtained.

    Query:
    """

    # 调用LLM
    query = llm.generate(prompt, max_tokens=50)

    return query.strip()

# 示例输出
# "ChCl-Urea DES cellulose solubility at low temperature with viscosity data"
```

### 优点
- ✅ 灵活（自动适应状态）
- ✅ 可能生成更好的查询
- ✅ 不需要人工设计模板

### 缺点
- ❌ 增加LLM调用成本
- ❌ 不可控（可能生成无关查询）
- ❌ 难调试（不知道为什么生成这个查询）
- ❌ 依赖LLM质量

---

## 方案C: RL学习Query（复杂，不推荐）

### 原理

让PolicyNetwork不仅选择工具，还学习生成查询：

```python
class PolicyNetwork(nn.Module):
    def __init__(self):
        super().__init__()
        self.shared = nn.Sequential(...)

        # 工具选择头
        self.tool_head = nn.Linear(64, 3)

        # Query生成头（输出查询embedding）
        self.query_head = nn.Linear(64, 128)  # 生成query向量

    def forward(self, state_vec):
        x = self.shared(state_vec)
        tool_logits = self.tool_head(x)
        query_embedding = self.query_head(x)
        return tool_logits, query_embedding

# 然后用query_embedding去检索或生成自然语言查询
```

### 优点
- ✅ 可学习最优查询策略
- ✅ 端到端优化

### 缺点
- ❌❌ 复杂度爆炸（需要训练query decoder）
- ❌❌ 数据需求大（需要大量query-结果对）
- ❌❌ 难收敛（action space变成连续空间）
- ❌❌ 初期不推荐

---

## 三方案对比

| 维度 | 方案A: 模板 | 方案B: LLM | 方案C: RL |
|------|------------|-----------|----------|
| 代码量 | 50行 | 100行 | 500行 |
| 实现难度 | 简单 | 中等 | 困难 |
| LLM调用次数 | 0 | 每次工具调用+1 | 0 |
| 查询质量 | 中等 | 好 | 未知 |
| 可控性 | 高 | 中 | 低 |
| 调试难度 | 易 | 中 | 难 |
| 推荐度 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐ |

---

## 我的建议

**推荐方案A（模板）或 方案A+B混合** ⭐

### 渐进策略

**Phase 1**: 纯模板
```python
query = TEMPLATES[tool][task_type].format(**task_keywords)
```

**Phase 2**: 模板 + LLM补充（如果需要）
```python
# 基础查询用模板
base_query = TEMPLATES[tool][task_type].format(**task_keywords)

# 如果状态复杂，用LLM精化
if state.iteration > 5:
    query = llm_refine_query(base_query, state)
else:
    query = base_query
```

### 何时考虑方案B（LLM）

- ✅ 模板查询效果不好（检索结果不相关）
- ✅ 需要更动态的查询生成
- ✅ LLM调用成本可接受

### 何时考虑方案C（RL）

- ⛔ 初期不考虑
- 可能的未来方向（有大量数据后）

---

## 实际例子对比

### 任务
"Design ChCl-based DES to dissolve cellulose at -20°C"

### 迭代1: 调用CoreRAG

**方案A（模板）**:
```
Query: "mechanism of dissolving cellulose in DES"
```

**方案B（LLM）**:
```
Query: "hydrogen bonding mechanism for cellulose dissolution in ChCl-based deep eutectic solvents at low temperature"
```

**结果**: 方案B更具体，但可能过度限制检索范围

### 迭代3: 调用LargeRAG

**当前状态**: 已知氢键机制，需要实验数据

**方案A（模板+上下文）**:
```
Query: "ChCl DES cellulose solubility experimental"
```

**方案B（LLM）**:
```
Query: "ChCl-based DES cellulose dissolution experimental data at subzero temperature with hydrogen bond donor comparison"
```

**结果**: 方案B太长，可能检索不到结果

---

## 总结

**初期推荐**: 方案A（模板）
- 快速实现
- 效果已经足够好
- 可以后续优化

**如果需要改进**: 方案A+B（模板+LLM精化）
- 保持基础模板
- 在特定情况下用LLM改进

**不推荐**: 方案C（RL学习Query）
- 过于复杂
- 收益不明确
