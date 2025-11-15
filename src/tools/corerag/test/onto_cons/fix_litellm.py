"""
临时修复litellm的TranscriptionCreateParams __annotations__错误
这个脚本会修改litellm库中的model_param_helper.py文件
"""
import os
import sys

# 找到litellm安装路径
try:
    import litellm
    litellm_path = os.path.dirname(litellm.__file__)
    target_file = os.path.join(litellm_path, 'litellm_core_utils', 'model_param_helper.py')

    print(f"找到litellm安装路径: {litellm_path}")
    print(f"目标文件: {target_file}")

    if not os.path.exists(target_file):
        print(f"错误: 文件不存在 {target_file}")
        sys.exit(1)

    # 备份原文件
    backup_file = target_file + '.backup'
    if not os.path.exists(backup_file):
        import shutil
        shutil.copy2(target_file, backup_file)
        print(f"已备份原文件到: {backup_file}")

    # 读取文件内容
    with open(target_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查是否已经修复
    if 'try:' in content and '_get_litellm_supported_transcription_kwargs' in content:
        # 简单检查，可能已经修复
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if '_get_litellm_supported_transcription_kwargs' in line:
                # 查看后面10行是否有try
                if any('try:' in lines[j] for j in range(i, min(i+10, len(lines)))):
                    print("检测到文件可能已经修复过，跳过修改")
                    print("如需重新修复，请先删除.backup文件并恢复原文件")
                    sys.exit(0)

    # 定义修复的代码
    old_code = '''    @staticmethod
    def _get_litellm_supported_transcription_kwargs() -> Set[str]:
        """
        Get the litellm supported transcription kwargs

        This follows the OpenAI API Spec
        """
        return set(TranscriptionCreateParams.__annotations__.keys())'''

    new_code = '''    @staticmethod
    def _get_litellm_supported_transcription_kwargs() -> Set[str]:
        """
        Get the litellm supported transcription kwargs

        This follows the OpenAI API Spec
        """
        try:
            # Try to access __annotations__ directly
            return set(TranscriptionCreateParams.__annotations__.keys())
        except AttributeError:
            # TranscriptionCreateParams might be a Union type without __annotations__
            # Return empty set as transcription is not used in most cases
            return set()'''

    # 替换代码
    if old_code in content:
        new_content = content.replace(old_code, new_code)

        # 写入修改后的内容
        with open(target_file, 'w', encoding='utf-8') as f:
            f.write(new_content)

        print("✓ 成功修复litellm!")
        print("修改内容: 在_get_litellm_supported_transcription_kwargs()中添加了try-except处理")
        print("\n如需恢复原文件，运行:")
        print(f"  copy \"{backup_file}\" \"{target_file}\"")
    else:
        print("警告: 未找到预期的代码模式，文件可能已被修改")
        print("请手动检查文件内容")

except ImportError:
    print("错误: 无法导入litellm，请确保已安装")
    sys.exit(1)
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
