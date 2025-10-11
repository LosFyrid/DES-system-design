"""
索引构建和管理模块
要求：
1. 使用 IngestionPipeline 实现批处理和缓存
2. 支持 Redis 缓存避免重复计算
3. Chroma 持久化存储
4. 提供索引统计信息
"""

from typing import List, Optional, Dict, Any
from llama_index.core import VectorStoreIndex, Document, StorageContext
from llama_index.core.ingestion import IngestionPipeline, IngestionCache
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.dashscope import (
    DashScopeEmbedding,
    DashScopeTextEmbeddingModels,
    DashScopeTextEmbeddingType
)
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.storage.kvstore.redis import RedisKVStore
import chromadb
import logging
import time
from requests.exceptions import ConnectionError, Timeout

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import SETTINGS, DASHSCOPE_API_KEY

logger = logging.getLogger(__name__)


class RetryableDashScopeEmbedding(DashScopeEmbedding):
    """带重试机制的 DashScope Embedding"""

    def __init__(self, *args, max_retries: int = 3, retry_delay: float = 2.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        """带重试的批量 embedding"""
        for attempt in range(self.max_retries):
            try:
                return super()._get_text_embeddings(texts)
            except (ConnectionError, Timeout, Exception) as e:
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)  # 指数退避
                    logger.warning(
                        f"Embedding attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {wait_time:.1f}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"All {self.max_retries} embedding attempts failed")
                    raise


class LargeRAGIndexer:
    """向量索引构建和管理器"""

    def __init__(self):
        self.settings = SETTINGS
        self.api_key = DASHSCOPE_API_KEY

        if not self.api_key:
            raise ValueError(
                "DASHSCOPE_API_KEY is required for indexing. "
                "Please set it in .env file."
            )

        # 初始化 Embedding 模型（带重试机制）
        self.embed_model = RetryableDashScopeEmbedding(
            model_name=DashScopeTextEmbeddingModels.TEXT_EMBEDDING_V3,
            text_type=DashScopeTextEmbeddingType.TEXT_TYPE_DOCUMENT,
            api_key=self.api_key,
            embed_batch_size=self.settings.embedding.batch_size,  # 显式设置批处理大小
            max_retries=3,  # 最多重试3次
            retry_delay=2.0,  # 初始延迟2秒，指数退避
        )

        # 初始化 Chroma 客户端
        self.chroma_client = chromadb.PersistentClient(
            path=self.settings.vector_store.persist_directory
        )

        # 初始化 Ingestion Pipeline
        self._init_pipeline()

    def _init_pipeline(self):
        """初始化 Ingestion Pipeline（含缓存）"""
        transformations = [
            SentenceSplitter(
                chunk_size=self.settings.document_processing.chunk_size,
                chunk_overlap=self.settings.document_processing.chunk_overlap,
            ),
            self.embed_model,
        ]

        # 配置缓存
        cache = None
        if self.settings.cache.enabled:
            if self.settings.cache.type == "redis":
                try:
                    # 注意：新版 RedisKVStore 不支持 db 参数
                    cache = IngestionCache(
                        cache=RedisKVStore.from_host_and_port(
                            host=self.settings.cache.redis_host,
                            port=self.settings.cache.redis_port,
                        ),
                        collection=self.settings.cache.collection_name,
                    )
                    logger.info("Redis cache initialized successfully")
                except Exception as e:
                    logger.warning(f"Failed to initialize Redis cache: {e}. Proceeding without cache.")
                    cache = None
            else:
                logger.warning("Local cache not implemented, using no cache")

        self.pipeline = IngestionPipeline(
            transformations=transformations,
            cache=cache,
        )

    def build_index(self, documents: List[Document]) -> VectorStoreIndex:
        """
        构建向量索引

        Args:
            documents: Document 对象列表

        Returns:
            VectorStoreIndex 对象

        注意：
        - 自动使用缓存，避免重复计算 embedding
        - 索引持久化到 Chroma
        """
        logger.info(f"Starting index build for {len(documents)} documents...")

        # 运行 Pipeline（自动批处理和缓存）
        nodes = self.pipeline.run(documents=documents, show_progress=True)
        logger.info(f"Generated {len(nodes)} nodes from {len(documents)} documents")

        # 创建 Chroma collection
        collection = self.chroma_client.get_or_create_collection(
            name=self.settings.vector_store.collection_name
        )
        vector_store = ChromaVectorStore(chroma_collection=collection)

        # 创建 StorageContext
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        # 构建索引（显式指定 embed_model）
        index = VectorStoreIndex(
            nodes=nodes,
            storage_context=storage_context,
            embed_model=self.embed_model,
            show_progress=True,
        )

        logger.info("Index build completed and persisted to Chroma")
        return index

    def load_index(self) -> Optional[VectorStoreIndex]:
        """从持久化存储加载索引"""
        try:
            collection = self.chroma_client.get_collection(
                name=self.settings.vector_store.collection_name
            )
            vector_store = ChromaVectorStore(chroma_collection=collection)

            # 创建 StorageContext
            storage_context = StorageContext.from_defaults(vector_store=vector_store)

            # 从 vector store 加载索引（显式指定 embed_model）
            index = VectorStoreIndex.from_vector_store(
                vector_store=vector_store,
                storage_context=storage_context,
                embed_model=self.embed_model,
            )

            logger.info("Index loaded from Chroma successfully")
            return index
        except Exception as e:
            logger.error(f"Failed to load index: {e}")
            return None

    def get_index_stats(self) -> Dict[str, Any]:
        """获取索引统计信息"""
        try:
            collection = self.chroma_client.get_collection(
                name=self.settings.vector_store.collection_name
            )
            return {
                "collection_name": self.settings.vector_store.collection_name,
                "document_count": collection.count(),
                "persist_directory": self.settings.vector_store.persist_directory,
            }
        except:
            return {"error": "Index not found"}
