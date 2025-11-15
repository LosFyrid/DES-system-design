# 自动化本体构建脚本使用说明

## 功能说明

这个脚本会自动使用三个不同的 LLM 模型依次运行本体构建，并自动备份每个模型生成的本体文件。

## 测试的模型

1. **qwen3-max**
2. **qwen3-next-80b-a3b-thinking**
3. **qwen3-235b-a22b-thinking-2507**

## 使用方法

### 方法1: 直接运行 Python 脚本

```bash
cd /home/syk/projects/experiment-plan-design
conda run -n OntologyConstruction python src/external/MOSES/test/onto_cons/run_multiple_models.py
```

### 方法2: 使用 Bash 启动脚本

```bash
cd /home/syk/projects/experiment-plan-design
./src/external/MOSES/test/onto_cons/run_models.sh
```

### 方法3: 后台运行（推荐，可以离开电脑）

```bash
cd /home/syk/projects/experiment-plan-design

# 使用 nohup 后台运行
nohup ./src/external/MOSES/test/onto_cons/run_models.sh > ontology_build.log 2>&1 &

# 或者使用 screen/tmux
screen -S ontology_build
./src/external/MOSES/test/onto_cons/run_models.sh
# 按 Ctrl+A 然后按 D 退出 screen
```

## 脚本工作流程

对于每个模型，脚本会自动执行以下步骤：

1. 📝 **修改配置**: 修改 `ontology_builder.py` 中的模型名称
2. 🚀 **运行构建**: 执行本体构建命令
3. 💾 **备份文件**: 将生成的 `chem_ontology.owl` 备份为 `{模型名}_{时间戳}.owl`
4. 🔄 **重置环境**: 创建新的空白 `chem_ontology.owl` 文件
5. ➡️ **继续下一个**: 重复以上步骤，直到所有模型完成

## 输出文件

所有生成的本体文件将保存在：
```
src/external/MOSES/data/ontology/
```

文件命名格式：
```
qwen3-max_20251022_213045.owl
qwen3-next-80b-a3b-thinking_20251022_215130.owl
qwen3-235b-a22b-thinking-2507_20251022_221215.owl
```

## 查看运行状态

### 查看后台进程
```bash
# 查看进程
ps aux | grep run_multiple_models

# 查看日志（如果使用 nohup）
tail -f ontology_build.log
```

### 查看输出文件
```bash
ls -lh src/external/MOSES/data/ontology/*.owl
```

## 预计耗时

- 每个模型的构建时间取决于：
  - 模型响应速度
  - 数据复杂度
  - 网络状况

预计总耗时：**30-90 分钟**（根据实际情况）

## 安全特性

- ✅ **自动备份**: 原始 `ontology_builder.py` 会在运行前备份
- ✅ **自动恢复**: 完成后会恢复原始配置
- ✅ **错误处理**: 单个模型失败不会影响后续模型
- ✅ **实时日志**: 所有输出都会实时显示和记录

## 故障排除

### 如果脚本中断

1. 检查 `src/external/MOSES/data/ontology/` 目录，查看哪些模型已完成
2. 编辑 `run_multiple_models.py`，修改 `MODELS` 列表，移除已完成的模型
3. 重新运行脚本

### 手动恢复原始配置

```bash
# 如果备份文件存在
cp src/external/MOSES/test/onto_cons/ontology_builder.py.backup \
   src/external/MOSES/test/onto_cons/ontology_builder.py
```

## 注意事项

⚠️ **重要提示**:
- 确保有足够的磁盘空间（每个本体文件可能较大）
- 确保 API 密钥已正确配置（DASHSCOPE_API_KEY）
- 建议在离开电脑前使用后台运行方式
- 可以通过日志文件或输出文件判断进度

## 完成后

当您回来时，应该能看到：
- 3个新的本体文件（每个模型一个）
- 每个文件都带有时间戳
- 原始 `ontology_builder.py` 配置已恢复

随后可以使用导出脚本将这些本体导出为 JSON 和 Markdown 格式：
```bash
cd src/external/MOSES/test/onto_export
conda run -n OntologyConstruction python export_ontology_hierarchy.py \
    "../../data/ontology/qwen3-max_<timestamp>.owl" \
    --output qwen3-max \
    --flat
```
