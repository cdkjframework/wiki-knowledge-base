"""
Universal LLM Client 测试示例
演示如何使用 UniversalLLMClient 连接各种 AI 模型服务
"""

from src.universal_llm_client import UniversalLLMClient, UniversalLLMError


def test_basic_usage():
    """基础用法测试"""
    print("=" * 60)
    print("测试 1: 基础用法")
    print("=" * 60)
    
    # 使用 from_provider 方法（推荐）
    client = UniversalLLMClient.from_provider(
        provider="lm_studio",  # 本地测试
        api_key=None,
        timeout=30
    )
    
    print(f"Provider: {client.provider}")
    print(f"Base URL: {client.base_url}")
    print()


def test_multiple_providers():
    """测试多个提供商"""
    print("=" * 60)
    print("测试 2: 多提供商支持")
    print("=" * 60)
    
    providers = [
        ("openai", "https://api.openai.com/v1"),
        ("deepseek", "https://api.deepseek.com/v1"),
        ("qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        ("kimi", "https://api.moonshot.cn/v1"),
        ("lm_studio", "http://localhost:1234/v1"),
    ]
    
    for provider, expected_url in providers:
        try:
            client = UniversalLLMClient.from_provider(
                provider=provider,
                api_key="test-key"
            )
            print(f"✓ {provider:12} -> {client.base_url}")
            assert client.base_url == expected_url
        except Exception as e:
            print(f"✗ {provider:12} -> Error: {e}")
    print()


def test_auto_detection():
    """测试自动提供商检测"""
    print("=" * 60)
    print("测试 3: 自动提供商检测")
    print("=" * 60)
    
    test_cases = [
        ("https://api.openai.com/v1", "openai"),
        ("https://api.deepseek.com/v1", "deepseek"),
        ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen"),
        ("https://ark.cn-beijing.volces.com/api/v3", "doubao"),
        ("https://api.x.ai/v1", "xai"),
        ("https://api.moonshot.cn/v1", "kimi"),
        ("http://localhost:1234/v1", "lm_studio"),
    ]
    
    for url, expected_provider in test_cases:
        client = UniversalLLMClient(base_url=url, api_key="test")
        detected = client.provider
        status = "✓" if detected == expected_provider else "✗"
        print(f"{status} {url:60} -> {detected}")
    print()


def test_chat_example():
    """聊天示例（需要实际 API key）"""
    print("=" * 60)
    print("测试 4: 聊天示例（演示代码）")
    print("=" * 60)
    
    # 示例代码（不实际执行，需要 API key）
    example_code = '''
# OpenAI 示例
client = UniversalLLMClient.from_provider(
    provider="openai",
    api_key="sk-your-openai-key"
)

response = client.chat_once(
    messages=[{"role": "user", "content": "你好"}],
    model="gpt-4",
    temperature=0.7
)
print(response)

# 流式响应示例
for chunk in client.chat_stream(
    messages=[{"role": "user", "content": "写一首诗"}],
    model="gpt-4"
):
    print(chunk, end="", flush=True)
'''
    print(example_code)
    print()


def test_embedding_example():
    """嵌入向量示例"""
    print("=" * 60)
    print("测试 5: 嵌入向量示例（演示代码）")
    print("=" * 60)
    
    example_code = '''
import numpy as np

client = UniversalLLMClient.from_provider(
    provider="openai",
    api_key="sk-your-key"
)

texts = ["文本1", "文本2", "文本3"]
embeddings = client.embed_texts(
    texts=texts,
    model="text-embedding-ada-002"
)

print(f"Shape: {embeddings.shape}")  # (3, 1536)
print(f"Type: {embeddings.dtype}")   # float32

# 计算相似度
similarity = np.dot(embeddings[0], embeddings[1])
print(f"Similarity: {similarity}")
'''
    print(example_code)
    print()


def test_error_handling():
    """错误处理测试"""
    print("=" * 60)
    print("测试 6: 错误处理")
    print("=" * 60)
    
    # 测试未知提供商
    try:
        client = UniversalLLMClient.from_provider(
            provider="unknown_provider",
            api_key="test"
        )
        print("✗ 应该抛出异常")
    except ValueError as e:
        print(f"✓ 正确捕获异常: {e}")
    
    print()


def test_custom_headers():
    """自定义请求头测试"""
    print("=" * 60)
    print("测试 7: 自定义请求头")
    print("=" * 60)
    
    client = UniversalLLMClient(
        base_url="https://api.example.com/v1",
        api_key="test-key",
        extra_headers={
            "X-Custom-Header": "custom-value",
            "X-Request-ID": "12345"
        }
    )
    
    headers = client._build_headers()
    print("生成的请求头:")
    for key, value in headers.items():
        print(f"  {key}: {value}")
    print()


def test_backward_compatibility():
    """向后兼容性测试"""
    print("=" * 60)
    print("测试 8: 向后兼容性")
    print("=" * 60)
    
    # 使用旧的导入方式
    from src.lm_studio_client import LmStudioClient, LmStudioRequestError
    
    # 创建客户端（应该仍然工作）
    client = LmStudioClient(
        base_url="http://localhost:1234/v1",
        api_key=None
    )
    
    print(f"✓ LmStudioClient 类型: {type(client).__name__}")
    print(f"✓ Base URL: {client.base_url}")
    print("✓ 向后兼容性正常")
    print()


def test_provider_list():
    """提供商列表测试"""
    print("=" * 60)
    print("测试 9: 支持的提供商列表")
    print("=" * 60)
    
    print("支持的提供商:")
    for provider, endpoint in UniversalLLMClient.PROVIDER_ENDPOINTS.items():
        print(f"  - {provider:12} : {endpoint}")
    print()


def main():
    """运行所有测试"""
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 10 + "Universal LLM Client 测试套件" + " " * 18 + "║")
    print("╚" + "═" * 58 + "╝")
    print()
    
    tests = [
        test_basic_usage,
        test_multiple_providers,
        test_auto_detection,
        test_provider_list,
        test_custom_headers,
        test_error_handling,
        test_backward_compatibility,
        test_chat_example,
        test_embedding_example,
    ]
    
    for test_func in tests:
        try:
            test_func()
        except Exception as e:
            print(f"✗ 测试失败: {test_func.__name__}")
            print(f"  错误: {e}")
            import traceback
            traceback.print_exc()
            print()
    
    print("=" * 60)
    print("✓ 所有测试完成")
    print("=" * 60)
    print()
    
    # 使用提示
    print("使用提示:")
    print("1. 查看详细文档: docs/UNIVERSAL_LLM_CLIENT.md")
    print("2. 配置示例: config.multi-provider.example.json")
    print("3. 对比文档: docs/CLIENT_COMPARISON.md")
    print()


if __name__ == "__main__":
    main()
