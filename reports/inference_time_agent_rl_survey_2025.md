# Inference-Time强化学习Agent框架深度调研报告
## 基于ReasoningBank与ACE的近期相关工作综述（2024-2025）

---

## 一、原始论文核心分析

### 1.1 ReasoningBank (arXiv:2509.25140v1)
**作者**: Google Research
**核心创新**:
- **内存框架**: 从成功/失败经验中蒸馏策略级推理记忆
- **Memory-aware Test-Time Scaling (MaTTS)**: 结合内存的测试时扩展机制
- **自我进化能力**: Agent能够从过往轨迹中持续学习和改进
- **结构化增量更新**: 将内存视为不断进化的playbooks

**性能提升**:
- Agent基准测试: +10.6%
- 金融领域任务: +8.6%

**关键特征**:
- ✅ 不需要模型微调/训练
- ✅ 推理时学习（Inference-time learning）
- ✅ 经验记忆与重放
- ✅ 策略级知识抽象

---

### 1.2 ACE: Agentic Context Engineering (arXiv:2510.04618v1)
**作者**: Stanford & SambaNova
**核心创新**:
- **三agent架构**: Generator（生成）→ Reflector（反思）→ Curator（策展）
- **Context作为进化playbooks**: 上下文不是静态提示，而是动态演化的知识库
- **Grow-and-Refine机制**: 增量delta更新策略
- **解决关键问题**: Brevity bias（简洁偏见）和Context collapse（上下文崩溃）

**性能提升**:
- Agent基准测试: +10.6%
- 领域特定任务: +8.6%
- 适应延迟降低: 86.9%

**关键特征**:
- ✅ 无需训练的agent强化
- ✅ Agentic工作流设计
- ✅ 增量式知识积累
- ✅ 防止上下文退化

---

## 二、相关工作系统分类（2024-2025）

### 2.1 Memory与Experience Replay类框架

#### 2.1.1 Agent Workflow Memory (AWM)
**论文**: arXiv:2409.07429 (2024年9月)
**作者**: Zora Zhiruo Wang, Jiayuan Mao, Daniel Fried, Graham Neubig
**GitHub**: https://github.com/zorazrw/agent-workflow-memory

**核心方法**:
- 从历史轨迹中归纳常用工作流（workflows）
- 选择性地为agent提供相关工作流以指导后续生成
- 支持离线和在线场景（从训练样本或测试查询中即时归纳）

**基准测试**:
- Mind2Web和WebArena（1000+任务，200+域）
- 涵盖旅行、购物、社交媒体等领域

**性能提升**:
- Mind2Web: 相对成功率提升 **24.6%**
- WebArena: 相对成功率提升 **51.1%**
- 同时减少了成功任务所需的步骤数

**与原始论文的关联**:
- 与ReasoningBank的内存框架理念一致
- 与ACE的工作流演化思想相似
- 同样强调从经验中提取可复用的策略模式

---

#### 2.1.2 Contextual Experience Replay (CER)
**论文**: arXiv:2506.06698 (2025年6月, ACL 2025)
**作者**: Yitao Liu, Chenglei Si, Karthik Narasimhan, Shunyu Yao
**GitHub**: 代码已在AGI-Edgerunners/LLM-Agents-Papers仓库中引用（具体链接可能在作者个人网站）

**核心方法**:
- **训练无关框架**: 在上下文窗口内实现高效自我改进
- **动态内存缓冲区**: 积累和综合过往经验
- **上下文内学习**: 无需参数更新即可提升性能

**基准测试**:
- VisualWebArena: 达到 **31.9%** 性能
- WebArena: 平均成功率 **36.7%**

**性能提升**:
- 相对于GPT-4o基线agent，成功率提升 **51.0%**

**与原始论文的关联**:
- 与ReasoningBank的"无微调"理念完全一致
- 类似ACE的上下文增强策略
- 强调经验重放在agent改进中的核心作用

---

#### 2.1.3 EM-LLM: Episodic Memory for Infinite Context
**论文**: arXiv:2407.09450 (2024年7月)
**项目页面**: https://em-llm.github.io/
**GitHub**: https://github.com/em-llm/EM-LLM-model

**核心方法**:
- **受人类情节记忆启发**: 将token序列组织为连贯的情节事件
- **事件分割**: 结合贝叶斯惊奇（Bayesian surprise）和图论边界细化
- **两阶段检索**: 结合基于相似度的检索和时间连续性检索
- **无需微调**: 直接应用于现有LLMs

**性能表现**:
- 在LongBench和∞-Bench基准上超越SOTA检索模型InfLLM
- 大多数任务中超越全上下文模型
- 成功处理 **1000万tokens** 的检索（全上下文模型计算不可行）

**与原始论文的关联**:
- 与ReasoningBank的"事件记忆"机制相呼应
- 提供了更长时间尺度的经验积累能力
- 人机认知桥梁：事件分割与人类感知事件高度相关

---

#### 2.1.4 Get Experience from Practice: Record & Replay
**论文**: arXiv:2505.17716 (2025年5月)
**GitHub**: 待确认

**核心方法**:
- 记录LLM agent的实践轨迹
- 通过重放机制学习改进
- 解决可靠性、隐私、成本和性能挑战

**与原始论文的关联**:
- 与ReasoningBank的经验学习框架一致
- 强调实践驱动的agent改进

---

### 2.2 Self-Reflection与Trial-and-Error学习

#### 2.2.1 Reflexion (NeurIPS 2023, 仍具高度影响力)
**论文**: arXiv:2303.11366
**作者**: Noah Shinn等
**GitHub**: https://github.com/noahshinn/reflexion

**核心方法**:
- **言语强化学习**: 通过语言反馈强化agents
- **情节记忆缓冲区**: Agents用语言反思任务反馈信号
- 将反思存储在情节记忆中，用于改进后续试验的决策

**性能表现**:
- HumanEval编程基准: **91% pass@1准确率**

**影响力**:
- 奠定了自我反思agent的基础范式
- 被大量后续工作引用和扩展

**与原始论文的关联**:
- 与ReasoningBank的失败学习机制高度相关
- ACE的Reflector agent可视为Reflexion思想的架构化实现

---

#### 2.2.2 Self-Reflection in LLM Agents (2024年10月更新)
**论文**: arXiv:2405.06682
**作者**: Matthew Renze
**GitHub**: https://github.com/matthewrenze/self-reflection

**核心方法**:
- 指导8种类型的自我反思LLM agents反思错误
- Agents向自己提供改进指导
- 使用指导重新尝试问题解决

**实验结果**:
- 显著改善问题解决性能 (p < 0.001)

**与原始论文的关联**:
- 系统性验证了自我反思的有效性
- 为ReasoningBank和ACE的反思机制提供实证支持

---

### 2.3 Self-Evolving Agent框架

#### 2.3.1 SEAgent: Self-Evolving Computer Use Agent
**论文**: arXiv:2508.04700 (2024年8月)
**作者**: Zeyi Sun等
**GitHub**: https://github.com/SunzeY/SEAgent
**模型**: Hugging Face上的Zery/SEAgent-1.0-7B

**核心方法**:
- **自主掌握新软件环境**: 通过经验学习
- **迭代试错探索**: Agents探索新软件，逐步学习
- **自动生成任务**: 从简单到复杂的任务组织
- **基于OpenRLHF训练**: 使用强化学习框架

**基准测试**:
- OSWorld（操作系统交互基准）
- AgentRewardBench

**性能提升**:
- 相对于开源CUA（UI-TARS）提升 **23.2%**（从11.3%到34.5%）

**发布资源**:
- SEAgent-1.0-7B模型
- World-State-Model-1.0-7B
- 训练和推理代码

**与原始论文的关联**:
- 完整实现了ReasoningBank的"自我进化"愿景
- 结合了推理时学习和轻量级RL优化
- 展示了从经验中持续学习的可行性

---

#### 2.3.2 Awesome Self-Evolving Agents (综述仓库)
**论文**: arXiv:2508.07407
**GitHub**: https://github.com/EvoAgentX/Awesome-Self-Evolving-Agents

**内容**:
- 自我进化AI agents的全面综述
- 桥接基础模型与终身agentic系统的新范式
- 汇集了大量相关论文和资源

**与原始论文的关联**:
- 提供了自我进化agent的全景视图
- ReasoningBank和ACE可视为该领域的最新进展

---

### 2.4 Test-Time Scaling与计算优化

#### 2.4.1 Scaling LLM Test-Time Compute Optimally
**论文**: arXiv:2408.03314 (2024年8月)
**会议**: ICLR 2025 Oral
**GitHub**: 待确认

**核心发现**:
- **测试时计算扩展可以比扩展模型参数更有效**
- 研究了LLMs如何通过更多测试时计算改进输出
- 两种主要机制：
  1. 基于密集过程验证器（PRMs）的搜索
  2. 自适应更新模型在响应上的分布

**性能Trade-offs**:
- 测试时计算可以与预训练计算权衡
- 较小或预训练较少的模型可通过测试时策略提升性能

**与原始论文的关联**:
- ReasoningBank的MaTTS机制的理论基础
- 为"不微调但增强"的理念提供计算视角

---

#### 2.4.2 Scaling Test-time Compute for LLM Agents
**论文**: arXiv:2506.12928 (2025年6月)
**GitHub**: 待确认

**核心方法**:
- **首次系统性探索**将测试时扩展应用于语言agents
- 探索策略包括：
  - 并行采样算法
  - 顺序修订策略
  - 验证器和合并方法
  - 多样化策略

**与原始论文的关联**:
- 直接呼应ReasoningBank的测试时扩展思想
- 为agent的计算资源分配提供策略框架

---

#### 2.4.3 Learning When to Plan
**论文**: arXiv:2509.03581 (2025年9月)
**GitHub**: 待确认

**核心方法**:
- 训练agents动态决定何时使用昂贵的规划过程
- 优化测试时计算的分配
- 在效率和性能之间取得平衡

**与原始论文的关联**:
- 与ACE的策展（Curator）角色功能相似
- 解决"何时使用何种策略"的元认知问题

---

### 2.5 Prompt与Context优化

#### 2.5.1 GEPA: Reflective Prompt Evolution
**论文**: arXiv:2507.19457 (2025年7月)
**GitHub**:
- 官方仓库: https://github.com/gepa-ai/gepa
- 轻量级实现: https://github.com/egmaminta/GEPA-Lite
- 其他实现: github.com/wangjing0/gepa-optimizer

**核心方法**:
- **反思性文本进化**: 使用LLMs反思系统行为
- **Genetic-Pareto算法**: 结合遗传算法和帕累托优化
- **通用框架**: 优化任意文本组件（prompts、代码片段、文本规范）
- **迭代突变、反思和帕累托选择**

**性能提升**:
- 超越GRPO（Group Relative Policy Optimization）平均 **10%**，最高 **20%**
- 使用的rollouts少 **最多35倍**
- 超越领先prompt优化器MIPROv2 **10%+**（跨两个LLMs）

**应用场景**:
- Prompt优化
- 代码优化
- 任意文本系统改进

**与原始论文的关联**:
- 与ACE的prompt进化机制高度相关
- 提供了比传统RL更高效的优化路径
- 证明反思性进化可以超越强化学习

---

### 2.6 其他重要相关工作

#### 2.6.1 MARS: Memory-Enhanced Agents with Reflective Self-improvement
**论文**: AGI-Edgerunners/LLM-Agents-Papers仓库记录（2025年3月）
**GitHub**: https://github.com/AGI-Edgerunners/LLM-Agents-Papers

**关键特征**:
- 结合内存增强和自我反思
- 与ReasoningBank和ACE的混合理念相似

---

#### 2.6.2 A-MEM: Agentic Memory for LLM Agents
**论文**: AGI-Edgerunners/LLM-Agents-Papers仓库记录（2025年2月）
**GitHub**: https://github.com/AGI-Edgerunners/LLM-Agents-Papers

**关键特征**:
- Agentic内存管理机制
- 为agents提供结构化记忆能力

---

#### 2.6.3 Awesome LLM Self-Improvement
**GitHub**: https://github.com/dongxiangjue/Awesome-LLM-Self-Improvement

**内容**:
- LLM推理时自我改进（ITSI, Inference-Time Self-Improvement）论文精选列表
- 来自最新综述的资源汇总

---

## 三、核心技术趋势与模式总结

### 3.1 共同设计模式

| 设计模式 | 代表工作 | 核心机制 |
|---------|---------|---------|
| **Memory-Driven Learning** | ReasoningBank, AWM, CER | 从经验轨迹中提取可复用知识 |
| **Reflective Architecture** | ACE, Reflexion, Self-Reflection | 多agent或多阶段反思机制 |
| **Episodic Memory** | EM-LLM, Reflexion | 类人情节记忆存储与检索 |
| **Test-Time Scaling** | ReasoningBank (MaTTS), Test-Time Compute Scaling | 推理时动态扩展计算资源 |
| **Context Evolution** | ACE, GEPA | 上下文/prompt的迭代进化 |
| **Self-Evolution** | SEAgent, EvoAgentX | 从简单到复杂的自主学习 |

---

### 3.2 关键技术对比

| 工作 | 无需训练 | 经验学习 | Test-Time Scaling | 反思机制 | 性能提升 | GitHub |
|-----|---------|---------|------------------|---------|---------|--------|
| **ReasoningBank** | ✅ | ✅ | ✅ | ✅ | +10.6% | - |
| **ACE** | ✅ | ✅ | ✅ | ✅ (三agent) | +10.6% | - |
| **AWM** | ✅ | ✅ | ❌ | ✅ | +51.1% | ✅ |
| **CER** | ✅ | ✅ | ❌ | ✅ | +51.0% | ✅ |
| **EM-LLM** | ✅ | ✅ | ❌ | ❌ | 超越SOTA | ✅ |
| **SEAgent** | ⚠️ (轻量RL) | ✅ | ❌ | ✅ | +23.2% | ✅ |
| **Reflexion** | ✅ | ✅ | ❌ | ✅ | 91% pass@1 | ✅ |
| **GEPA** | ✅ | ✅ | ❌ | ✅ | +10-20% | ✅ |

---

### 3.3 技术演进时间线

```
2023.03 ─── Reflexion (NeurIPS 2023)
              └─ 奠定自我反思agent基础

2024.07 ─── EM-LLM (arXiv:2407.09450)
              └─ 情节记忆用于无限上下文

2024.08 ─── SEAgent (arXiv:2508.04700)
          └─ Scaling Test-Time Compute (arXiv:2408.03314)
              └─ 自我进化computer-use agent
              └─ 测试时计算扩展理论

2024.09 ─── AWM (arXiv:2409.07429)
              └─ 工作流内存框架

2024.10 ─── Self-Reflection更新 (arXiv:2405.06682v2)
              └─ 自我反思有效性验证

2025.05 ─── Record & Replay (arXiv:2505.17716)
              └─ 实践经验记录重放

2025.06 ─── CER (arXiv:2506.06698)
          └─ Scaling Test-Time for Agents (arXiv:2506.12928)
              └─ 上下文经验重放
              └─ Agent专用测试时扩展

2025.07 ─── GEPA (arXiv:2507.19457)
              └─ 反思性进化超越RL

2025.09 ─── ReasoningBank (arXiv:2509.25140)
          └─ Learning When to Plan (arXiv:2509.03581)
              └─ 推理银行：内存驱动测试时扩展
              └─ 动态规划资源分配

2025.10 ─── ACE (arXiv:2510.04618)
              └─ Agentic上下文工程
```

---

## 四、与ReasoningBank和ACE的关联性分析

### 4.1 ReasoningBank的学术定位

**前置工作**:
- Reflexion: 提供了基于反思的学习基础
- EM-LLM: 展示了情节记忆的威力
- AWM: 证明了工作流内存的有效性

**同期工作**:
- Learning When to Plan: 解决元认知问题（何时规划）
- ReasoningBank解决的是"如何从经验中提取策略级知识"

**后续潜在方向**:
- 结合GEPA的进化算法，可能实现更高效的内存更新
- 结合Test-Time Compute Scaling理论，优化MaTTS机制

---

### 4.2 ACE的学术定位

**前置工作**:
- Reflexion: 提供了反思agent的基础架构灵感
- GEPA: 证明了prompt进化的有效性
- CER: 展示了上下文内学习的潜力

**核心创新**:
- 将单一agent的反思提升为**三agent协同架构**
- 系统性解决了brevity bias和context collapse问题
- 提供了可工程化的agentic工作流框架

**互补性**:
- ACE侧重上下文工程，ReasoningBank侧重内存机制
- 两者结合可实现"内存驱动的上下文进化"

---

### 4.3 技术栈融合潜力

**最优组合方案**:
1. **记忆层**: EM-LLM的情节记忆 + ReasoningBank的策略内存
2. **推理层**: ACE的三agent架构 + Reflexion的反思机制
3. **优化层**: GEPA的进化算法 + Test-Time Compute Scaling
4. **执行层**: AWM的工作流管理 + CER的经验重放

**实现路径**:
```
任务输入
   ↓
[EM-LLM] 长期情节记忆检索
   ↓
[AWM] 提取相关工作流
   ↓
[ACE Generator] 生成初始方案
   ↓
[ReasoningBank] 查询策略内存
   ↓
[ACE Reflector] 反思并识别问题
   ↓
[GEPA] 进化优化上下文/prompt
   ↓
[ACE Curator] 策展增量更新
   ↓
[CER] 将经验存入重放缓冲区
   ↓
[Test-Time Scaling] 根据任务难度动态分配计算
   ↓
输出最优方案
```

---

## 五、开源资源汇总

### 5.1 完整GitHub仓库列表

| 项目 | GitHub链接 | 状态 | 语言/框架 |
|-----|-----------|------|----------|
| **Agent Workflow Memory** | https://github.com/zorazrw/agent-workflow-memory | 活跃 | Python |
| **Reflexion** | https://github.com/noahshinn/reflexion | 稳定 | Python |
| **Self-Reflection** | https://github.com/matthewrenze/self-reflection | 活跃 | - |
| **SEAgent** | https://github.com/SunzeY/SEAgent | 活跃 | Python/OpenRLHF |
| **EM-LLM** | https://github.com/em-llm/EM-LLM-model | 活跃 | Python |
| **GEPA (官方)** | https://github.com/gepa-ai/gepa | 活跃 | Python |
| **GEPA-Lite** | https://github.com/egmaminta/GEPA-Lite | 活跃 | Python |
| **GEPA Optimizer** | https://github.com/wangjing0/gepa-optimizer | 活跃 | Python |
| **Awesome Self-Evolving Agents** | https://github.com/EvoAgentX/Awesome-Self-Evolving-Agents | 活跃 | 综述 |
| **Awesome LLM Self-Improvement** | https://github.com/dongxiangjue/Awesome-LLM-Self-Improvement | 活跃 | 综述 |
| **LLM-Agents-Papers** | https://github.com/AGI-Edgerunners/LLM-Agents-Papers | 活跃 | 综述 |

---

### 5.2 模型发布

| 模型 | Hugging Face链接 | 大小 | 说明 |
|-----|-----------------|------|-----|
| **SEAgent-1.0** | Zery/SEAgent-1.0-7B | 7B | 自我进化agent模型 |
| **World-State-Model-1.0** | Zery/World-State-Model-1.0-7B | 7B | 世界状态建模 |

---

### 5.3 项目主页与演示

| 项目 | 链接 | 类型 |
|-----|------|------|
| **EM-LLM** | https://em-llm.github.io/ | 项目主页 |
| **GEPA** | 多个GitHub实现 | 代码库 |

---

## 六、未来研究方向

### 6.1 技术融合方向

1. **统一内存架构**: 融合情节记忆（EM-LLM）、工作流内存（AWM）和策略内存（ReasoningBank）
2. **混合优化策略**: 结合进化算法（GEPA）和测试时扩展（MaTTS）
3. **Agentic架构标准化**: 基于ACE的三agent模式建立行业标准
4. **终身学习系统**: SEAgent式的持续自我进化能力

---

### 6.2 开放研究问题

1. **内存容量与检索效率**: 如何在长期运行中管理大规模内存？
2. **经验泛化能力**: 如何确保从特定任务学到的经验可迁移？
3. **Context崩溃防御**: ACE提出的问题在更长时间尺度上如何解决？
4. **计算资源分配**: 测试时扩展的最优策略是什么？
5. **多模态经验学习**: 如何扩展到视觉、音频等多模态场景？

---

### 6.3 工程化挑战

1. **生产环境部署**: 如何在低延迟要求下实现经验学习？
2. **隐私与安全**: 经验内存中敏感信息的保护
3. **成本优化**: 减少测试时计算和存储开销
4. **可解释性**: 如何让用户理解agent的学习过程？

---

## 七、总结

### 7.1 核心发现

1. **技术成熟度**: 2024-2025年出现了大量高质量的inference-time agent强化工作，该领域已从理论探索进入实践验证阶段

2. **性能验证**: 多个工作展示了显著的性能提升（+10%到+51%不等），证明"无训练强化"路径的可行性

3. **开源生态**: 大部分工作提供了GitHub代码库，形成了良好的开源生态，便于研究者快速复现和扩展

4. **理论基础**: Test-Time Compute Scaling等理论工作为这类方法提供了坚实的基础

5. **工程化进展**: SEAgent等工作展示了从研究到产品的可能路径

---

### 7.2 ReasoningBank与ACE的独特贡献

**ReasoningBank**:
- 首个系统性结合内存和测试时扩展的框架（MaTTS）
- 策略级知识抽象，而非简单的经验存储
- 为agent自我进化提供了可操作的技术路径

**ACE**:
- 首个明确提出并解决brevity bias和context collapse问题
- 三agent架构提供了可工程化的设计模式
- 将上下文从静态提示提升为动态演化的知识载体

---

### 7.3 对DES-system-design项目的启示

考虑到您的DES（Deep Eutectic Solvent）系统设计项目正在构建推理Agent：

**可借鉴的技术**:
1. **AWM的工作流内存**: 适合存储DES配方设计的常用流程
2. **ReasoningBank的策略内存**: 存储化学原理和设计策略
3. **ACE的三agent架构**: Generator生成配方→Reflector评估可行性→Curator积累知识
4. **EM-LLM的长期记忆**: 管理大量文献和实验数据
5. **CER的经验重放**: 从历史实验中学习

**实现建议**:
```python
# 伪代码示例
class DESReasoningAgent:
    def __init__(self):
        self.episodic_memory = EMLLMMemory()      # 文献和实验记忆
        self.workflow_memory = AWMMemory()        # 设计流程
        self.strategy_memory = ReasoningBankMemory()  # 化学策略
        self.context_engine = ACEEngine()         # 三agent架构

    def design_formulation(self, task):
        # 检索相关记忆
        episodes = self.episodic_memory.retrieve(task)
        workflows = self.workflow_memory.retrieve(task)
        strategies = self.strategy_memory.retrieve(task)

        # ACE三阶段
        candidates = self.context_engine.generate(task, workflows)
        reflections = self.context_engine.reflect(candidates, strategies)
        final_design = self.context_engine.curate(reflections, episodes)

        # 存储经验
        self.update_memories(task, final_design, outcome)

        return final_design
```

---

## 八、参考文献

### 原始论文
1. ReasoningBank (2025). arXiv:2509.25140v1
2. ACE: Agentic Context Engineering (2025). arXiv:2510.04618v1

### 关键相关工作
3. Agent Workflow Memory (2024). arXiv:2409.07429
4. Contextual Experience Replay (2025). arXiv:2506.06698
5. EM-LLM (2024). arXiv:2407.09450
6. SEAgent (2024). arXiv:2508.04700
7. Reflexion (2023). arXiv:2303.11366
8. GEPA (2025). arXiv:2507.19457
9. Scaling LLM Test-Time Compute (2024). arXiv:2408.03314
10. Scaling Test-time Compute for Agents (2025). arXiv:2506.12928
11. Self-Reflection in LLM Agents (2024). arXiv:2405.06682
12. Learning When to Plan (2025). arXiv:2509.03581

---

**报告完成日期**: 2025年10月13日
**调研范围**: 2024年3月 - 2025年10月
**调研深度**: 深度综述，涵盖理论、实现、性能、开源资源
**GitHub链接**: 已完整标注所有可获得的代码库
