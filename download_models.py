#!/usr/bin/env python
"""
下载 Hugging Face 模型到本地缓存
"""
import os
import sys

# 设置镜像地址
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
os.environ['HF_HUB_ENDPOINT'] = 'https://hf-mirror.com'

print("正在下载模型...")
print(f"镜像地址: {os.environ.get('HF_HUB_ENDPOINT')}")
print("=" * 60)

try:
    from transformers import AutoTokenizer, AutoModel
    
    cache_dir = './models/hf_cache'
    
    # 下载 Embedding 模型
    print("\n1. 下载 Embedding 模型: Qwen/Qwen3-Embedding-0.6B")
    print("-" * 60)
    tokenizer = AutoTokenizer.from_pretrained(
        "Qwen/Qwen3-Embedding-0.6B",
        trust_remote_code=True,
        local_files_only=False,
        cache_dir=cache_dir,
    )
    print("✓ Tokenizer 下载完成")
    
    model = AutoModel.from_pretrained(
        "Qwen/Qwen3-Embedding-0.6B",
        trust_remote_code=True,
        local_files_only=False,
        cache_dir=cache_dir,
    )
    print("✓ Model 下载完成")
    
    # 下载 Reranker 模型
    print("\n2. 下载 Reranker 模型: Qwen/Qwen3-Reranker-0.6B")
    print("-" * 60)
    tokenizer = AutoTokenizer.from_pretrained(
        "Qwen/Qwen3-Reranker-0.6B",
        trust_remote_code=True,
        local_files_only=False,
        cache_dir=cache_dir,
    )
    print("✓ Tokenizer 下载完成")
    
    model = AutoModel.from_pretrained(
        "Qwen/Qwen3-Reranker-0.6B",
        trust_remote_code=True,
        local_files_only=False,
        cache_dir=cache_dir,
    )
    print("✓ Model 下载完成")
    
    print("\n" + "=" * 60)
    print("✓ 所有模型下载成功！")
    print("=" * 60)
    
except KeyboardInterrupt:
    print("\n\n⚠ 下载已取消")
    sys.exit(1)
except Exception as e:
    print(f"\n\n✗ 下载失败: {e}")
    sys.exit(1)
