# 🚀 快速启动指南

## 最简单的方式（推荐）

**只需运行这一条命令，然后就可以离开电脑了：**

```bash
./src/external/MOSES/test/onto_cons/start_background.sh
```

这会：
- ✅ 在后台自动运行所有3个模型
- ✅ 自动备份每个模型生成的本体文件
- ✅ 创建带时间戳的日志文件
- ✅ 显示进程 PID 和日志位置

---

## 回来后查看结果

### 1. 查看生成的本体文件

```bash
ls -lh src/external/MOSES/data/ontology/*.owl
```

您应该看到3个新文件：
- `qwen3-max_<timestamp>.owl`
- `qwen3-next-80b-a3b-thinking_<timestamp>.owl`
- `qwen3-235b-a22b-thinking-2507_<timestamp>.owl`

### 2. 查看运行日志

```bash
# 列出所有日志文件
ls -lt ontology_build_*.log

# 查看最新的日志
tail -100 ontology_build_*.log | tail -1
```

---

## 其他启动方式

### 方式2: 前台运行（可以看到实时输出）

```bash
./src/external/MOSES/test/onto_cons/run_models.sh
```

### 方式3: 直接运行 Python 脚本

```bash
cd /home/syk/projects/experiment-plan-design
conda run -n OntologyConstruction python src/external/MOSES/test/onto_cons/run_multiple_models.py
```

---

## 运行时查看进度

```bash
# 查看进程是否在运行
ps aux | grep run_multiple_models

# 实时查看日志
tail -f ontology_build_*.log

# 查看已生成的文件
watch -n 10 'ls -lh src/external/MOSES/data/ontology/*.owl'
```

---

## 如需中断

```bash
# 找到进程 PID
ps aux | grep run_multiple_models

# 终止进程
kill <PID>
```

---

## 预计时间

⏱️ **总耗时**: 30-90 分钟（取决于模型响应速度）

每个模型独立运行，即使一个失败也不影响其他模型。

---

## 完成后的下一步

使用导出脚本将生成的本体导出为 JSON 和 Markdown 格式：

```bash
cd src/external/MOSES/test/onto_export

# 导出 qwen3-max 本体
conda run -n OntologyConstruction python export_ontology_hierarchy.py \
    "../../data/ontology/qwen3-max_<timestamp>.owl" \
    --output qwen3-max \
    --flat
```

---

**祝运行顺利！🎉**
