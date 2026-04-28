# LLM Generate Proxy

通用大模型 API 转发代理 - 简化版

## 功能特性

- 透明转发多个大模型 API (OpenAI, Anthropic, DeepSeek, DashScope)
- 完整的请求/响应日志记录 (JSON 格式)
- 支持流式和非流式响应
- 基于 aiohttp 的高性能异步实现

## 环境要求

- Python 3.13+
- uv (Python 包管理工具)

## 安装

```bash
# 使用 uv 安装依赖
uv sync
```

## 使用方法

### 启动代理服务器

```bash
# 默认端口 8080
uv run python main.py

# 指定端口
uv run python main.py --port 9000

# 指定日志文件
uv run python main.py --log-file custom.log
```

### 支持的 API 前缀

- `/openai/*` -> https://api.openai.com
- `/anthropic/*` -> https://api.anthropic.com
- `/deepseek/*` -> https://api.deepseek.com
- `/dashscope/*` -> https://dashscope.aliyuncs.com/compatible-mode/v1

### 示例请求

```python
from openai import OpenAI

client = OpenAI(
    api_key="your-api-key",
    base_url="http://127.0.0.1:8080/dashscope/compatible-mode/v1",
)

completion = client.chat.completions.create(
    model="qwen3.6-plus",
    messages=[
        {"role": "user", "content": "你是谁？"},
    ],
)
print(completion.choices[0].message.content)
```

## 配置

在 `main.py` 中修改 `API_MAPPING` 配置来添加或修改上游 API:

```python
API_MAPPING = {
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
    "deepseek": "https://api.deepseek.com",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
}
```

## 日志

所有请求和响应都会记录到日志文件 (默认 `proxy_requests.log`),格式为 JSON,包含:
- 请求方法、路径、URL
- 请求头和请求体
- 响应状态码、响应时间
- 响应头和响应体

## 开发

```bash
# 添加新依赖
uv add package-name

# 运行测试
uv run python test.py
```
