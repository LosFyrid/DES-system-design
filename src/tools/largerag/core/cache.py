"""
本地文件缓存模块
提供轻量级的 embedding 缓存功能，无需 Redis 依赖
"""

import pickle
import hashlib
import logging
from pathlib import Path
from typing import Any, Optional

from llama_index.core.storage.kvstore.types import BaseKVStore

logger = logging.getLogger(__name__)


class LocalFileCache:
    """
    本地文件系统缓存

    特点：
    - 无需额外服务（Redis）
    - 持久化存储（重启后仍有效）
    - 简单易用，零维护成本
    - 适合单机部署场景
    """

    def __init__(self, cache_dir: str, collection_name: str = "default"):
        """
        初始化本地缓存

        Args:
            cache_dir: 缓存目录路径
            collection_name: 集合名称（用于隔离不同类型的缓存）
        """
        self.cache_dir = Path(cache_dir) / collection_name
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Local file cache initialized at: {self.cache_dir}")

    def _get_cache_path(self, key: str) -> Path:
        """
        生成缓存文件路径

        使用 MD5 哈希确保文件名安全且长度固定
        """
        key_hash = hashlib.md5(key.encode('utf-8')).hexdigest()
        return self.cache_dir / f"{key_hash}.pkl"

    def get(self, key: str) -> Optional[Any]:
        """
        从缓存获取值

        Args:
            key: 缓存键

        Returns:
            缓存的值，如果不存在返回 None
        """
        cache_path = self._get_cache_path(key)

        if not cache_path.exists():
            return None

        try:
            with open(cache_path, 'rb') as f:
                value = pickle.load(f)
            logger.debug(f"Cache hit: {key[:50]}...")
            return value
        except Exception as e:
            logger.warning(f"Failed to load cache for key {key[:50]}...: {e}")
            # 损坏的缓存文件，删除它
            try:
                cache_path.unlink()
            except:
                pass
            return None

    def set(self, key: str, value: Any) -> bool:
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 要缓存的值

        Returns:
            是否成功
        """
        cache_path = self._get_cache_path(key)

        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(value, f)
            logger.debug(f"Cache set: {key[:50]}...")
            return True
        except Exception as e:
            logger.warning(f"Failed to set cache for key {key[:50]}...: {e}")
            return False

    def clear(self) -> int:
        """
        清空所有缓存

        Returns:
            删除的文件数量
        """
        count = 0
        try:
            for cache_file in self.cache_dir.glob("*.pkl"):
                cache_file.unlink()
                count += 1
            logger.info(f"Cleared {count} cache files")
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
        return count

    def get_stats(self) -> dict:
        """
        获取缓存统计信息

        Returns:
            包含缓存文件数量和总大小的字典
        """
        try:
            cache_files = list(self.cache_dir.glob("*.pkl"))
            total_size = sum(f.stat().st_size for f in cache_files)
            return {
                "cache_dir": str(self.cache_dir),
                "file_count": len(cache_files),
                "total_size_mb": round(total_size / (1024 * 1024), 2),
            }
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {"error": str(e)}


class LlamaIndexLocalCache(BaseKVStore):
    """
    LlamaIndex IngestionCache 兼容的本地缓存包装器

    将 LocalFileCache 适配为 LlamaIndex 期望的 KVStore 接口
    """

    def __init__(self, cache_dir: str, collection_name: str = "ingestion_cache"):
        self._cache = LocalFileCache(cache_dir, collection_name)
        self._collection_name = collection_name

    def put(self, key: str, val: Any, collection: str = "default") -> None:
        """LlamaIndex KVStore 接口：存储"""
        # collection 参数被忽略，使用构造时的 collection_name
        self._cache.set(key, val)

    def get(self, key: str, collection: str = "default") -> Optional[Any]:
        """LlamaIndex KVStore 接口：获取"""
        # collection 参数被忽略，使用构造时的 collection_name
        return self._cache.get(key)

    def get_all(self, collection: str = "default") -> dict:
        """LlamaIndex KVStore 接口：获取所有（不支持）"""
        # 文件缓存不高效支持此操作，返回空字典
        logger.warning("get_all() not efficiently supported by LocalFileCache")
        return {}

    def delete(self, key: str, collection: str = "default") -> bool:
        """LlamaIndex KVStore 接口：删除"""
        cache_path = self._cache._get_cache_path(key)
        try:
            if cache_path.exists():
                cache_path.unlink()
                return True
            return False
        except Exception as e:
            logger.warning(f"Failed to delete cache key {key}: {e}")
            return False

    # Async 版本（简单包装同步版本）
    async def aput(self, key: str, val: Any, collection: str = "default") -> None:
        """异步存储（包装同步方法）"""
        self.put(key, val, collection)

    async def aget(self, key: str, collection: str = "default") -> Optional[Any]:
        """异步获取（包装同步方法）"""
        return self.get(key, collection)

    async def aget_all(self, collection: str = "default") -> dict:
        """异步获取所有（包装同步方法）"""
        return self.get_all(collection)

    async def adelete(self, key: str, collection: str = "default") -> bool:
        """异步删除（包装同步方法）"""
        return self.delete(key, collection)

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()

    @property
    def stats(self) -> dict:
        """缓存统计信息"""
        return self._cache.get_stats()
