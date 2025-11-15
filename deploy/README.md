# Docker 部署指南

DES Formulation System 的 Docker 容器化部署方案。

## 🎯 部署架构

```
┌─────────────────────────────────────────┐
│   Frontend (Nginx)                      │  :80
│   - React 静态文件                       │
│   - API 反向代理                        │
└─────────────────────────────────────────┘
              ↓ /api/*
┌─────────────────────────────────────────┐
│   Backend (FastAPI + Python 3.13)      │  :8000
│   - CoreRAG (本体推理)                   │
│   - LargeRAG (向量检索)                  │
│   - DESAgent (推理代理)                  │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│   持久化卷                               │
│   - data/ (本体、推荐、记忆)             │
│   - largerag/data/ (向量数据库)         │
│   - logs/ (日志)                        │
└─────────────────────────────────────────┘
```

## 📋 前置要求

- Docker Engine 20.10+
- Docker Compose 2.0+
- 至少 4GB 可用内存
- 至少 10GB 可用磁盘空间

## 🚀 快速部署

### 1. 配置环境变量

编辑 `.env.production` 文件：

```bash
# 必须修改的配置
DASHSCOPE_API_KEY=your-production-api-key-here

# 如果需要外网访问，修改 CORS 和前端 API URL
CORS_ORIGINS=http://your-domain.com
VITE_API_BASE_URL=http://your-domain.com:8000
```

### 2. 准备数据（可选）

如果有现成的本体文件或文献数据：

```bash
# 复制本体文件
cp /path/to/your/ontology/*.owl data/ontology/

# 复制文献数据
cp -r /path/to/literature/* src/tools/largerag/data/
```

### 3. 一键部署

```bash
./deploy/quick-deploy.sh
```

或手动执行：

```bash
# 创建必要目录
mkdir -p data/{ontology,recommendations,memory} logs

# 启动服务
docker compose --env-file .env.production up -d --build

# 查看日志
docker compose logs -f
```

### 4. 验证部署

```bash
# 运行健康检查
./deploy/healthcheck.sh

# 或手动测试
curl http://localhost:8000/health
curl http://localhost
```

## 📁 文件结构

```
DES-system-design/
├── docker-compose.yml              # 服务编排配置
├── .env.production                 # 生产环境变量（需配置）
├── docker/
│   ├── backend.Dockerfile          # 后端镜像（Python 3.13）
│   ├── frontend.Dockerfile         # 前端镜像（Node + Nginx）
│   └── nginx.conf                  # Nginx 配置
├── config/
│   └── production/                 # 生产配置（独立于开发环境）
│       ├── corerag_settings.yaml
│       └── largerag_settings.yaml
├── deploy/
│   ├── quick-deploy.sh            # 快速部署脚本
│   └── healthcheck.sh             # 健康检查脚本
└── .dockerignore                  # Docker 构建排除
```

## ⚙️ 配置说明

### 环境隔离

- **开发环境**: 使用 `.env` 和 `src/tools/*/config/settings.yaml`
- **生产环境**: 使用 `.env.production` 和 `config/production/*.yaml`

两套配置完全隔离，互不影响。

### 核心配置项

#### `.env.production`

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DASHSCOPE_API_KEY` | DashScope API 密钥 | **必填** |
| `CORS_ORIGINS` | 允许的跨域来源 | `http://localhost` |
| `VITE_API_BASE_URL` | 前端请求后端的 URL | `http://localhost:8000` |
| `FRONTEND_PORT` | 前端暴露端口 | `80` |
| `LOG_LEVEL` | 日志级别 | `INFO` |

#### 生产配置特点

- ✅ 不包含 Java（未使用 OWL 推理功能）
- ✅ 路径使用 Docker 容器内绝对路径 (`/app/...`)
- ✅ 向量数据库独立命名 (`des_literature_production`)
- ✅ 日志输出到持久化卷 (`/app/logs/`)

## 🔧 常用操作

### 查看服务状态

```bash
docker compose ps
```

### 查看日志

```bash
# 所有服务
docker compose logs -f

# 仅后端
docker compose logs -f backend

# 仅前端
docker compose logs -f frontend
```

### 重启服务

```bash
# 重启所有服务
docker compose restart

# 仅重启后端
docker compose restart backend
```

### 停止服务

```bash
# 停止但保留容器
docker compose stop

# 停止并删除容器（保留数据）
docker compose down

# 停止并删除容器和卷（清空所有数据）
docker compose down -v
```

### 更新代码

```bash
git pull
docker compose up -d --build
```

### 进入容器调试

```bash
# 进入后端容器
docker exec -it des-backend bash

# 进入前端容器
docker exec -it des-frontend sh
```

### 查看资源使用

```bash
docker stats des-backend des-frontend
```

## 🔍 故障排查

### 1. 容器启动失败

```bash
# 查看详细日志
docker compose logs backend

# 检查配置文件
docker exec -it des-backend cat /app/src/tools/largerag/config/settings.yaml
```

### 2. API 请求失败

```bash
# 检查后端健康
curl http://localhost:8000/health

# 查看 Nginx 代理日志
docker compose logs frontend
```

### 3. 数据持久化问题

```bash
# 检查卷挂载
docker compose exec backend ls -la /app/data

# 检查权限
docker compose exec backend ls -ld /app/data /app/logs
```

### 4. 内存不足

编辑 `docker-compose.yml` 调整资源限制：

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          memory: 6G  # 增加到 6GB
```

## 🛡️ 生产环境优化

### 1. 使用 HTTPS

建议使用 Nginx 或 Traefik 反向代理处理 SSL：

```bash
# 示例：使用 Certbot 获取证书
docker run -it --rm -v /etc/letsencrypt:/etc/letsencrypt \
  certbot/certbot certonly --standalone -d your-domain.com
```

### 2. 配置域名

修改 `.env.production`:

```bash
CORS_ORIGINS=https://your-domain.com
VITE_API_BASE_URL=https://api.your-domain.com
```

### 3. 日志管理

Docker Compose 已配置日志轮转：

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

### 4. 备份数据

```bash
# 备份数据目录
tar -czf des-backup-$(date +%Y%m%d).tar.gz data/ logs/

# 备份向量数据库
tar -czf chroma-backup-$(date +%Y%m%d).tar.gz \
  src/tools/largerag/data/chroma_db_prod/
```

## 📊 监控与维护

### 健康检查端点

- **后端健康**: `http://localhost:8000/health`
- **API 文档**: `http://localhost:8000/docs`
- **前端**: `http://localhost/`

### 定期维护

```bash
# 每周清理未使用的镜像
docker system prune -f

# 每月备份数据
./deploy/backup.sh  # 可自行创建

# 查看磁盘使用
du -sh data/ logs/ src/tools/largerag/data/
```

## 🔐 安全建议

1. **API 密钥管理**
   - 不要将 `.env.production` 提交到版本控制
   - 使用环境变量或密钥管理服务

2. **网络隔离**
   - 生产环境不要暴露 8000 端口到公网
   - 仅通过 Nginx 反向代理访问

3. **日志安全**
   - 定期检查日志中是否包含敏感信息
   - 配置日志轮转避免磁盘占满

## 📝 开发与部署环境对比

| 项目 | 开发环境 | 部署环境 |
|------|---------|---------|
| 配置文件 | `.env` + `src/tools/*/config/settings.yaml` | `.env.production` + `config/production/*.yaml` |
| Python 解释器 | `C:/D/AnacondaEnPs/envs/OntologyConstruction/python.exe` | Docker 容器内 Python 3.13 |
| Java | 本地 JDK 23 | ❌ 不使用（已移除） |
| 数据路径 | 本地相对路径 | 容器内绝对路径 (`/app/...`) |
| 热重载 | ✅ `API_RELOAD=true` | ❌ `API_RELOAD=false` |
| 端口 | 自定义 | 80 (前端) + 8000 (后端) |

## 🆘 获取帮助

遇到问题时：

1. 查看日志: `docker compose logs -f`
2. 运行健康检查: `./deploy/healthcheck.sh`
3. 检查 GitHub Issues
4. 联系项目维护者

## 📜 许可证

参见项目根目录 LICENSE 文件。
