"""
索引构建和管理模块 V2 - 重构版
核心改进：
1. Document-level 缓存（真正的断点续传）
2. 分批写入Chroma（每N个nodes写一次，降低中断风险）
3. 自动跳过已处理的文献
"""

from typing import List, Optional, Dict, Any, Set
from llama_index.core import VectorStoreIndex, Document, StorageContext
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import BaseNode, TextNode
from llama_index.embeddings.dashscope import (
    DashScopeEmbedding,
    DashScopeTextEmbeddingType
)
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb
import logging
import time
import pickle
from pathlib import Path
from requests.exceptions import ConnectionError, Timeout

from ..config.settings import SETTINGS, DASHSCOPE_API_KEY

logger = logging.getLogger(__name__)


class DocumentLevelCache:
    """Document-level 缓存管理器"""

    def __init__(self, cache_dir: str):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Document-level cache initialized at: {self.cache_dir}")

    def _get_cache_path(self, doc_hash: str) -> Path:
        """获取文档缓存文件路径"""
        return self.cache_dir / f"{doc_hash}.pkl"

    def get(self, doc_hash: str) -> Optional[List[BaseNode]]:
        """获取缓存的nodes"""
        cache_path = self._get_cache_path(doc_hash)

        if not cache_path.exists():
            return None

        try:
            with open(cache_path, 'rb') as f:
                nodes = pickle.load(f)

            logger.debug(f"Cache hit for doc {doc_hash[:16]}... ({len(nodes)} nodes)")
            return nodes
        except Exception as e:
            logger.warning(f"Failed to load cache for {doc_hash[:16]}...: {e}")
            # 损坏的缓存，删除
            try:
                cache_path.unlink()
            except:
                pass
            return None

    def put(self, doc_hash: str, nodes: List[BaseNode]) -> bool:
        """保存nodes到缓存"""
        cache_path = self._get_cache_path(doc_hash)

        try:
            # 直接pickle nodes对象（保留embedding）
            with open(cache_path, 'wb') as f:
                pickle.dump(nodes, f)

            logger.debug(f"Cached {len(nodes)} nodes for doc {doc_hash[:16]}...")
            return True
        except Exception as e:
            logger.warning(f"Failed to cache nodes for {doc_hash[:16]}...: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        cache_files = list(self.cache_dir.glob("*.pkl"))
        total_size = sum(f.stat().st_size for f in cache_files)

        return {
            "cache_dir": str(self.cache_dir),
            "cached_documents": len(cache_files),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
        }


class RetryableDashScopeEmbedding(DashScopeEmbedding):
    """带重试机制的 DashScope Embedding"""

    def __init__(self, *args, max_retries: int = 3, retry_delay: float = 2.0, **kwargs):
        super().__init__(*args, **kwargs)
        object.__setattr__(self, 'max_retries', max_retries)
        object.__setattr__(self, 'retry_delay', retry_delay)

    def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        """带重试的批量 embedding"""
        for attempt in range(self.max_retries):
            try:
                return super()._get_text_embeddings(texts)
            except (ConnectionError, Timeout, Exception) as e:
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.warning(
                        f"Embedding attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {wait_time:.1f}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"All {self.max_retries} embedding attempts failed")
                    raise


class LargeRAGIndexerV2:
    """向量索引构建和管理器 V2"""

    def __init__(self, collection_name: Optional[str] = None):
        self.settings = SETTINGS
        self.api_key = DASHSCOPE_API_KEY
        self.collection_name = collection_name or self.settings.vector_store.collection_name

        if not self.api_key:
            raise ValueError(
                "DASHSCOPE_API_KEY is required for indexing. "
                "Please set it in .env file."
            )

        # 初始化 Embedding 模型
        self.embed_model = RetryableDashScopeEmbedding(
            model_name=self.settings.embedding.model,
            text_type=DashScopeTextEmbeddingType.TEXT_TYPE_DOCUMENT,
            api_key=self.api_key,
            embed_batch_size=self.settings.embedding.batch_size,
            max_retries=3,
            retry_delay=2.0,
        )

        # 初始化 Chroma 客户端
        self.chroma_client = chromadb.PersistentClient(
            path=self.settings.vector_store.persist_directory
        )

        # 初始化 Splitter
        self._init_splitter()

        # 初始化 Document-level 缓存（按collection隔离）
        self.doc_cache = None
        if self.settings.cache.enabled and self.settings.cache.type == "local":
            cache_dir = Path(self.settings.cache.local_cache_dir) / "document_level_cache" / self.collection_name
            self.doc_cache = DocumentLevelCache(str(cache_dir))

    def _init_splitter(self):
        """初始化文档分块器"""
        splitter_type = self.settings.document_processing.splitter_type

        if splitter_type == "semantic":
            # 语义切分（需要额外 embedding 计算）
            from llama_index.core.node_parser import SemanticSplitterNodeParser

            # 转换阈值：配置文件使用 0-1 范围，LlamaIndex 期望 0-100 整数
            threshold_config = self.settings.document_processing.semantic_breakpoint_threshold
            if isinstance(threshold_config, float) and 0 <= threshold_config <= 1:
                # 转换 0-1 → 0-100
                threshold_percentile = int(threshold_config * 100)
            else:
                # 如果已经是整数，直接使用
                threshold_percentile = int(threshold_config)

            self.splitter = SemanticSplitterNodeParser(
                embed_model=self.embed_model,
                breakpoint_percentile_threshold=threshold_percentile,
                buffer_size=self.settings.document_processing.semantic_buffer_size,
            )
            logger.info(f"Using semantic splitter (threshold={threshold_percentile}%, buffer_size={self.settings.document_processing.semantic_buffer_size})")
        elif splitter_type == "sentence":
            # 句子切分（保持句子完整性）
            from llama_index.core.node_parser import SentenceSplitter
            self.splitter = SentenceSplitter(
                chunk_size=self.settings.document_processing.chunk_size,
                chunk_overlap=self.settings.document_processing.chunk_overlap,
                paragraph_separator=self.settings.document_processing.separator,
            )
            logger.info(f"Using sentence splitter (size={self.settings.document_processing.chunk_size})")
        else:  # "token" (default)
            # Token 切分（当前默认）
            from llama_index.core.node_parser import SentenceSplitter
            self.splitter = SentenceSplitter(
                chunk_size=self.settings.document_processing.chunk_size,
                chunk_overlap=self.settings.document_processing.chunk_overlap,
                paragraph_separator=self.settings.document_processing.separator,
            )
            logger.info(f"Using token-based splitter (size={self.settings.document_processing.chunk_size}, overlap={self.settings.document_processing.chunk_overlap})")

    def _get_processed_doc_hashes(self) -> Set[str]:
        """从Chroma collection中提取已处理的文献哈希"""
        try:
            collection = self.chroma_client.get_collection(name=self.collection_name)
            results = collection.get(include=['metadatas'])
            metadatas = results.get('metadatas', [])

            doc_hashes = set()
            for meta in metadatas:
                if meta and 'doc_hash' in meta:
                    doc_hashes.add(meta['doc_hash'])

            logger.info(f"Found {len(doc_hashes)} already processed documents in Chroma")
            return doc_hashes
        except:
            logger.info("No existing collection found, will process all documents")
            return set()

    def _write_nodes_batch_to_chroma(self, nodes: List[BaseNode]):
        """批量写入nodes到Chroma"""
        if not nodes:
            return

        collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": self.settings.vector_store.distance_metric}
        )

        vector_store = ChromaVectorStore(chroma_collection=collection)

        # 批量添加nodes
        vector_store.add(nodes)

        logger.info(f"✓ Wrote {len(nodes)} nodes to Chroma")

    def build_index_incremental(
        self,
        documents: List[Document],
        batch_write_size: int = 500,
        show_progress: bool = True
    ) -> VectorStoreIndex:
        """
        增量构建索引（支持断点续传）

        Args:
            documents: Document 对象列表
            batch_write_size: 每多少个nodes写一次Chroma（默认500）
            show_progress: 是否显示进度

        Returns:
            VectorStoreIndex 对象

        特性：
        - Document-level 缓存：每个文档单独缓存，真正的断点续传
        - 自动跳过已处理：检查Chroma中的doc_hash
        - 分批写入：每N个nodes写一次，降低中断风险
        """
        logger.info(f"="*80)
        logger.info(f"Starting incremental index build for {len(documents)} documents")
        logger.info(f"  Batch write size: {batch_write_size} nodes")
        logger.info(f"  Cache enabled: {self.doc_cache is not None}")
        logger.info(f"="*80)

        start_time = time.time()

        # 1. 获取已处理的doc_hashes
        processed_doc_hashes = self._get_processed_doc_hashes()

        # 2. 过滤未处理的documents
        remaining_docs = [d for d in documents if d.metadata.get('doc_hash') not in processed_doc_hashes]
        logger.info(f"\n文档统计:")
        logger.info(f"  总文档数: {len(documents)}")
        logger.info(f"  已处理: {len(processed_doc_hashes)}")
        logger.info(f"  待处理: {len(remaining_docs)}")

        if not remaining_docs:
            logger.info("\n✓ 所有文档已处理完成！")
            return self.load_index()

        # 3. 逐个处理documents
        pending_nodes = []  # 待写入的nodes缓冲区
        total_new_nodes = 0
        cache_hits = 0
        cache_misses = 0

        logger.info(f"\n开始处理 {len(remaining_docs)} 个文档...\n")

        for i, doc in enumerate(remaining_docs):
            if show_progress and (i + 1) % 10 == 0:
                elapsed = time.time() - start_time
                progress_pct = ((i + 1) / len(remaining_docs)) * 100
                avg_time = elapsed / (i + 1)
                eta = avg_time * (len(remaining_docs) - i - 1)

                logger.info(
                    f"Progress: {i+1}/{len(remaining_docs)} ({progress_pct:.1f}%) | "
                    f"Nodes: {total_new_nodes} | "
                    f"Cache: {cache_hits} hits, {cache_misses} misses | "
                    f"ETA: {eta/60:.1f}min"
                )

            doc_hash = doc.metadata.get('doc_hash')
            if not doc_hash:
                logger.warning(f"Document missing doc_hash in metadata, skipping")
                continue

            # 3.1 检查document-level缓存
            nodes = None
            if self.doc_cache:
                nodes = self.doc_cache.get(doc_hash)
                if nodes:
                    cache_hits += 1
                    # 确保缓存的nodes也有doc_hash
                    for node in nodes:
                        if 'doc_hash' not in node.metadata:
                            node.metadata['doc_hash'] = doc_hash

            # 3.2 缓存未命中：parsing + embedding
            if nodes is None:
                cache_misses += 1

                # Parsing
                nodes = self.splitter([doc])

                # 确保nodes继承doc_hash（用于后续识别已处理文献）
                for node in nodes:
                    if 'doc_hash' not in node.metadata:
                        node.metadata['doc_hash'] = doc_hash

                # Embedding（分批处理，遵循API的batch_size限制）
                batch_size = self.settings.embedding.batch_size  # 10
                for i in range(0, len(nodes), batch_size):
                    batch_nodes = nodes[i:i + batch_size]
                    texts = [node.get_content() for node in batch_nodes]
                    embeddings = self.embed_model._get_text_embeddings(texts)

                    for node, embedding in zip(batch_nodes, embeddings):
                        node.embedding = embedding

                # 保存到document-level缓存
                if self.doc_cache:
                    self.doc_cache.put(doc_hash, nodes)

            # 3.3 添加到待写入缓冲区
            pending_nodes.extend(nodes)
            total_new_nodes += len(nodes)

            # 3.4 达到batch_write_size，写入Chroma
            if len(pending_nodes) >= batch_write_size:
                write_batch = pending_nodes[:batch_write_size]
                self._write_nodes_batch_to_chroma(write_batch)
                pending_nodes = pending_nodes[batch_write_size:]

        # 4. 写入剩余nodes
        if pending_nodes:
            self._write_nodes_batch_to_chroma(pending_nodes)

        # 5. 完成统计
        total_time = time.time() - start_time
        logger.info(f"\n{'='*80}")
        logger.info(f"✅ Index build completed!")
        logger.info(f"{'='*80}")
        logger.info(f"\n统计:")
        logger.info(f"  处理文档数: {len(remaining_docs)}")
        logger.info(f"  新增nodes: {total_new_nodes:,}")
        logger.info(f"  缓存命中率: {cache_hits}/{cache_hits+cache_misses} ({100*cache_hits/(cache_hits+cache_misses):.1f}%)" if (cache_hits+cache_misses) > 0 else "  缓存: N/A")
        logger.info(f"  总耗时: {total_time/60:.1f}分钟 ({total_time/3600:.2f}小时)")
        logger.info(f"  平均速度: {len(remaining_docs)/(total_time/60):.1f} 文档/分钟")

        # 6. 加载并返回索引
        logger.info(f"\n加载完整索引...")
        return self.load_index()

    def load_index(self) -> Optional[VectorStoreIndex]:
        """从持久化存储加载索引"""
        try:
            collection = self.chroma_client.get_collection(name=self.collection_name)
            vector_store = ChromaVectorStore(chroma_collection=collection)
            storage_context = StorageContext.from_defaults(vector_store=vector_store)

            index = VectorStoreIndex.from_vector_store(
                vector_store=vector_store,
                storage_context=storage_context,
                embed_model=self.embed_model,
            )

            logger.info(f"Index loaded successfully (collection: {self.collection_name}, vectors: {collection.count():,})")
            return index
        except Exception as e:
            logger.error(f"Failed to load index: {e}")
            return None

    def get_index_stats(self) -> Dict[str, Any]:
        """获取索引统计信息"""
        try:
            collection = self.chroma_client.get_collection(name=self.collection_name)
            stats = {
                "collection_name": self.collection_name,
                "document_count": collection.count(),
                "persist_directory": self.settings.vector_store.persist_directory,
            }

            # 添加缓存统计
            if self.doc_cache:
                stats["cache_stats"] = self.doc_cache.get_stats()

            return stats
        except:
            return {"error": "Index not found", "collection_name": self.collection_name}
