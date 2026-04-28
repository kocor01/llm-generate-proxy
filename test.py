import os
from openai import OpenAI

try:
    client = OpenAI(
        # 各地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
        # 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：api_key="sk-xxx",
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        # 各地域的base_url不同
        base_url="http:127.0.0.1:8080/dashscope/compatible-mode/v1",
    )

    completion = client.chat.completions.create(
        model="qwen3.6-plus",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "你是谁？"},
        ],
    )
    print(completion.choices[0].message.content)
    # 如需查看完整响应，请取消下列注释
    # print(completion.model_dump_json())
except Exception as e:
    print(f"错误信息：{e}")
    print("请参考文档：https://help.aliyun.com/zh/model-studio/developer-reference/error-code")