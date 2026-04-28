import os
from dotenv import load_dotenv
from openai import OpenAI

# 加载 .env 文件中的环境变量
load_dotenv()

try:
    # 获取 API Key
    api_key = os.getenv("DASHSCOPE_API_KEY")
    
    if not api_key:
        print("❌ 错误: 未设置 DASHSCOPE_API_KEY 环境变量")
        print("请执行以下操作之一:")
        print("  1. 复制 .env.example 为 .env 并填写你的 API Key")
        print("  2. 或者设置环境变量: $env:DASHSCOPE_API_KEY='sk-xxx'")
        print("\n获取 API Key: https://help.aliyun.com/zh/model-studio/get-api-key")
        exit(1)
    
    client = OpenAI(
        api_key=api_key,
        # 注意: base_url 指向本地代理服务器
        base_url="http://127.0.0.1:8080/dashscope-openai",
    )

    print("=" * 60)
    print("测试 1: 非流式响应")
    print("=" * 60)
    print("🚀 正在发送请求到代理服务器...")
    completion = client.chat.completions.create(
        model="qwen-plus-latest",  # 使用阿里云百炼的模型
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "1+1=?"},
        ],
    )
    print("\n✅ 响应内容:")
    print(completion.choices[0].message.content)
    print(f"\n📊 元数据:")
    print(f"   模型: {completion.model}")
    print(f"   Token 使用: {completion.usage}")
    
    # 测试流式响应
    print("\n" + "=" * 60)
    print("测试 2: 流式响应")
    print("=" * 60)
    print("🚀 正在发送流式请求...")
    
    stream = client.chat.completions.create(
        model="qwen-plus-latest",
        messages=[
            {"role": "user", "content": "请用一句话介绍你自己"},
        ],
        stream=True,
    )
    
    print("\n✅ 流式响应内容:")
    for chunk in stream:
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
    print("\n")
    
    # 如需查看完整响应，请取消下列注释
    # print("\n完整响应:")
    # print(completion.model_dump_json(indent=2))
    
    print("\n✨ 所有测试完成!")
    
except Exception as e:
    print(f"\n❌ 错误信息: {e}")
    print("\n可能的原因:")
    print("  1. 代理服务器未启动 - 请先运行: uv run python main.py")
    print("  2. API Key 无效或已过期")
    print("  3. 网络连接问题")
    print(f"\n详细错误: {type(e).__name__}: {str(e)}")
