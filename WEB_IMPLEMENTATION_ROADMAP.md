# Web前端开发实施路线图

**基于**: WEB_FRONTEND_DESIGN.md
**目标**: 为DES系统开发Web界面（3周MVP）
**状态**: 📋 待审批

---

## 快速概览

### 技术选型
- **后端**: FastAPI (Python 3.13) + Uvicorn
- **前端**: React 18 + Ant Design 5
- **存储**: JSON文件（初期）→ SQLite（后期）
- **部署**: Docker Compose

### 核心功能（MVP）
1. ✅ 任务提交：用户输入材料、温度、约束条件
2. ✅ 推荐列表：查看、筛选、搜索推荐记录
3. ✅ 推荐详情：配方、推理、置信度展示
4. ✅ 反馈提交：提交实验结果（液态、溶解度、属性）
5. ✅ 统计仪表板：可视化图表和性能趋势

---

## 3周开发计划

### Week 1: 后端API开发（5天）

#### Day 1-2: 项目搭建 + 核心API

**目录结构**:
```
src/web_backend/
├── main.py                    # FastAPI应用入口
├── config.py                  # 配置管理
├── requirements.txt           # 依赖
├── api/
│   ├── __init__.py
│   ├── tasks.py               # 任务相关API
│   ├── recommendations.py     # 推荐相关API
│   ├── feedback.py            # 反馈相关API
│   └── statistics.py          # 统计相关API
├── services/
│   ├── task_service.py        # 业务逻辑：任务处理
│   ├── recommendation_service.py
│   ├── feedback_service.py
│   └── statistics_service.py
├── models/
│   └── schemas.py             # Pydantic数据模型
└── utils/
    ├── agent_loader.py        # 初始化DESAgent
    └── response.py            # 统一响应格式
```

**关键代码示例**:

```python
# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api import tasks, recommendations, feedback, statistics

app = FastAPI(
    title="DES Formulation System API",
    version="1.0.0",
    description="API for DES formulation recommendation and experimental feedback"
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # 前端开发服务器
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由注册
app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["Tasks"])
app.include_router(recommendations.router, prefix="/api/v1/recommendations", tags=["Recommendations"])
app.include_router(feedback.router, prefix="/api/v1/feedback", tags=["Feedback"])
app.include_router(statistics.router, prefix="/api/v1/statistics", tags=["Statistics"])

@app.get("/")
def root():
    return {"message": "DES Formulation System API", "docs": "/docs"}
```

```python
# api/tasks.py
from fastapi import APIRouter, HTTPException
from models.schemas import TaskRequest, TaskResponse
from services.task_service import TaskService

router = APIRouter()
task_service = TaskService()

@router.post("/", response_model=TaskResponse, status_code=201)
async def create_task(task: TaskRequest):
    """创建DES配方推荐任务"""
    try:
        result = task_service.create_task(task)
        return TaskResponse(status="success", data=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**任务清单**:
- [ ] 搭建FastAPI项目结构
- [ ] 实现TaskService（调用DESAgent.solve_task）
- [ ] 实现POST /api/v1/tasks
- [ ] 测试API（使用Swagger UI）

#### Day 3: 推荐管理API

**任务清单**:
- [ ] 实现RecommendationService
  - list_recommendations(status, material, page, page_size)
  - get_recommendation_detail(rec_id)
- [ ] 实现GET /api/v1/recommendations
- [ ] 实现GET /api/v1/recommendations/{id}
- [ ] 实现PATCH /api/v1/recommendations/{id}/cancel
- [ ] 测试分页、筛选功能

#### Day 4: 反馈管理API

**任务清单**:
- [ ] 实现FeedbackService（调用agent.submit_experiment_feedback）
- [ ] 实现POST /api/v1/feedback
- [ ] 实现ExperimentResult数据验证
- [ ] 测试反馈提交流程

#### Day 5: 统计API + 文档

**任务清单**:
- [ ] 实现StatisticsService
  - get_summary_statistics()
  - get_performance_trend()
  - get_top_formulations()
- [ ] 实现GET /api/v1/statistics
- [ ] 实现GET /api/v1/statistics/performance-trend
- [ ] 完善API文档（Swagger描述）
- [ ] 编写API测试用例

---

### Week 2: 前端开发（5天）

#### Day 1: 项目搭建 + 布局

**创建项目**:
```bash
npx create-react-app des-frontend
cd des-frontend
npm install antd axios react-router-dom
```

**目录结构**:
```
src/
├── App.js                     # 主应用
├── config.js                  # 配置（API_BASE_URL）
├── components/
│   ├── Layout/
│   │   ├── MainLayout.jsx     # 主布局（导航栏）
│   │   └── Header.jsx
│   └── common/
│       ├── LoadingSpinner.jsx
│       └── ErrorMessage.jsx
├── pages/
│   ├── TaskSubmit/
│   │   └── index.jsx          # 任务提交页面
│   ├── RecommendationList/
│   │   └── index.jsx          # 推荐列表页面
│   ├── RecommendationDetail/
│   │   └── index.jsx          # 推荐详情页面
│   ├── FeedbackSubmit/
│   │   └── index.jsx          # 反馈提交页面
│   └── Dashboard/
│       └── index.jsx          # 统计仪表板
├── services/
│   └── api.js                 # API调用封装
└── utils/
    └── formatters.js          # 数据格式化工具
```

**任务清单**:
- [ ] 创建React项目并安装依赖
- [ ] 实现MainLayout（顶部导航、侧边菜单）
- [ ] 配置React Router（路由表）
- [ ] 封装Axios（统一错误处理）

#### Day 2: 任务提交页面

**关键组件**:
```jsx
// pages/TaskSubmit/index.jsx
import { Form, Input, InputNumber, Button, Select, message } from 'antd';
import { createTask } from '../../services/api';

export default function TaskSubmit() {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  const onSubmit = async (values) => {
    setLoading(true);
    try {
      const result = await createTask(values);
      message.success('推荐生成成功！');
      // 跳转到推荐详情页
      navigate(`/recommendations/${result.recommendation_id}`);
    } catch (error) {
      message.error(`提交失败: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Form form={form} onFinish={onSubmit} layout="vertical">
      <Form.Item name="description" label="任务描述" rules={[{required: true}]}>
        <Input.TextArea rows={4} placeholder="例如: Design DES for cellulose dissolution at 25°C" />
      </Form.Item>
      <Form.Item name="target_material" label="目标材料" rules={[{required: true}]}>
        <Select>
          <Select.Option value="cellulose">Cellulose</Select.Option>
          <Select.Option value="lignin">Lignin</Select.Option>
          <Select.Option value="chitin">Chitin</Select.Option>
        </Select>
      </Form.Item>
      <Form.Item name="target_temperature" label="目标温度 (°C)" rules={[{required: true}]}>
        <InputNumber min={-50} max={200} />
      </Form.Item>
      <Button type="primary" htmlType="submit" loading={loading}>
        提交任务
      </Button>
    </Form>
  );
}
```

**任务清单**:
- [ ] 实现表单布局（描述、材料、温度、约束）
- [ ] 实现约束条件动态添加（键值对）
- [ ] 集成API调用（createTask）
- [ ] 添加表单验证
- [ ] 成功后跳转到详情页

#### Day 3: 推荐列表页面

**关键功能**:
- 表格展示（ProTable）
- 筛选（状态、材料、日期）
- 分页
- 操作按钮（查看详情、提交反馈）

**任务清单**:
- [ ] 实现ProTable表格
- [ ] 实现筛选表单
- [ ] 集成API（fetchRecommendations）
- [ ] 实现分页逻辑
- [ ] 添加操作列（查看、反馈按钮）

#### Day 4: 推荐详情 + 反馈提交

**推荐详情页**:
- 标签页（配方信息、推理过程、实验结果、轨迹）
- 配方展示卡片
- 状态标签

**反馈提交页**:
- 单选（是否形成液态）
- 溶解度输入
- 动态属性添加
- 实验备注

**任务清单**:
- [ ] 实现推荐详情页（Tabs布局）
- [ ] 实现反馈提交表单
- [ ] 集成API（submitFeedback）
- [ ] 实现表单验证（液态=是时，溶解度必填）

#### Day 5: API集成 + 联调

**API封装示例**:
```javascript
// services/api.js
import axios from 'axios';
import { API_BASE_URL } from '../config';

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
});

// 统一错误处理
client.interceptors.response.use(
  (response) => response.data.data,
  (error) => {
    const message = error.response?.data?.message || error.message;
    return Promise.reject(new Error(message));
  }
);

export const createTask = (taskData) => client.post('/tasks', taskData);
export const fetchRecommendations = (params) => client.get('/recommendations', { params });
export const fetchRecommendationDetail = (id) => client.get(`/recommendations/${id}`);
export const submitFeedback = (data) => client.post('/feedback', data);
export const fetchStatistics = () => client.get('/statistics');
```

**任务清单**:
- [ ] 完善API封装（所有端点）
- [ ] 前后端联调测试
- [ ] 修复集成问题
- [ ] UI细节优化

---

### Week 3: 统计仪表板 + 测试优化（5天）

#### Day 1-2: 统计仪表板

**图表库选择**: ECharts / Recharts

**关键组件**:
- 关键指标卡片（总推荐数、待实验数、平均分数）
- 材料分布饼图
- 性能趋势折线图
- Top配方表格

**任务清单**:
- [ ] 实现StatCard组件（关键指标）
- [ ] 实现MaterialDistributionChart（饼图）
- [ ] 实现PerformanceTrendChart（折线图）
- [ ] 实现TopFormulationsTable
- [ ] 集成API（fetchStatistics）

#### Day 3: 测试与Bug修复

**测试清单**:
- [ ] 任务提交流程测试
- [ ] 推荐列表筛选测试
- [ ] 反馈提交流程测试
- [ ] 统计数据展示测试
- [ ] 异常场景测试（网络错误、验证失败）
- [ ] 跨浏览器测试（Chrome, Firefox, Safari）

#### Day 4: UI优化与响应式

**优化清单**:
- [ ] 统一样式风格（颜色、间距）
- [ ] 移动端适配（响应式布局）
- [ ] Loading状态优化
- [ ] 错误提示优化
- [ ] 表单交互优化（即时验证）

#### Day 5: 文档与部署准备

**文档清单**:
- [ ] 编写用户使用手册（README_USER.md）
- [ ] 编写开发部署文档（README_DEPLOY.md）
- [ ] API使用示例
- [ ] 常见问题FAQ

**部署准备**:
- [ ] 编写Dockerfile（backend + frontend）
- [ ] 编写docker-compose.yml
- [ ] 配置Nginx反向代理
- [ ] 编写启动脚本

---

## 部署指南（开发环境）

### 快速启动

#### 后端启动

```bash
# 1. 进入后端目录
cd src/web_backend

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，设置 OPENAI_API_KEY

# 4. 启动服务
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 访问API文档: http://localhost:8000/docs
```

#### 前端启动

```bash
# 1. 进入前端目录
cd src/web_frontend

# 2. 安装依赖
npm install

# 3. 配置API地址
# 编辑 src/config.js
# export const API_BASE_URL = "http://localhost:8000/api/v1"

# 4. 启动开发服务器
npm start

# 访问前端: http://localhost:3000
```

### Docker Compose启动

```bash
# 1. 在项目根目录
cd DES-system-design

# 2. 编辑 .env 文件（配置API Key）

# 3. 启动所有服务
docker-compose up -d --build

# 查看日志
docker-compose logs -f

# 访问:
# - 前端: http://localhost:80
# - 后端API: http://localhost:8000/docs
```

---

## 验收标准

### 功能验收

- [ ] **任务提交**: 输入材料、温度，成功生成推荐
- [ ] **推荐列表**: 显示所有推荐，支持筛选（状态、材料）
- [ ] **推荐详情**: 显示配方、推理、置信度
- [ ] **反馈提交**: 提交实验结果，系统提取记忆
- [ ] **统计仪表板**: 显示图表和性能趋势

### 性能验收

- [ ] 任务提交响应时间 < 10秒（含LLM调用）
- [ ] 列表页加载时间 < 1秒（100条记录）
- [ ] 详情页加载时间 < 0.5秒
- [ ] 反馈处理时间 < 5秒（含记忆提取）

### 稳定性验收

- [ ] API错误统一返回标准格式
- [ ] 前端捕获并展示所有错误
- [ ] 表单验证完整（必填项、格式验证）
- [ ] 无控制台报错（React warnings）

---

## 风险与应对

### 技术风险

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| LLM API调用超时 | 任务提交失败 | 增加超时时间，显示进度提示 |
| JSON文件读写性能 | 列表加载慢 | 优化索引，考虑SQLite升级 |
| 前端状态管理复杂 | 代码难维护 | 引入Redux/Zustand（如需要） |

### 时间风险

| 风险 | 应对措施 |
|------|----------|
| Week 1超期 | 简化统计API，Phase 2实现 |
| Week 2前端开发慢 | 使用Ant Design ProComponents加速 |
| Week 3测试不充分 | 优先核心功能，次要功能延后 |

---

## 后续计划（Phase 2）

### 功能增强（3-6周）

1. **用户认证系统** (1周)
   - JWT Token登录
   - 用户权限管理（研究人员 vs 管理员）

2. **历史数据导入** (0.5周)
   - 管理员界面加载其他系统数据
   - 数据格式校验

3. **配方对比功能** (1周)
   - 并排对比多个推荐
   - 性能参数对比表

4. **数据导出** (0.5周)
   - JSON/CSV/Excel格式导出
   - 自定义字段选择

5. **批量操作** (1周)
   - 批量生成推荐
   - 批量提交反馈

### 技术升级（2-4周）

1. **数据库升级** (1周)
   - JSON → SQLite迁移
   - 复杂查询优化

2. **缓存层** (0.5周)
   - Redis缓存统计数据
   - 提升性能

3. **WebSocket实时通知** (1周)
   - 推荐生成完成通知
   - 反馈处理完成通知

---

## 联系与支持

- **设计文档**: WEB_FRONTEND_DESIGN.md
- **项目文档**: CLAUDE.md
- **异步反馈设计**: src/agent/ASYNC_FEEDBACK_DESIGN.md

---

**文档版本**: 1.0
**最后更新**: 2025-10-16
**下一步**: 等待审批后开始Week 1开发
