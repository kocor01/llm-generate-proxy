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

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置 API Key

复制示例配置文件并填写你的 API Key：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 API Key：

```env
DASHSCOPE_API_KEY=sk-your-actual-api-key-here
```

**获取 API Key:**
- 阿里云百炼: https://help.aliyun.com/zh/model-studio/get-api-key

### 3. 启动代理服务器

```bash
# 默认端口 8080
uv run python main.py

# 指定端口
uv run python main.py --port 9000

# 指定日志文件
uv run python main.py --log-file custom.log
```

### 4. 测试代理

在另一个终端窗口运行：

```bash
uv run python test.py
```

## 支持的 API 前缀

| 前缀 | 上游 URL |
|------|----------|
| `/openai/*` | https://api.openai.com |
| `/anthropic/*` | https://api.anthropic.com |
| `/deepseek/*` | https://api.deepseek.com |
| `/dashscope/*` | https://dashscope.aliyuncs.com/compatible-mode/v1 |

## 使用示例

### Python (OpenAI SDK)

```python
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="http://127.0.0.1:8080/dashscope/compatible-mode/v1",
)

completion = client.chat.completions.create(
    model="qwen-plus",
    messages=[
        {"role": "user", "content": "你是谁？"},
    ],
)
print(completion.choices[0].message.content)
```

### cURL

```bash
curl http://127.0.0.1:8080/dashscope/compatible-mode/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DASHSCOPE_API_KEY" \
  -d '{
    "model": "qwen-plus",
    "messages": [{"role": "user", "content": "你好"}]
  }'
```

## 配置

在 [`main.py`](file://d:\code\llm-generate-proxy\main.py) 中修改 `API_MAPPING` 配置来添加或修改上游 API：

```python
API_MAPPING = {
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
    "deepseek": "https://api.deepseek.com",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
}
```

## 日志

所有请求和响应都会记录到日志文件 (默认 `proxy_requests.log`)，格式为 JSON，包含：
- 请求方法、路径、URL
- 请求头和请求体
- 响应状态码、响应时间
- 响应头和响应体

查看日志：

```bash
# Linux/Mac
tail -f proxy_requests.log

# Windows PowerShell
Get-Content proxy_requests.log -Wait
```

## 开发

```bash
# 添加新依赖
uv add package-name

# 移除依赖
uv remove package-name

# 更新所有依赖
uv lock --upgrade

# 运行测试
uv run python test.py
```

## 常见问题

### Q: 提示 "未设置 DASHSCOPE_API_KEY 环境变量"

**A:** 请确保：
1. 已创建 `.env` 文件并填写了正确的 API Key
2. 已安装 `python-dotenv` 包（已通过 `uv sync` 安装）
3. 或者手动设置环境变量：
   ```bash
   # Windows PowerShell
   $env:DASHSCOPE_API_KEY="sk-your-key"
   
   # Linux/Mac
   export DASHSCOPE_API_KEY="sk-your-key"
   ```

### Q: 连接被拒绝

**A:** 确保代理服务器正在运行：
```bash
uv run python main.py
```

### Q: 如何添加新的 API 提供商？

**A:** 在 `main.py` 的 `API_MAPPING` 中添加新的映射：
```python
API_MAPPING = {
    # ... existing mappings ...
    "your-provider": "https://api.your-provider.com/v1",
}
```

## 许可证

MIT
