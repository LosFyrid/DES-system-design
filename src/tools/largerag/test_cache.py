"""
测试本地文件缓存功能
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.cache import LocalFileCache

def test_basic_cache():
    """测试基本缓存功能"""
    print("=" * 60)
    print("本地文件缓存功能测试")
    print("=" * 60)

    # 1. 初始化缓存
    print("\n[测试 1/5] 初始化缓存...")
    cache = LocalFileCache(
        cache_dir="data/cache_test",
        collection_name="test_collection"
    )
    print(f"  ✓ 缓存目录: {cache.cache_dir}")

    # 2. 设置缓存
    print("\n[测试 2/5] 设置缓存值...")
    test_key = "test_document_123"
    test_value = [0.1, 0.2, 0.3, 0.4, 0.5]  # 模拟 embedding 向量

    success = cache.set(test_key, test_value)
    assert success, "缓存设置失败"
    print(f"  ✓ 缓存键: {test_key}")
    print(f"  ✓ 缓存值: {test_value}")

    # 3. 获取缓存
    print("\n[测试 3/5] 获取缓存值...")
    cached_value = cache.get(test_key)
    assert cached_value is not None, "缓存未命中"
    assert cached_value == test_value, "缓存值不匹配"
    print(f"  ✓ 缓存命中")
    print(f"  ✓ 获取值: {cached_value}")

    # 4. 缓存未命中
    print("\n[测试 4/5] 测试缓存未命中...")
    non_existent = cache.get("non_existent_key")
    assert non_existent is None, "应该返回 None"
    print(f"  ✓ 正确返回 None")

    # 5. 缓存统计
    print("\n[测试 5/5] 获取缓存统计...")
    stats = cache.get_stats()
    print(f"  缓存文件数: {stats['file_count']}")
    print(f"  总大小: {stats['total_size_mb']} MB")
    print(f"  缓存目录: {stats['cache_dir']}")

    assert stats['file_count'] >= 1, "应该至少有1个缓存文件"

    # 6. 清空缓存
    print("\n[清理] 清空测试缓存...")
    count = cache.clear()
    print(f"  ✓ 删除了 {count} 个缓存文件")

    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)


def test_cache_speed():
    """测试缓存速度"""
    print("\n" + "=" * 60)
    print("缓存速度测试")
    print("=" * 60)

    cache = LocalFileCache(
        cache_dir="data/cache_test",
        collection_name="speed_test"
    )

    # 模拟大型 embedding 向量
    large_embedding = [0.1] * 1024  # 1024维向量

    # 写入速度
    print("\n[写入测试] 写入 100 个缓存条目...")
    start = time.time()
    for i in range(100):
        cache.set(f"doc_{i}", large_embedding)
    write_time = time.time() - start
    print(f"  ✓ 写入耗时: {write_time:.3f} 秒")
    print(f"  ✓ 平均速度: {100/write_time:.1f} 条/秒")

    # 读取速度
    print("\n[读取测试] 读取 100 个缓存条目...")
    start = time.time()
    for i in range(100):
        value = cache.get(f"doc_{i}")
        assert value is not None
    read_time = time.time() - start
    print(f"  ✓ 读取耗时: {read_time:.3f} 秒")
    print(f"  ✓ 平均速度: {100/read_time:.1f} 条/秒")

    # 清理
    cache.clear()

    print("\n" + "=" * 60)
    print("✅ 速度测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_basic_cache()
        test_cache_speed()
        print("\n🎉 缓存功能验证成功！\n")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
