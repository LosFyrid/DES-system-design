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
    DashScopeTextEmbeddingType
)
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb
import logging
import time
from requests.exceptions import ConnectionError, Timeout

from ..config.settings import SETTINGS, DASHSCOPE_API_KEY
from .cache import LlamaIndexLocalCache

logger = logging.getLogger(__name__)

# Redis 作为可选依赖，仅在需要时导入
try:
    from llama_index.storage.kvstore.redis import RedisKVStore
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis support not available. Install llama-index-storage-kvstore-redis to enable Redis cache.")


class RetryableDashScopeEmbedding(DashScopeEmbedding):
    """带重试机制的 DashScope Embedding"""

    def __init__(self, *args, max_retries: int = 3, retry_delay: float = 2.0, **kwargs):
        super().__init__(*args, **kwargs)
        # 使用 object.__setattr__ 绕过 Pydantic 的字段验证
        object.__setattr__(self, 'max_retries', max_retries)
        object.__setattr__(self, 'retry_delay', retry_delay)

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

    def __init__(self, collection_name: Optional[str] = None):
        self.settings = SETTINGS
        self.api_key = DASHSCOPE_API_KEY

        # 使用自定义 collection 名称或配置文件中的默认值
        self.collection_name = collection_name or self.settings.vector_store.collection_name

        if not self.api_key:
            raise ValueError(
                "DASHSCOPE_API_KEY is required for indexing. "
                "Please set it in .env file."
            )

        # 初始化 Embedding 模型（带重试机制，使用配置文件中的模型）
        self.embed_model = RetryableDashScopeEmbedding(
            model_name=self.settings.embedding.model,
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
        # 根据配置选择分块策略
        splitter_type = self.settings.document_processing.splitter_type

        if splitter_type == "semantic":
            # 语义切分（需要额外 embedding 计算）
            from llama_index.core.node_parser import SemanticSplitterNodeParser
            splitter = SemanticSplitterNodeParser(
                embed_model=self.embed_model,
                breakpoint_percentile_threshold=self.settings.document_processing.semantic_breakpoint_threshold,
                buffer_size=self.settings.document_processing.semantic_buffer_size,
            )
            logger.info(f"Using semantic splitter (threshold={self.settings.document_processing.semantic_breakpoint_threshold})")
        elif splitter_type == "sentence":
            # 句子切分（保持句子完整性）
            from llama_index.core.node_parser import SentenceSplitter
            splitter = SentenceSplitter(
                chunk_size=self.settings.document_processing.chunk_size,
                chunk_overlap=self.settings.document_processing.chunk_overlap,
            )
            logger.info(f"Using sentence splitter (size={self.settings.document_processing.chunk_size})")
        else:  # "token" (default)
            # Token 切分（当前默认）
            from llama_index.core.node_parser import SentenceSplitter
            splitter = SentenceSplitter(
                chunk_size=self.settings.document_processing.chunk_size,
                chunk_overlap=self.settings.document_processing.chunk_overlap,
            )
            logger.info(f"Using token-based splitter (size={self.settings.document_processing.chunk_size}, overlap={self.settings.document_processing.chunk_overlap})")

        transformations = [
            splitter,
            self.embed_model,
        ]

        # 配置缓存
        cache = None
        if self.settings.cache.enabled:
            if self.settings.cache.type == "local":
                # 本地文件缓存（默认推荐）
                try:
                    local_cache = LlamaIndexLocalCache(
                        cache_dir=self.settings.cache.local_cache_dir,
                        collection_name=self.settings.cache.collection_name,
                    )
                    cache = IngestionCache(
                        cache=local_cache,
                        collection=self.settings.cache.collection_name,
                    )
                    logger.info(f"Local file cache initialized at: {self.settings.cache.local_cache_dir}")
                except Exception as e:
                    logger.warning(f"Failed to initialize local cache: {e}. Proceeding without cache.")
                    cache = None

            elif self.settings.cache.type == "redis":
                # Redis 缓存（可选，需要额外服务）
                if not REDIS_AVAILABLE:
                    logger.warning("Redis cache requested but not available. Install llama-index-storage-kvstore-redis.")
                else:
                    try:
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
                logger.warning(f"Unknown cache type: {self.settings.cache.type}. Using no cache.")

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

        # 创建 Chroma collection（添加距离度量配置）
        collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": self.settings.vector_store.distance_metric}
        )
        vector_store = ChromaVectorStore(chroma_collection=collection)

        # 创建 StorageContext
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        # 构建索引（nodes 已包含 embedding，但仍需指定 embed_model 用于查询）
        index = VectorStoreIndex(
            nodes=nodes,
            storage_context=storage_context,
            embed_model=self.embed_model,  # 必须指定，用于后续查询时的 embedding
            show_progress=True,
        )

        logger.info("Index build completed and persisted to Chroma")
        return index

    def load_index(self) -> Optional[VectorStoreIndex]:
        """从持久化存储加载索引"""
        try:
            collection = self.chroma_client.get_collection(
                name=self.collection_name
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

            logger.info(f"Index loaded from Chroma successfully (collection: {self.collection_name})")
            return index
        except Exception as e:
            logger.error(f"Failed to load index from collection '{self.collection_name}': {e}")
            return None

    def get_index_stats(self) -> Dict[str, Any]:
        """获取索引统计信息"""
        try:
            collection = self.chroma_client.get_collection(
                name=self.collection_name
            )
            return {
                "collection_name": self.collection_name,
                "document_count": collection.count(),
                "persist_directory": self.settings.vector_store.persist_directory,
            }
        except:
            return {"error": "Index not found", "collection_name": self.collection_name}
