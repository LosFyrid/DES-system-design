"""调试 DashScope Embedding"""

from llama_index.embeddings.dashscope import (
    DashScopeEmbedding,
    DashScopeTextEmbeddingModels,
    DashScopeTextEmbeddingType
)
from config.settings import DASHSCOPE_API_KEY

print("=== DashScope Embedding 调试 ===")
print(f"API Key 存在: {DASHSCOPE_API_KEY is not None}")

# 初始化 embedding 模型
embed_model = DashScopeEmbedding(
    model_name=DashScopeTextEmbeddingModels.TEXT_EMBEDDING_V3,
    text_type=DashScopeTextEmbeddingType.TEXT_TYPE_DOCUMENT,
    api_key=DASHSCOPE_API_KEY,
    embed_batch_size=5,  # 显式设置批处理大小
)

print(f"Embedding 模型初始化成功")
print(f"Batch size: {embed_model.embed_batch_size}")

# 测试单个文本
test_text = "Deep eutectic solvents are a new class of green solvents."
print(f"\n测试文本: {test_text}")

try:
    embedding = embed_model.get_text_embedding(test_text)
    print(f"✓ Embedding 成功")
    print(f"  维度: {len(embedding)}")
    print(f"  前5个值: {embedding[:5]}")
except Exception as e:
    print(f"✗ Embedding 失败: {e}")

# 测试批处理
test_texts = [
    "Deep eutectic solvents are important.",
    "DES have many applications.",
    "Chemistry research uses DES."
]
print(f"\n测试批处理 ({len(test_texts)} texts)...")

try:
    embeddings = embed_model.get_text_embedding_batch(test_texts)
    print(f"✓ 批处理成功")
    print(f"  返回数量: {len(embeddings)}")
    for i, emb in enumerate(embeddings):
        if emb is None:
            print(f"  ✗ 文本 {i}: embedding 为 None")
        else:
            print(f"  ✓ 文本 {i}: 维度 {len(emb)}")
except Exception as e:
    print(f"✗ 批处理失败: {e}")
