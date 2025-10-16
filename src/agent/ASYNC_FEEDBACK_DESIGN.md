# 异步实验反馈循环设计方案

**创建日期**: 2025-10-16
**状态**: ✅ 设计完成，开始实施
**目标**: 实现基于真实实验反馈的连续优化系统

---

## 📋 目录

1. [需求分析](#需求分析)
2. [核心设计理念](#核心设计理念)
3. [数据模型](#数据模型)
4. [系统架构](#系统架构)
5. [核心组件](#核心组件)
6. [跨实例复用机制](#跨实例复用机制)
7. [使用示例](#使用示例)
8. [实施计划](#实施计划)

---

## 需求分析

### 背景

原系统使用 **LLM-as-a-Judge** 进行同步评估，但这是模拟评估。实际使用中：
1. 用户根据推荐的 DES 配方进行**真实实验**
2. 实验需要**小时到天**的时间（异步）
3. 用户测量实验参数并**反馈给系统**
4. 系统利用真实数据进行**连续优化**

### 核心需求

| 需求 | 说明 |
|------|------|
| **异步工作流** | 推荐 → 等待实验 → 反馈 → 学习（跨越时间） |
| **持久化存储** | 推荐和反馈需长期保存，便于查询 |
| **实验参数反馈** | 必选：是否形成液态、溶解度；可选：黏度等 |
| **跨实例复用** | 系统 A 的数据可直接用于系统 B 的优化 |
| **连续优化** | 不做二分类（成功/失败），而是基于实验参数优化 |

### 实验参数定义

#### 必选参数
1. **is_liquid_formed** (bool): DES 固态组分是否溶解形成液态溶剂
2. **solubility** (float): 溶剂对特定材料的溶解度
   - ⚠️ **边界情况**: 若 `is_liquid_formed=False`，则 `solubility` 应为 `None`（前提不满足）

#### 可选参数
- 用户自定义（如黏度、密度、电导率等）
- 存储在 `properties: Dict[str, Any]` 中

### 为什么不用成功/失败标签？

**原因**：这是一个**连续优化过程**，而非二分类问题

| 对比维度 | 二分类（旧） | 连续优化（新） |
|---------|------------|--------------|
| 标签类型 | success/failure | 实验参数（溶解度、黏度等） |
| 记忆内容 | "成功策略" vs "失败教训" | "配方-条件-性能"映射关系 |
| 学习目标 | 区分好坏 | 建立定量预测模型 |
| 提示策略 | 成功提示/失败提示 | 实验数据提取提示 |

**优势**：
- ✅ 保留完整的定量信息（溶解度 6.5 g/L vs 二分类丢失信息）
- ✅ 支持渐进式优化（8.0 > 6.5 > 4.0，而非简单的成功/失败）
- ✅ 可以学习边界情况（如"黏度过高但溶解度尚可"的配方）

---

## 核心设计理念

### 从二分类到连续优化

```
旧设计（LLM-as-a-Judge）:
  Trajectory → Judge → Success/Failure → Extract Memory

新设计（实验反馈）:
  Trajectory → Real Experiment → Performance Metrics → Extract Data-Driven Memory
```

### 关键变化

1. **移除二分类**：不再区分 `success`/`failure`，统一为 `experiment_completed`
2. **保留完整数据**：将实验参数存储在 `Trajectory.metadata["experiment_result"]`
3. **性能分数**：引入 `performance_score` (0-10) 用于排序和比较
4. **新的提取逻辑**：`extract_from_experiment()` 替代 `extract_from_trajectory(outcome)`

---

## 数据模型

### 1. ExperimentResult

```python
@dataclass
class ExperimentResult:
    """实验反馈数据"""

    # ===== 必选参数 =====
    is_liquid_formed: bool  # DES 是否形成液态
    solubility: Optional[float]  # 溶解度（仅当 is_liquid_formed=True 时有值）
    solubility_unit: str = "g/L"  # 溶解度单位

    # ===== 可选参数（用户自定义）=====
    properties: Dict[str, Any] = field(default_factory=dict)
    # 例如: {"viscosity": 450, "density": 1.2, "melting_point": -15}

    # ===== 元数据 =====
    experimenter: Optional[str] = None
    experiment_date: str = field(default_factory=lambda: datetime.now().isoformat())
    notes: str = ""

    def __post_init__(self):
        """验证数据完整性"""
        # 边界情况：未形成液态时，溶解度应为 None
        if not self.is_liquid_formed and self.solubility is not None:
            logger.warning("Setting solubility to None (DES not formed)")
            self.solubility = None

        # 形成液态时，溶解度必须提供
        if self.is_liquid_formed and self.solubility is None:
            raise ValueError("Solubility required when is_liquid_formed=True")

    def get_performance_score(self) -> float:
        """
        计算性能分数（0-10）

        规则：
        - 未形成液态：0 分
        - 形成液态：基于溶解度（可自定义）
        """
        if not self.is_liquid_formed:
            return 0.0

        # 简单映射：溶解度越高越好
        if self.solubility is not None:
            return min(10.0, self.solubility)

        return 5.0  # 默认中等分数
```

**关键设计**：
- ✅ `__post_init__` 自动验证边界情况
- ✅ `get_performance_score()` 提供统一的性能度量
- ✅ `properties` 支持用户扩展（未来可能有新参数）

### 2. Recommendation

```python
@dataclass
class Recommendation:
    """DES 配方推荐记录"""

    # ===== 核心字段 =====
    recommendation_id: str  # 例如: "REC_20251016_123456_task_001"
    task: Dict  # 原始任务
    task_id: str
    formulation: Dict  # {HBD, HBA, molar_ratio}
    reasoning: str
    confidence: float

    # ===== Trajectory（用于跨实例复用）=====
    trajectory: Trajectory  # 完整的执行轨迹

    # ===== 状态管理 =====
    status: str  # PENDING, COMPLETED, CANCELLED
    created_at: str
    updated_at: str

    # ===== 实验反馈 =====
    experiment_result: Optional[ExperimentResult] = None

    # ===== 版本化（向后兼容）=====
    version: str = "1.0"
    metadata: dict = field(default_factory=dict)
```

**关键设计**：
- ✅ `version` 字段支持未来数据格式变化
- ✅ 完整保存 `Trajectory` 用于跨实例复用
- ✅ 状态管理（PENDING → COMPLETED）

---

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                     DESAgent                             │
│  ┌────────────────────────────────────────────────┐     │
│  │  solve_task()                                  │     │
│  │  1. 记忆检索 + 工具查询                        │     │
│  │  2. 生成配方                                   │     │
│  │  3. 创建 Recommendation 记录 ✨NEW             │     │
│  │  4. 返回 recommendation_id                     │     │
│  └────────────────────────────────────────────────┘     │
│                                                          │
│  ┌────────────────────────────────────────────────┐     │
│  │  submit_experiment_feedback()  ✨NEW           │     │
│  │  1. 接收 ExperimentResult                      │     │
│  │  2. 更新 Recommendation                        │     │
│  │  3. 调用 FeedbackProcessor                     │     │
│  └────────────────────────────────────────────────┘     │
│                                                          │
│  ┌────────────────────────────────────────────────┐     │
│  │  load_historical_recommendations()  ✨NEW      │     │
│  │  - 跨实例复用历史数据                          │     │
│  │  - 重新提取记忆                                │     │
│  └────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────┐
│              RecommendationManager  ✨NEW                │
│  - save_recommendation()                                 │
│  - get_recommendation(rec_id)                            │
│  - list_recommendations(filters)                         │
│  - update_status(rec_id, status)                         │
│  - submit_feedback(rec_id, ExperimentResult)             │
│  Storage: JSON files + index.json                        │
└─────────────────────────────────────────────────────────┘
                         │
                         ↓
                   (用户实验)
                         │
                         ↓
┌─────────────────────────────────────────────────────────┐
│              FeedbackProcessor  ✨NEW                    │
│  process_feedback(rec_id):                               │
│  1. 加载 Recommendation + ExperimentResult               │
│  2. 更新 Trajectory.outcome = "experiment_completed"     │
│  3. 调用 MemoryExtractor.extract_from_experiment()       │
│  4. 巩固到 ReasoningBank                                 │
└─────────────────────────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────┐
│              MemoryExtractor (扩展)  ✨NEW               │
│  extract_from_experiment():                              │
│  - 使用 EXPERIMENT_EXTRACTION_PROMPT                     │
│  - 提取"配方-条件-性能"映射关系                          │
│  - 不区分成功/失败，关注定量关系                         │
└─────────────────────────────────────────────────────────┘
```

---

## 核心组件

### 1. RecommendationManager

**职责**: 推荐记录的持久化存储和查询

**存储策略**:
- Phase 1: JSON 文件（每个推荐一个文件）
- 索引文件: `index.json`（加速查询）
- 优势: 简单、易于调试、支持版本控制（Git）

**目录结构**:
```
data/recommendations/
├── index.json                          # 索引
├── REC_20251016_001.json              # 推荐 1
├── REC_20251016_002.json              # 推荐 2
└── ...
```

**核心方法**:
```python
class RecommendationManager:
    def save_recommendation(rec: Recommendation) -> str
    def get_recommendation(rec_id: str) -> Optional[Recommendation]
    def list_recommendations(status=None, target_material=None, limit=100) -> List[Recommendation]
    def update_status(rec_id: str, status: str)
    def submit_feedback(rec_id: str, experiment_result: ExperimentResult)
    def get_statistics() -> Dict
```

### 2. FeedbackProcessor

**职责**: 处理实验反馈并更新 ReasoningBank

**核心逻辑**:
```python
def process_feedback(rec_id: str) -> Dict:
    # 1. 加载推荐和反馈
    rec = rec_manager.get_recommendation(rec_id)
    exp_result = rec.experiment_result

    # 2. ✨ 不设置二分类 outcome，统一为 "experiment_completed"
    rec.trajectory.outcome = "experiment_completed"
    rec.trajectory.metadata["experiment_result"] = exp_result.to_dict()
    rec.trajectory.metadata["performance_score"] = exp_result.get_performance_score()

    # 3. ✨ 提取基于实验数据的记忆
    new_memories = agent.extractor.extract_from_experiment(
        rec.trajectory,
        exp_result
    )

    # 4. 标记记忆来源
    for memory in new_memories:
        memory.metadata["source"] = "experiment_validated"
        memory.metadata["performance_score"] = exp_result.get_performance_score()

    # 5. 巩固
    agent.memory.consolidate(new_memories)

    return {...}
```

**关键变化**:
- ❌ 移除 `outcome = "success"/"failure"`
- ✅ 统一为 `outcome = "experiment_completed"`
- ✅ 保留完整的 `experiment_result` 数据

### 3. MemoryExtractor 扩展

**新增方法**: `extract_from_experiment()`

**提取目标**:
1. 配方-条件-性能的**因果关系**
2. 组分选择对性能的**定量影响**
3. 摩尔比对溶解度的**数值关系**
4. 温度对液态形成的**边界条件**

**Prompt 策略**:
```python
EXPERIMENT_EXTRACTION_PROMPT = """
You are an expert in DES formulation design. Extract data-driven insights from:

**Experimental Results:**
- DES Formation: {"Yes" if is_liquid_formed else "No"}
- Solubility: {solubility} {unit}
- Performance Score: {score}/10.0

Focus on:
1. Quantitative relationships (formulation → performance)
2. Component effects (HBD/HBA choice → solubility)
3. Molar ratio effects (ratio → performance)
4. Temperature effects (temp → DES formation)

Output:
# Memory Item 1
## Title: ChCl:Urea (1:2) Performance for Cellulose at 25°C
## Description: Achieved 6.5 g/L solubility, moderate viscosity
## Content: The formulation ChCl:Urea (1:2) successfully formed liquid DES
at 25°C and dissolved cellulose with solubility of 6.5 g/L. Viscosity was
measured at 450 cP, which is acceptable for processing. This suggests the
1:2 ratio provides good balance between H-bonding and fluidity.
...
"""
```

---

## 跨实例复用机制

### 需求

系统 A（v1.0）生成 20 个推荐 + 反馈 → 系统 B（v2.0）直接复用

### 实现

```python
class DESAgent:
    def load_historical_recommendations(
        self,
        rec_manager: RecommendationManager,
        status_filter: str = "COMPLETED",
        reprocess: bool = False
    ) -> Dict:
        """
        从历史推荐中加载实验数据并更新 ReasoningBank

        Args:
            rec_manager: 推荐管理器（可能来自旧系统）
            status_filter: 只加载指定状态的推荐
            reprocess: 是否重新处理已处理过的反馈
        """
        # 1. 获取历史推荐
        recs = rec_manager.list_recommendations(status=status_filter)

        # 2. 遍历处理
        for rec in recs:
            if not rec.experiment_result:
                continue

            # 检查是否已处理
            if rec.trajectory.metadata.get("feedback_processed_at") and not reprocess:
                continue

            # 3. 提取记忆（可能使用新的提取逻辑）
            new_memories = self.extractor.extract_from_experiment(
                rec.trajectory,
                rec.experiment_result
            )

            # 4. 标记来源
            for memory in new_memories:
                memory.metadata["source"] = "historical_experiment"

            # 5. 巩固
            self.memory.consolidate(new_memories)

        # 6. Auto-save
        self.memory.save(...)

        return stats
```

### 数据流

```
┌─────────────────────────────────────┐
│  系统 A（v1.0）                      │
│  - 生成 20 个推荐                    │
│  - 收集实验反馈                      │
│  - 提取 60 个记忆                    │
│  保存到: data/recommendations/       │
│         data/memory/                 │
└─────────────────────────────────────┘
              │
              │（磁盘存储）
              ↓
┌─────────────────────────────────────┐
│  系统 B（v2.0 - 代码更新）           │
│  1. 新的 ReasoningBank（空）         │
│  2. 指向 data/recommendations/       │
│  3. load_historical_recommendations()│
│     - 读取 20 个推荐 + 反馈          │
│     - 重新提取记忆（新逻辑）         │
│     - 巩固到 ReasoningBank           │
│  4. 继续生成新推荐（基于历史）       │
└─────────────────────────────────────┘
```

**关键优势**:
- ✅ 只需要 `Trajectory` + `ExperimentResult`（不依赖旧代码）
- ✅ 可以用新的提取逻辑重新处理（`reprocess=True`）
- ✅ 支持数据格式版本化（`Recommendation.version`）

---

## 使用示例

### 场景 1: 系统 A 生成推荐并收集反馈

```python
from agent.des_agent import DESAgent
from agent.reasoningbank import RecommendationManager, ExperimentResult

# 初始化
agent = DESAgent(
    llm_client=llm_client,
    reasoning_bank=bank,
    retriever=retriever,
    extractor=extractor,
    judge=judge,
    rec_manager=RecommendationManager("data/recommendations"),
    corerag_client=corerag,
    largerag_client=largerag,
    config=config
)

# ===== 生成推荐 =====
task = {
    "task_id": "task_001",
    "description": "Design DES for cellulose dissolution at 25°C",
    "target_material": "cellulose",
    "target_temperature": 25,
    "constraints": {"viscosity": "< 500 cP"}
}

result = agent.solve_task(task)
rec_id = result["recommendation_id"]

print(f"Recommendation ID: {rec_id}")
print(f"Formulation: {result['formulation']}")
print(f"Status: {result['status']}")  # PENDING

# ===== 用户进行实验（异步，可能需要几天）=====
# ...

# ===== 提交实验反馈 =====
experiment_result = ExperimentResult(
    is_liquid_formed=True,
    solubility=6.5,
    solubility_unit="g/L",
    properties={"viscosity": 450, "density": 1.15},
    experimenter="Dr. Zhang",
    notes="Good dissolution, acceptable viscosity"
)

feedback_result = agent.submit_experiment_feedback(rec_id, experiment_result)

print(f"Performance Score: {feedback_result['performance_score']}")
print(f"Memories Extracted: {feedback_result['num_memories']}")
print(f"Titles: {feedback_result['memories_extracted']}")
```

### 场景 2: 系统 B 加载历史数据

```python
# ===== 系统 B：新代码版本 =====
agent_B = DESAgent(
    llm_client=new_llm_client,
    reasoning_bank=ReasoningBank(...),  # 新的空记忆库
    rec_manager=RecommendationManager("data/recommendations"),  # 指向系统 A 的数据
    ...
)

# ✨ 加载系统 A 的历史数据
stats = agent_B.load_historical_recommendations(
    agent_B.rec_manager,
    status_filter="COMPLETED",
    reprocess=False  # 不重复处理
)

print(f"Loaded {stats['total_loaded']} recommendations")
print(f"Added {stats['memories_added']} memories")

# 系统 B 现在继承了系统 A 的所有经验！
new_result = agent_B.solve_task(new_task)
```

### 场景 3: 查询推荐历史

```python
# 查看所有待实验的推荐
pending = agent.rec_manager.list_recommendations(status="PENDING")
print(f"Pending: {len(pending)}")

# 查看特定材料的推荐
cellulose_recs = agent.rec_manager.list_recommendations(
    target_material="cellulose"
)

# 统计信息
stats = agent.rec_manager.get_statistics()
print(stats)
# {
#   "total": 20,
#   "by_status": {"PENDING": 5, "COMPLETED": 15},
#   "by_material": {"cellulose": 10, "lignin": 10}
# }
```

---

## 实施计划

### Phase 1: 核心功能（1-2天）

**文件新增/修改**:
- ✅ `src/agent/reasoningbank/feedback.py` - ExperimentResult, Recommendation, RecommendationManager, FeedbackProcessor
- ✅ `src/agent/reasoningbank/extractor.py` - 新增 `extract_from_experiment()`
- ✅ `src/agent/prompts/extraction_prompts.py` - 新增 `EXPERIMENT_EXTRACTION_PROMPT`
- ✅ `src/agent/des_agent.py` - 修改 `solve_task()`, 新增 `submit_experiment_feedback()`, `load_historical_recommendations()`
- ✅ `src/agent/reasoningbank/__init__.py` - 导出新组件

**任务清单**:
- [ ] 定义 `ExperimentResult`（边界情况处理）
- [ ] 定义 `Recommendation`（版本化支持）
- [ ] 实现 `RecommendationManager`（JSON + 索引）
- [ ] 实现 `FeedbackProcessor`（移除二分类）
- [ ] 新增 `MemoryExtractor.extract_from_experiment()`
- [ ] 新增 `EXPERIMENT_EXTRACTION_PROMPT`
- [ ] 修改 `DESAgent.solve_task()` - 创建推荐记录
- [ ] 实现 `DESAgent.submit_experiment_feedback()`
- [ ] 实现 `DESAgent.load_historical_recommendations()`
- [ ] 更新 `__init__.py` 导出

### Phase 2: 测试和示例（0.5天）

**文件新增/修改**:
- ✅ `src/agent/examples/example_async_feedback.py` - 演示完整流程
- ✅ `src/agent/examples/example_load_history.py` - 演示跨实例复用
- ✅ `src/agent/tests/test_feedback.py` - 单元测试

**任务清单**:
- [ ] 创建 `example_async_feedback.py`
- [ ] 创建 `example_load_history.py`
- [ ] 单元测试（ExperimentResult, Recommendation, 版本化加载）
- [ ] 更新 `README.md` 文档

### Phase 3: CLI 工具（可选，0.5天）

**文件新增**:
- ✅ `src/agent/cli.py` - 命令行工具

**功能**:
- `python -m agent.cli list` - 查看推荐列表
- `python -m agent.cli submit-feedback <rec_id>` - 交互式提交反馈
- `python -m agent.cli load-history` - 加载历史数据
- `python -m agent.cli stats` - 查看统计信息

---

## 配置更新

```yaml
# config/reasoningbank_config.yaml

# ... existing config ...

# Recommendation Management
recommendations:
  storage_path: "data/recommendations"
  auto_save: true

# Feedback Processing
feedback:
  enable_llm_evaluation: false  # 第一版不使用 LLM 评估
  auto_process_on_submit: true  # 提交反馈后自动处理
  reprocess_on_load: false  # 加载历史数据时不重复处理

# Memory Extraction
extractor:
  temperature: 1.0
  use_experiment_extraction: true
  max_items_per_experiment: 3
```

---

## 关键设计决策

### 1. 为什么用 JSON 而非数据库？

**理由**:
- ✅ 简单易懂，易于调试
- ✅ 支持版本控制（Git）
- ✅ 易于跨系统迁移（复制文件夹）
- ✅ 预计数据量不大（< 1000 推荐）
- ⚠️ 未来可升级到 SQLite（如果需要复杂查询）

### 2. 为什么移除成功/失败标签？

**理由**:
- ✅ 保留完整的定量信息（溶解度 6.5 vs 二分类）
- ✅ 支持渐进式优化（8.0 > 6.5 > 4.0）
- ✅ 更符合科学实验本质（连续变量）
- ✅ 避免阈值选择的主观性（多少溶解度算"成功"？）

### 3. 为什么保留 LLM Judge？

**理由**:
- ✅ 第一版不实现（`enable_llm_evaluation: false`）
- ✅ 未来可能有用（基于 trajectory + 真实反馈分析问题）
- ✅ 代码保留但不删除（灵活性）

### 4. 跨实例复用如何保证兼容性？

**策略**:
- ✅ 版本化数据格式（`Recommendation.version`）
- ✅ 只依赖 `Trajectory` + `ExperimentResult`（不依赖旧代码）
- ✅ 支持重新处理（`reprocess=True`）
- ✅ 向后兼容（`from_dict` 方法处理旧格式）

---

## 未来扩展方向

### 短期（1-2月）

1. **Web 界面**：
   - 查看推荐列表
   - 在线提交反馈
   - 可视化性能趋势

2. **批量处理**：
   - 批量生成推荐
   - 批量提交反馈

### 中期（3-6月）

3. **SQLite 升级**：
   - 复杂查询（按性能分数排序、时间范围过滤）
   - 全文搜索（按备注搜索）

4. **实验数据工具集成**：
   - 与 `src/tools/experimental_data/` 整合
   - 自动从实验数据库加载反馈

### 长期（6月+）

5. **主动学习**：
   - 基于历史数据推荐"最有价值的实验"
   - 不确定性估计

6. **多目标优化**：
   - 同时优化溶解度、黏度、成本等
   - Pareto 前沿分析

---

## 总结

### 核心创新

1. **异步反馈循环**：推荐 → 实验 → 反馈 → 学习
2. **连续优化**：基于实验参数（而非二分类）
3. **跨实例复用**：历史数据可直接用于新系统
4. **持久化存储**：便于查询和长期积累

### 预期收益

- ✅ 系统随实验次数增多而持续优化
- ✅ 知识可跨版本迁移（不重新训练）
- ✅ 支持真实科研场景（异步、长周期）
- ✅ 定量学习（建立配方-性能映射）

---

**文档版本**: 1.0
**最后更新**: 2025-10-16
**状态**: 设计完成，开始实施
