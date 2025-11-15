# ============================================
# DES System - Docker 快速参考
# ============================================

## 一键部署

```bash
./deploy/quick-deploy.sh
```

## 常用命令

### 服务管理
```bash
# 启动
docker compose --env-file .env.production up -d

# 停止
docker compose down

# 重启
docker compose restart

# 查看状态
docker compose ps
```

### 日志查看
```bash
# 所有日志
docker compose logs -f

# 后端日志
docker compose logs -f backend

# 前端日志
docker compose logs -f frontend

# 最近 100 行
docker compose logs --tail=100
```

### 健康检查
```bash
# 运行检查脚本
./deploy/healthcheck.sh

# 手动检查
curl http://localhost:8000/health
curl http://localhost/
```

### 容器调试
```bash
# 进入后端容器
docker exec -it des-backend bash

# 查看进程
docker exec -it des-backend ps aux

# 查看 Python 环境
docker exec -it des-backend pip list
```

### 数据管理
```bash
# 备份数据
tar -czf backup-$(date +%Y%m%d).tar.gz data/ logs/

# 清理日志
docker compose exec backend sh -c "rm -f /app/logs/*.log"

# 查看磁盘使用
du -sh data/ logs/
```

### 更新部署
```bash
# 拉取最新代码
git pull

# 重新构建并启动
docker compose up -d --build

# 仅重启（不重新构建）
docker compose restart
```

## 配置文件位置

| 文件 | 用途 |
|------|------|
| `.env.production` | 环境变量 |
| `config/production/largerag_settings.yaml` | LargeRAG 配置 |
| `config/production/corerag_settings.yaml` | CoreRAG 配置 |
| `docker-compose.yml` | 服务编排 |

## 端口映射

| 服务 | 容器端口 | 主机端口 |
|------|----------|----------|
| Frontend | 80 | 80 |
| Backend | 8000 | 8000 |

## 重要 URL

- 前端: http://localhost
- 后端 API: http://localhost:8000
- API 文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/health

## 故障排查

### 后端启动失败
```bash
docker compose logs backend
docker exec -it des-backend env | grep DASHSCOPE
```

### 前端无法访问后端
```bash
# 检查网络
docker network inspect des-system-design_des-network

# 检查 Nginx 配置
docker exec -it des-frontend cat /etc/nginx/conf.d/default.conf
```

### 数据未持久化
```bash
# 检查卷挂载
docker compose exec backend ls -la /app/data
docker volume ls
```

## 资源限制

当前配置（可在 docker-compose.yml 修改）：

- 后端内存限制: 4GB
- 后端 CPU 限制: 2 核
- 日志大小限制: 10MB/文件，保留 3 个

## 环境隔离说明

✅ **开发环境**（本地调试）:
- 配置: `.env` + `src/tools/*/config/settings.yaml`
- Python: 本地 Anaconda 环境
- 数据: 本地相对路径

✅ **生产环境**（Docker 部署）:
- 配置: `.env.production` + `config/production/*.yaml`
- Python: Docker 容器 Python 3.13
- 数据: 容器内绝对路径 `/app/...`

两套环境完全独立，互不干扰。

## 安全提示

⚠️ **不要提交到 Git**:
- `.env.production`（包含 API 密钥）
- `data/` 目录（用户数据）
- `logs/` 目录（日志文件）

✅ **已在 .gitignore 中排除**，但请注意不要强制添加。
