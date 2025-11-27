#!/usr/bin/env python3
"""
Ollama连通性测试脚本

用于验证Ollama后端是否正常工作
运行前确保已在华为内网环境中
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm.llm_client import LLMClient
from loguru import logger

# 配置日志
logger.remove()
logger.add(sys.stderr, level="INFO")


def test_ollama_connection():
    """测试Ollama连接"""
    print("=" * 80)
    print("Ollama连通性测试")
    print("=" * 80)
    print()

    # Ollama配置
    host = "http://10.78.108.45:11434"
    model = "qwen3:4b-instruct-2507-fp16"

    print(f"🔧 配置信息:")
    print(f"   Host: {host}")
    print(f"   Model: {model}")
    print()

    # 创建LLM客户端
    print("📡 创建Ollama客户端...")
    try:
        client = LLMClient(
            backend='ollama',
            host=host,
            model=model,
            timeout=60  # 设置较短的超时用于测试
        )
        print("✅ 客户端创建成功")
    except Exception as e:
        print(f"❌ 客户端创建失败: {e}")
        return False

    print()

    # 检查可用性
    print("🔍 检查后端可用性...")
    if client.is_available():
        print("✅ 后端可用")
        print(f"   后端信息: {client.get_backend_info()}")
    else:
        print("❌ 后端不可用（可能网络连接失败或服务未启动）")
        return False

    print()

    # 测试列出模型（如果支持）
    print("📋 尝试列出可用模型...")
    try:
        if hasattr(client.backend, 'list_models'):
            models = client.backend.list_models()
            if models:
                print(f"✅ 可用模型列表:")
                for i, m in enumerate(models, 1):
                    print(f"   {i}. {m}")
            else:
                print("⚠️  未获取到模型列表")
    except Exception as e:
        print(f"⚠️  列出模型时出错: {e}")

    print()

    # 测试简单对话
    print("💬 测试简单对话...")
    print("   问题: '1+1等于几？只回答数字。'")
    try:
        response = client.complete(
            prompt="1+1等于几？只回答数字。",
            system_prompt="你是一个数学助手。",
            temperature=0.1,
            max_tokens=50,
            timeout=30
        )

        if response:
            print(f"✅ 对话成功")
            print(f"   响应: {response.strip()}")
        else:
            print("❌ 对话失败：未收到响应")
            return False
    except Exception as e:
        print(f"❌ 对话失败: {e}")
        return False

    print()

    # 测试代码分析能力
    print("🔬 测试代码分析能力...")
    print("   任务: 分析一个简单的C函数")

    test_code = """
void test_function(void) {
    int x = 5;
    int y = 10;
    printf("Sum is %d\\n", x + y);
}
"""

    try:
        response = client.complete(
            prompt=f"""分析以下C函数，简要说明它的功能（一句话）：

```c
{test_code}
```

只返回功能描述，不要其他内容。""",
            system_prompt="你是一个C代码分析专家。",
            temperature=0.3,
            max_tokens=100,
            timeout=30
        )

        if response:
            print(f"✅ 代码分析成功")
            print(f"   分析结果: {response.strip()}")
        else:
            print("❌ 代码分析失败：未收到响应")
            return False
    except Exception as e:
        print(f"❌ 代码分析失败: {e}")
        return False

    print()

    # 测试JSON输出格式
    print("📝 测试JSON输出格式...")
    try:
        response = client.complete(
            prompt="""请以JSON格式返回以下信息：
{
  "name": "Ollama",
  "status": "working",
  "capabilities": ["chat", "code_analysis"]
}

只返回JSON，不要其他内容。""",
            system_prompt="你是一个助手，擅长返回结构化数据。",
            temperature=0.1,
            max_tokens=200,
            timeout=30
        )

        if response:
            print(f"✅ JSON输出成功")
            print(f"   响应: {response.strip()}")
            # 尝试解析JSON
            import json
            try:
                # 清理响应中的markdown代码块标记
                cleaned = response.strip()
                if '```json' in cleaned:
                    cleaned = cleaned.split('```json')[1].split('```')[0].strip()
                elif '```' in cleaned:
                    cleaned = cleaned.split('```')[1].split('```')[0].strip()

                parsed = json.loads(cleaned)
                print(f"   ✅ JSON解析成功: {parsed}")
            except json.JSONDecodeError as e:
                print(f"   ⚠️  JSON解析失败: {e}")
        else:
            print("❌ JSON输出失败：未收到响应")
            return False
    except Exception as e:
        print(f"❌ JSON输出测试失败: {e}")
        return False

    print()
    print("=" * 80)
    print("✅ 所有测试通过！Ollama后端工作正常。")
    print("=" * 80)
    return True


def test_openai_compatible():
    """测试华为OpenAI-compatible API（仅供参考）"""
    print()
    print("=" * 80)
    print("华为OpenAI-compatible API测试（需要API Key）")
    print("=" * 80)
    print()

    # 华为OpenAI-compatible配置
    base_url = "http://openai.md.huawei.com/"
    model = "DS-V3-0324"  # 或其他支持的模型

    print(f"🔧 配置信息:")
    print(f"   Base URL: {base_url}")
    print(f"   Model: {model}")
    print(f"   API Key: (需要从用户获取)")
    print()
    print("⚠️  由于需要API Key，此测试跳过。")
    print("   如需测试，请修改此脚本添加你的API Key。")
    print()

    # 如果有API Key，取消注释以下代码：
    # api_key = "your_api_key_here"
    # client = LLMClient(
    #     backend='openai',
    #     base_url=base_url,
    #     api_key=api_key,
    #     model=model
    # )
    # # ... 进行测试


if __name__ == "__main__":
    print()
    print("🚀 开始Ollama后端测试...")
    print()

    # 主测试
    success = test_ollama_connection()

    # 可选：测试华为OpenAI-compatible API
    # test_openai_compatible()

    print()
    if success:
        print("✅ 测试完成，一切正常！")
        sys.exit(0)
    else:
        print("❌ 测试失败，请检查网络连接和Ollama服务状态。")
        sys.exit(1)
