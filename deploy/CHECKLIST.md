# ============================================
# DES System Docker 部署检查清单
# ============================================

## 📋 部署前检查

### 1. 环境准备
- [ ] Docker Engine 20.10+ 已安装
- [ ] Docker Compose 2.0+ 已安装
- [ ] 服务器至少 4GB 可用内存
- [ ] 服务器至少 10GB 可用磁盘空间

验证命令：
```bash
docker --version
docker compose version
free -h
df -h
```

### 2. 配置文件准备

#### 必须配置
- [ ] 已复制 `.env.production` 并配置 `DASHSCOPE_API_KEY`
- [ ] 已检查 `config/production/largerag_settings.yaml`
- [ ] 已检查 `config/production/corerag_settings.yaml`

#### 需要修改的配置项（如果外网访问）
- [ ] `.env.production` 中的 `CORS_ORIGINS` 修改为实际域名
- [ ] `.env.production` 中的 `VITE_API_BASE_URL` 修改为后端地址

### 3. 数据准备（可选）

如果有现成数据：
- [ ] 本体文件已复制到 `data/ontology/`
- [ ] 文献数据已复制到 `src/tools/largerag/data/`

如果没有数据，系统将使用空数据库启动。

### 4. 网络配置

- [ ] 防火墙已开放 80 端口（前端）
- [ ] 防火墙已开放 8000 端口（后端 API，可选）
- [ ] 如果使用域名，DNS 记录已配置

验证端口：
```bash
# Linux
sudo netstat -tulpn | grep -E '80|8000'

# 测试端口
curl -I http://localhost:80
curl http://localhost:8000/health
```

---

## 🚀 部署步骤

### 快速部署（推荐）

```bash
./deploy/quick-deploy.sh
```

### 手动部署

1. **创建必要目录**
   ```bash
   mkdir -p data/ontology data/recommendations data/memory logs
   ```

2. **启动服务**
   ```bash
   docker compose --env-file .env.production up -d --build
   ```

3. **查看日志**
   ```bash
   docker compose logs -f
   ```

4. **运行健康检查**
   ```bash
   ./deploy/healthcheck.sh
   ```

---

## ✅ 部署后验证

### 1. 容器状态检查
```bash
docker compose ps
```

期望输出：
```
NAME            STATUS          PORTS
des-backend     Up (healthy)    0.0.0.0:8000->8000/tcp
des-frontend    Up (healthy)    0.0.0.0:80->80/tcp
```

### 2. 健康检查
```bash
./deploy/healthcheck.sh
```

或手动检查：
```bash
curl http://localhost:8000/health
# 期望: {"status":"healthy",...}

curl http://localhost/
# 期望: HTML 页面
```

### 3. API 功能测试
```bash
# 查看 API 文档
curl http://localhost:8000/docs
# 或浏览器访问 http://localhost:8000/docs

# 测试统计接口
curl http://localhost:8000/api/v1/statistics
```

### 4. 日志检查
```bash
# 确认无错误日志
docker compose logs backend | grep -i error
docker compose logs frontend | grep -i error
```

### 5. 数据持久化验证
```bash
# 检查数据目录
ls -la data/
ls -la src/tools/largerag/data/chroma_db_prod/

# 进入容器检查
docker exec -it des-backend ls -la /app/data
```

---

## 🔍 常见问题排查

### 问题 1: 容器启动失败

**症状**: `docker compose ps` 显示容器 Exit 或 Unhealthy

**排查**:
```bash
docker compose logs backend
```

**可能原因**:
- [ ] API Key 未配置或错误
- [ ] 配置文件路径错误
- [ ] 内存不足

### 问题 2: 前端无法访问后端

**症状**: 前端页面加载正常，但无法获取数据

**排查**:
```bash
# 检查 CORS 配置
docker exec -it des-backend env | grep CORS

# 检查 Nginx 配置
docker exec -it des-frontend cat /etc/nginx/conf.d/default.conf
```

**可能原因**:
- [ ] CORS_ORIGINS 配置错误
- [ ] Nginx 反向代理配置错误
- [ ] 后端服务未启动

### 问题 3: 数据未持久化

**症状**: 重启容器后数据丢失

**排查**:
```bash
docker compose config | grep volumes
```

**可能原因**:
- [ ] docker-compose.yml 中的卷挂载配置错误
- [ ] 数据目录权限问题

### 问题 4: 内存不足

**症状**: 容器频繁重启，日志显示 OOM

**排查**:
```bash
docker stats
free -h
```

**解决方案**:
- 修改 `docker-compose.yml` 增加内存限制
- 增加服务器内存
- 优化查询参数（减少 `similarity_top_k`）

---

## 📊 监控建议

### 日常监控

1. **每日检查**
   ```bash
   ./deploy/healthcheck.sh
   docker compose ps
   ```

2. **每周维护**
   ```bash
   # 清理日志
   docker system prune -f

   # 备份数据
   tar -czf backup-$(date +%Y%m%d).tar.gz data/ logs/
   ```

3. **每月审计**
   - 检查磁盘使用: `du -sh data/ logs/`
   - 检查日志错误: `docker compose logs | grep -i error`
   - 更新系统: `docker compose pull && docker compose up -d`

---

## 📝 配置文件对比

### 开发环境 vs 生产环境

| 项目 | 开发环境 | 生产环境 |
|------|---------|---------|
| 配置文件 | `.env` | `.env.production` |
| 设置文件 | `src/tools/*/config/settings.yaml` | `config/production/*.yaml` |
| Python 路径 | 本地 Anaconda | Docker 容器 Python 3.13 |
| Java | 本地 JDK | ❌ 不使用 |
| 热重载 | ✅ | ❌ |
| 日志级别 | DEBUG | INFO |
| 数据路径 | 相对路径 | 容器内绝对路径 |

---

## 🛡️ 安全检查

部署到生产环境前：

- [ ] `.env.production` 未提交到版本控制
- [ ] API Key 使用生产环境密钥，非测试密钥
- [ ] CORS 配置仅允许信任的域名
- [ ] 日志不包含敏感信息
- [ ] 防火墙已配置，仅开放必要端口
- [ ] 考虑使用 HTTPS（通过反向代理）

---

## 📞 获取帮助

遇到无法解决的问题：

1. 查看完整文档: `deploy/README.md`
2. 快速参考: `deploy/QUICKREF.md`
3. 查看 GitHub Issues
4. 联系项目维护者

---

**部署日期**: ____________

**部署人员**: ____________

**备注**:
