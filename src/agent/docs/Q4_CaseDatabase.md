# 问题4: 案例库(CaseDatabase)的作用？

## 背景

原计划中CaseDatabase有多个功能：
1. 存储历史实验
2. 检索相似案例
3. 案例类比推理
4. 经验模式提取

问题：精简版中，案例库应该保留哪些功能？

---

## 核心概念：什么是Case-Based RL？

### 传统RL的问题

```python
# 从零开始学习
初始策略 = 随机
第1次实验 → 选择随机工具 → 失败 → 奖励 -20
第2次实验 → 选择随机工具 → 失败 → 奖励 -15
...
第50次实验 → 终于学会合理策略 → 成功 → 奖励 +40
```

**问题**: 需要大量试错，成本高（每次都是真实实验）

### Case-Based RL的解决方案

```python
# 从历史案例学习
案例库 = [
    案例1: "溶解纤维素任务 → [CoreRAG, LargeRAG, LargeRAG] → 成功",
    案例2: "降低粘度任务 → [LargeRAG, CoreRAG, ExpData] → 成功",
    ...
]

# 冷启动：模仿成功案例
初始策略 = 从案例1-10学习得到

第1次实验 → 模仿相似案例 → 成功率提升到60%
第5次实验 → 策略已经合理 → 成功率80%
```

**优势**: 快速启动，减少试错

---

## 方案A: 最小案例库（仅冷启动） ⭐ 推荐

### 功能

**唯一目的**: 冷启动训练（行为克隆）

```python
class SimpleCaseDatabase:
    """极简案例库"""

    def __init__(self):
        self.cases: List[Case] = []

    def add_case(self, case: Case):
        """添加案例"""
        self.cases.append(case)

    def get_all_success_cases(self) -> List[Case]:
        """获取所有成功案例（用于冷启动训练）"""
        return [c for c in self.cases if c.success]

    def save(self, path: str):
        """保存到文件"""
        with open(path, 'w') as f:
            json.dump([c.to_dict() for c in self.cases], f)

    def load(self, path: str):
        """从文件加载"""
        with open(path) as f:
            data = json.load(f)
            self.cases = [Case.from_dict(d) for d in data]
```

### 使用流程

```python
# ========== 第1步：准备离线数据 ==========
offline_cases = [
    Case(
        task="dissolve cellulose at -20°C",
        trajectory=[
            {"tool": "CoreRAG", "query": "cellulose dissolution mechanism"},
            {"tool": "LargeRAG", "query": "ChCl DES cellulose"},
            {"tool": "LargeRAG", "query": "low temperature viscosity"}
        ],
        formulation={"ChCl": 1, "Urea": 2},
        success=True,
        reward=46.8
    ),
    # ... 10-20个案例
]

# ========== 第2步：加载到案例库 ==========
case_db = SimpleCaseDatabase()
for case in offline_cases:
    case_db.add_case(case)

# ========== 第3步：冷启动训练（只用一次）==========
def bootstrap_training(policy, case_db):
    """从案例库学习初始策略"""
    success_cases = case_db.get_all_success_cases()

    for epoch in range(50):
        for case in success_cases:
            for state, action in zip(case.states, case.actions):
                # 监督学习：模仿成功案例的动作
                loss = train_step(policy, state, action)
                loss.backward()

# ========== 第4步：在线学习（不再需要案例库）==========
# 冷启动完成后，案例库不再使用
# PolicyNetwork直接从新实验学习
```

### 数据结构

```python
@dataclass
class Case:
    """简化的案例数据结构"""
    task: str                          # 任务描述
    trajectory: List[Dict]             # 工具调用序列
    formulation: Dict[str, float]      # 最终配方
    result: Dict                       # 实验结果
    success: bool                      # 是否成功
    reward: float                      # 奖励值
    timestamp: str                     # 时间戳
```

### 优点
- ✅ 极简实现（50行代码）
- ✅ 只做一件事：冷启动
- ✅ 不增加运行时开销
- ✅ 易于理解和维护

### 缺点
- ❌ 不能动态参考案例（运行时）
- ❌ 不能案例类比推理

---

## 方案B: 动态案例检索

### 功能

在**每次研究**时，检索相似案例作为参考：

```python
class DynamicCaseDatabase:
    """支持动态检索的案例库"""

    def __init__(self):
        self.cases: List[Case] = []
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")

    def add_case(self, case: Case):
        self.cases.append(case)

    def retrieve_similar(self, task: str, k=3) -> List[Case]:
        """检索相似案例"""
        # 任务embedding
        query_emb = self.embedder.encode(task)

        # 计算相似度
        similarities = []
        for case in self.cases:
            case_emb = self.embedder.encode(case.task)
            sim = cosine_similarity(query_emb, case_emb)
            similarities.append((case, sim))

        # 返回top-k
        similarities.sort(key=lambda x: x[1], reverse=True)
        return [case for case, sim in similarities[:k]]
```

### 使用流程

```python
# ========== 研究开始时，检索相似案例 ==========
def research(self, task: str):
    # 1. 检索相似案例
    similar_cases = self.case_db.retrieve_similar(task, k=3)

    # 2. 提取案例的工具使用模式
    common_pattern = extract_pattern(similar_cases)
    # 例如: 发现80%的相似案例都是 [CoreRAG, LargeRAG, LargeRAG]

    # 3. 将模式信息编码到State
    state = ResearchState(task=task, similar_cases=similar_cases)

    # 4. PolicyNetwork可以"看到"相似案例的模式
    state_vec = encode_state(state)  # 包含案例信息

    # 5. 正常研究流程
    for i in range(max_iter):
        action = self.policy.select_action(state_vec)
        # ...
```

### 优点
- ✅ 运行时参考历史经验
- ✅ 可能提升决策质量
- ✅ 提供解释性（"参考了案例#3"）

### 缺点
- ❌ 增加100行代码
- ❌ 每次研究都需要检索（开销）
- ❌ State特征维度增加（需要编码案例信息）
- ❌ 效果不明确（PolicyNetwork可能学会了模式）

---

## 方案C: 案例驱动推理（复杂）

### 功能

不仅检索，还进行案例类比推理：

```python
class AdvancedCaseDatabase:
    """案例推理系统"""

    def retrieve_and_reason(self, current_state):
        """检索案例并进行类比推理"""

        # 1. 检索相似案例
        similar = self.retrieve_similar(current_state.task)

        # 2. 分析当前状态与案例的差异
        case_states = [c.trajectory[current_state.iteration] for c in similar]
        current_context = extract_context(current_state)

        # 3. 案例类比
        if similar[0].had_theory_at_step_2 and not current_state.has_theory:
            recommendation = "Call CoreRAG (similar case did this)"
        elif ...

        # 4. 案例适配
        adapted_action = adapt_action(similar[0].next_action, current_state)

        return recommendation, adapted_action
```

### 优点
- ✅ 理论上更智能

### 缺点
- ❌❌ 复杂度爆炸（500+行）
- ❌❌ 难以实现（需要复杂的类比逻辑）
- ❌❌ 可能与RL冲突（两套决策系统）
- ❌❌ 不推荐

---

## 三方案对比

| 维度 | 方案A: 最小 | 方案B: 动态检索 | 方案C: 案例推理 |
|------|-----------|----------------|----------------|
| 代码量 | 50行 | 150行 | 500+行 |
| 何时使用 | 仅冷启动 | 每次研究 | 每次研究 |
| State复杂度 | 不变 | +10维 | +50维 |
| 运行时开销 | 无 | 检索(快) | 推理(慢) |
| 效果提升 | 冷启动 | 可能有 | 未知 |
| 推荐度 | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐ |

---

## 我的建议

### 推荐方案A（最小案例库）⭐

**理由**：
1. **RL已经能学习模式**
   - 如果某个工具序列有效，PolicyNetwork会自己学会
   - 案例库的模式提取，RL训练后策略网络自然就掌握了

2. **动态检索收益不明确**
   - 如果PolicyNetwork训练充分，它已经"记住"了有效模式
   - 运行时检索案例可能是冗余的

3. **保持简洁**
   - 案例库只做冷启动：从零到60分
   - 后续优化：从60到90分，靠RL自己学

### 实施建议

```python
# ========== Week 1: 准备案例库 ==========
# 1. 收集10-20个离线实验
# 2. 转换为Case格式
# 3. 存储为JSON文件

# ========== Week 2: 冷启动训练 ==========
# 1. 加载案例库
# 2. 行为克隆训练（50 epochs）
# 3. 验证初始策略（准确率应>50%）

# ========== Week 3+: 在线学习 ==========
# 1. 从真实实验学习
# 2. 案例库仅用于记录历史（可选）
# 3. 不再依赖案例库进行决策
```

### 何时考虑方案B

**如果**：
- PolicyNetwork训练不稳定
- 新任务类型差异很大
- 需要更强的解释性

**那么**：添加动态检索（但先尝试方案A）

---

## 实际例子：案例库如何帮助冷启动

### 场景

**任务**: "Design ChCl-based DES to dissolve lignin at -15°C"

### 方案A（最小案例库）

**冷启动前**（随机策略）:
```
Iteration 1: LargeRAG (随机选择)
Iteration 2: ExpData (随机选择)
Iteration 3: CoreRAG (随机选择)
结果: 配方质量差，因为没有系统性
```

**冷启动后**（从案例学习）:
```
案例库中发现：80%的溶解任务都是先查理论
PolicyNetwork学到：溶解任务 → 先CoreRAG

Iteration 1: CoreRAG (学到的模式)
Iteration 2: LargeRAG (学到的模式)
Iteration 3: LargeRAG (学到的模式)
结果: 配方质量明显提升
```

### 方案B（动态检索）

**研究开始时**:
```
检索相似案例: "dissolve cellulose at -20°C" (相似度0.87)

案例模式: [CoreRAG, LargeRAG, LargeRAG]
当前状态: Iteration 1

PolicyNetwork输入 = [state_features, case_pattern]
决策: 参考案例，选择CoreRAG
```

**差异**: 方案B每次都检索，方案A只在训练时用一次

**问题**: 如果PolicyNetwork训练好了，它已经"记住"了这个模式，检索可能是多余的

---

## 总结

**初期推荐**: 方案A（最小案例库）⭐⭐⭐⭐⭐

**核心设计**:
```python
class SimpleCaseDatabase:
    # 只有3个方法
    def add_case(self, case): ...
    def get_all_success_cases(self): ...
    def save(self, path): ...

# 用途：仅冷启动训练，运行时不使用
```

**数据需求**: 10-20个离线实验（包含工具调用轨迹）

**何时升级**: 如果发现需要运行时参考案例，再考虑方案B
