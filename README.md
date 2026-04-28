# LLM Generate Proxy - 通用大模型 API 转发代理

[![Python Version](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

一个轻量级、高性能的通用大模型 API 转发代理服务，支持透明转发多个主流 AI 平台（OpenAI、Anthropic、DeepSeek、阿里云百炼等），并提供完整的请求/响应日志记录。

## ✨ 核心特性

- **🔄 透明转发**：无需修改客户端代码，只需更改 `base_url` 即可使用
- **📝 完整日志**：自动记录所有请求和响应的详细信息（JSON 格式）
- **🌊 流式支持**：完美支持 SSE 流式响应，实时传输数据
- **🔗 多平台兼容**：通过路径前缀路由到不同的上游 API
- **⚡ 高性能**：基于 `aiohttp` 异步框架，支持高并发
- **🛡️ 健壮性**：完善的异常处理机制，区分连接中断与真实错误
- **🎯 零配置启动**：开箱即用，也可自定义配置

## 📋 目录

- [工作原理](#-工作原理)
- [支持的 API 平台](#-支持的-api-平台)
- [应用场景](#-应用场景)
- [快速开始](#-快速开始)
- [使用示例](#-使用示例)
- [配置说明](#-配置说明)
- [日志格式](#-日志格式)
- [常见问题](#-常见问题)
- [测试](#-测试)
- [开发](#-开发)

## 🔍 工作原理

### 架构图

```
Client App (OpenAI SDK / 其他客户端)
    ↓
┌─────────────────────────────────────┐
│   LLM Generate Proxy (端口 8080)     │
│                                     │
│  1. 解析路径前缀 → 确定上游平台       │
│  2. 转发请求到对应的上游 API          │
│  3. 记录完整请求/响应日志             │
│  4. 返回响应给客户端                  │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│   上游 API 平台                      │
│   • OpenAI (api.openai.com)         │
│   • Anthropic (api.anthropic.com)   │
│   • DeepSeek (api.deepseek.com)     │
│   • DashScope (阿里云百炼)           │
└─────────────────────────────────────┘
```

### 工作流程

1. **客户端发起请求**：使用 OpenAI SDK 或其他 HTTP 客户端向代理发送请求
   ```
   POST http://127.0.0.1:8080/dashscope-openai/v1/chat/completions
   ```

2. **路径解析**：代理提取路径前缀（如 `dashscope-openai`），查找对应的上游 base_url

3. **请求转发**：将请求透明转发到上游 API
   ```
   POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
   ```

4. **响应处理**：
   - **非流式响应**：等待完整响应后返回
   - **流式响应**：实时转发每个 chunk，同时缓冲完整内容用于日志

5. **日志记录**：以 JSON 格式记录完整的请求和响应信息到 `proxy_requests.log`

## 🌐 支持的 API 平台

| 路径前缀 | 上游 Base URL | 说明 |
|---------|--------------|------|
| `openai` | `https://api.openai.com` | OpenAI API |
| `anthropic` | `https://api.anthropic.com` | Anthropic Claude API |
| `deepseek` | `https://api.deepseek.com` | DeepSeek API |
| `dashscope-openai` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 阿里云百炼（OpenAI 兼容模式） |
| `dashscope-anthropic` | `https://dashscope.aliyuncs.com/apps/anthropic` | 阿里云百炼（Anthropic 兼容模式） |

**使用方式**：在客户端的 `base_url` 中添加对应的前缀即可。

例如：
- OpenAI: `http://127.0.0.1:8080/openai/v1/chat/completions`
- 阿里云百炼: `http://127.0.0.1:8080/dashscope-openai/v1/chat/completions`

### 添加新的 API 平台

编辑 [`main.py`](main.py) 中的 `API_MAPPING` 字典：

```python
API_MAPPING = {
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
    "deepseek": "https://api.deepseek.com",
    "dashscope-openai": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "dashscope-anthropic": "https://dashscope.aliyuncs.com/apps/anthropic",
    # 添加新的平台
    "your-platform": "https://your-api-endpoint.com",
}
```

## 🎯 应用场景

本代理服务器可与多种 AI 开发工具集成使用，以下是常见应用场景：

### 1. Claude Code CLI

[Claude Code](https://docs.anthropic.com/claude-code) 是 Anthropic 官方推出的命令行 AI 编程助手。通过本代理，您可以：

- **统一 API 管理**：集中管理多个 Claude API Key
- **完整日志记录**：自动记录所有 Claude Code 的对话和代码生成过程
- **灵活路由**：轻松切换不同的 Claude 模型或 API 提供商

**配置步骤：**

```bash
# 1. 启动代理服务器
uv run python main.py

# 2. 配置 Claude Code 使用本地代理
export ANTHROPIC_BASE_URL="http://127.0.0.1:8080/anthropic"
export ANTHROPIC_API_KEY="your-api-key"

# 3. 使用 Claude Code
claude "帮我创建一个 Python Flask 应用"
```

**优势：**
- ✅ 所有 Claude Code 的请求都会被记录到 `proxy_requests.log`
- ✅ 便于审计和回溯对话历史
- ✅ 可以在团队中共享同一个代理，统一管理 API Key

### 2. ccswitch (Claude Code Switch)

[ccswitch](https://github.com/your-repo/ccswitch) 是一个用于在多个 Claude API 端点之间切换的工具。配合本代理使用可以实现：

- **多账号负载均衡**：在多个 API Key 之间自动切换
- **故障转移**：当某个 API 不可用时自动切换到备用端点
- **成本优化**：根据不同场景选择最经济的 API 提供商

**配置示例：**

```python
# ccswitch 配置文件
{
    "endpoints": [
        {
            "name": "primary",
            "base_url": "http://127.0.0.1:8080/anthropic",
            "api_key": "sk-ant-primary"
        },
        {
            "name": "backup",
            "base_url": "http://127.0.0.1:8080/dashscope-anthropic",
            "api_key": "sk-dashscope-backup"
        }
    ],
    "strategy": "round-robin"  # 或 "failover"
}
```

**工作流程：**
```
ccswitch → LLM Generate Proxy → 上游 API
              ↓
         记录完整日志
```

### 3. 其他 AI 开发工具

本代理还可以与以下工具集成：

#### Cursor / VSCode AI 插件
```json
// .cursorrules 或 VSCode 设置
{
  "openai.baseURL": "http://127.0.0.1:8080/openai",
  "anthropic.baseURL": "http://127.0.0.1:8080/anthropic"
}
```

#### Continue.dev
```json
// config.json
{
  "models": [
    {
      "title": "Claude via Proxy",
      "provider": "anthropic",
      "model": "claude-3-sonnet-20240229",
      "apiKey": "your-key",
      "apiBase": "http://127.0.0.1:8080/anthropic"
    }
  ]
}
```

#### Aider (AI Pair Programming)
```bash
# 使用代理运行 aider
export ANTHROPIC_BASE_URL="http://127.0.0.1:8080/anthropic"
aider --model claude-3-sonnet-20240229
```

### 4. 团队协作场景

在团队开发环境中，本代理可以发挥更大价值：

**架构示意：**
```
开发者 A ──┐
开发者 B ──┼──→ LLM Generate Proxy ──→ 上游 API
开发者 C ──┘         ↓
                  统一日志中心
```

**优势：**
- 📊 **用量统计**：基于日志分析每个开发者的 API 使用情况
- 🔒 **权限控制**：集中管理 API Key，避免泄露
- 💰 **成本控制**：监控和优化 API 调用成本
- 📝 **知识沉淀**：保存所有对话记录，形成团队知识库

### 5. 自定义工作流

您可以基于代理日志构建自定义工作流：

```python
# 示例：从日志中提取代码片段
import json

with open('proxy_requests.log', 'r') as f:
    for line in f:
        log_entry = json.loads(line)
        if log_entry['response']['status_code'] == 200:
            # 提取生成的代码
            response_body = log_entry['response']['body']
            # 处理代码片段...
```

---

## 🚀 快速开始

### 前置要求

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) 包管理工具（推荐）或 pip

### 安装步骤

#### 方法一：使用 uv（推荐）

```bash
# 克隆仓库
git clone <repository-url>
cd llm-generate-proxy

# 初始化虚拟环境并安装依赖
uv sync

# 或者手动安装
uv init
uv add aiohttp openai python-dotenv
```

#### 方法二：使用 pip

```bash
pip install aiohttp openai python-dotenv
```

### 配置 API Key

1. 复制配置文件示例：
   ```bash
   cp .env.example .env
   ```

2. 编辑 `.env` 文件，填入你的 API Key：
   ```env
   # 阿里云百炼 API Key
   DASHSCOPE_API_KEY=sk-your-dashscope-api-key-here
   
   # OpenAI API Key (可选)
   OPENAI_API_KEY=sk-your-openai-api-key-here
   
   # Anthropic API Key (可选)
   ANTHROPIC_API_KEY=sk-ant-your-anthropic-api-key-here
   
   # DeepSeek API Key (可选)
   DEEPSEEK_API_KEY=sk-your-deepseek-api-key-here
   ```

3. 获取 API Key：
   - **阿里云百炼**: [获取 API Key](https://help.aliyun.com/zh/model-studio/get-api-key)
   - **OpenAI**: [Platform API Keys](https://platform.openai.com/api-keys)
   - **Anthropic**: [Console API Keys](https://console.anthropic.com/settings/keys)
   - **DeepSeek**: [Platform Settings](https://platform.deepseek.com/settings)

### 启动代理服务器

```bash
# 使用 uv 运行（推荐）
uv run python main.py

# 或使用 Python 直接运行
python main.py

# 自定义端口和日志文件
uv run python main.py --port 9000 --log-file custom.log
```

启动成功后会看到类似输出：
```
2026-04-28 19:00:00 | 代理启动，监听 0.0.0.0:8080
2026-04-28 19:00:00 | 支持的 API 前缀: ['openai', 'anthropic', 'deepseek', 'dashscope-openai', 'dashscope-anthropic']
2026-04-28 19:00:00 | 日志文件: proxy_requests.log
```

## 💻 使用示例

### 示例 1：使用 OpenAI SDK 调用阿里云百炼

```
import os
from dotenv import load_dotenv
from openai import OpenAI

# 加载环境变量
load_dotenv()

client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="http://127.0.0.1:8080/dashscope-openai",  # 指向本地代理
)

# 非流式对话
completion = client.chat.completions.create(
    model="qwen-plus-latest",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "你好！"},
    ],
)
print(completion.choices[0].message.content)
```

### 示例 2：流式响应

```
stream = client.chat.completions.create(
    model="qwen-plus-latest",
    messages=[{"role": "user", "content": "介绍下你自己"}],
    stream=True,
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

### 示例 3：调用 OpenAI API

```
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="http://127.0.0.1:8080/openai",  # 使用 openai 前缀
)

completion = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(completion.choices[0].message.content)
```

### 示例 4：调用 Anthropic API

```
import anthropic

client = anthropic.Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    base_url="http://127.0.0.1:8080/anthropic",  # 使用 anthropic 前缀
)

message = client.messages.create(
    model="claude-3-sonnet-20240229",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello!"}],
)
print(message.content[0].text)
```

### 示例 5：直接使用 HTTP 请求

```
import requests
import json

response = requests.post(
    "http://127.0.0.1:8080/dashscope-openai/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {os.getenv('DASHSCOPE_API_KEY')}",
        "Content-Type": "application/json",
    },
    json={
        "model": "qwen-plus-latest",
        "messages": [{"role": "user", "content": "你好"}],
    },
)

print(response.json())
```

## ⚙️ 配置说明

### 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--port` | `8080` | 代理服务器监听端口 |
| `--log-file` | `proxy_requests.log` | 日志文件路径 |

### 超时配置

修改 `REQUEST_TIMEOUT` 常量（默认 300 秒）：

```python
REQUEST_TIMEOUT = 300  # 单位：秒
```

## 📝 日志格式

代理会自动将所有请求和响应记录到日志文件（默认 `proxy_requests.log`），格式为 JSON：

### 非流式响应日志示例

```
{
  "timestamp": "2026-04-28T19:00:00",
  "request": {
    "method": "POST",
    "path": "/dashscope-openai/v1/chat/completions",
    "upstream_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    "headers": {
      "Authorization": "Bearer sk-xxx",
      "Content-Type": "application/json"
    },
    "body": "{\"model\":\"qwen-plus-latest\",\"messages\":[{\"role\":\"user\",\"content\":\"你好\"}]}"
  },
  "response": {
    "status_code": 200,
    "elapsed_seconds": 1.234,
    "headers": {
      "Content-Type": "application/json",
      "X-Request-Id": "xxx"
    },
    "body": "{\"choices\":[{\"message\":{\"content\":\"你好！有什么可以帮助你的？\"}}]}",
    "is_streaming": false
  }
}
```

### 流式响应日志示例

```
{
  "timestamp": "2026-04-28T19:00:00",
  "request": { ... },
  "response": {
    "status_code": 200,
    "elapsed_seconds": 2.567,
    "headers": { ... },
    "body": "data: {...}\n\ndata: {...}\n\n...",
    "is_streaming": true
  }
}
```

### 日志字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `timestamp` | string | ISO 8601 格式时间戳 |
| `request.method` | string | HTTP 方法 |
| `request.path` | string | 原始请求路径 |
| `request.upstream_url` | string | 转发到的上游 URL |
| `request.headers` | object | 请求头（不含 Host） |
| `request.body` | string | 请求体（UTF-8 解码） |
| `response.status_code` | integer | 响应状态码 |
| `response.elapsed_seconds` | float | 请求耗时（秒） |
| `response.headers` | object | 响应头 |
| `response.body` | string | 响应体（UTF-8 解码） |
| `response.is_streaming` | boolean | 是否为流式响应 |

## ❓ 常见问题

### Q1: 为什么要使用代理而不是直接调用 API？

**A:** 代理提供以下优势：
- **统一入口**：多个应用共享同一个代理，集中管理 API Key
- **完整日志**：自动记录所有请求和响应，便于调试和审计
- **灵活路由**：通过路径前缀轻松切换不同的 API 提供商
- **监控分析**：基于日志进行用量统计、性能分析等

### Q2: 流式响应和非流式响应有什么区别？

**A:** 
- **非流式响应**：等待服务器返回完整结果后一次性返回，适合短文本
- **流式响应**：逐字返回生成内容，用户体验更好，适合长文本生成

代理会自动检测响应类型并采用相应的处理方式。

### Q3: 如何查看实时日志？

**A:** 使用 `tail` 命令（Linux/Mac）或 PowerShell（Windows）：

```bash
# Linux/Mac
tail -f proxy_requests.log

# Windows PowerShell
Get-Content proxy_requests.log -Wait -Tail 50
```

### Q4: 日志文件太大怎么办？

**A:** 可以：
1. 定期清理旧日志文件
2. 使用日志轮转工具（如 `logrotate`）
3. 修改代码添加日志大小限制

### Q5: 支持哪些编程语言和 SDK？

**A:** 理论上支持任何能发送 HTTP 请求的语言。已验证兼容：
- Python (OpenAI SDK, Anthropic SDK)
- JavaScript/TypeScript (OpenAI SDK)
- Go, Java, Rust 等

只要遵循 OpenAI 或 Anthropic 的 API 规范即可。

### Q6: 如何处理认证和安全？

**A:** 
- **不要将 `.env` 文件提交到 Git**（已在 `.gitignore` 中配置）
- 生产环境建议使用环境变量或密钥管理服务
- 可以考虑添加 IP 白名单、速率限制等安全机制

### Q7: 代理的性能如何？

**A:** 基于 `aiohttp` 异步框架，单实例可处理数百并发请求。如需更高性能，可以：
- 使用多个代理实例 + 负载均衡
- 调整系统文件描述符限制
- 优化网络配置

## 🧪 测试

项目包含完整的测试脚本 [`test.py`](test.py)，用于验证代理功能。

### 运行测试

1. **确保代理服务器已启动**：
   ```bash
   uv run python main.py
   ```

2. **在另一个终端运行测试**：
   ```bash
   uv run python test.py
   ```

### 测试覆盖范围

- ✅ 非流式响应测试
- ✅ 流式响应测试
- ✅ 错误处理（API Key 缺失、服务未启动等）

### 预期输出

```
============================================================
测试 1: 非流式响应
============================================================
🚀 正在发送请求到代理服务器...

✅ 响应内容:
1+1=2

📊 元数据:
   模型: qwen-plus-latest
   Token 使用: CompletionUsage(...)

============================================================
测试 2: 流式响应
============================================================
🚀 正在发送流式请求...

✅ 流式响应内容:
我是一个人工智能助手...

✨ 所有测试完成!
```

## 👨‍💻 开发

### 项目结构

```
llm-generate-proxy/
├── main.py              # 主程序（代理服务器）
├── test.py              # 测试脚本
├── pyproject.toml       # 项目配置和依赖
├── uv.lock             # 依赖锁定文件
├── .env.example        # 环境变量示例
├── .gitignore          # Git 忽略规则
├── README.md           # 项目文档
└── proxy_requests.log  # 运行时生成的日志文件
```

### 核心模块说明

- **路径解析**：[`extract_path_prefix()`](main.py) 和 [`build_upstream_url()`](main.py) 负责解析路径前缀并构建上游 URL
- **请求处理**：[`handle_request()`](main.py) 是核心处理器，负责透明转发和日志记录
- **流式处理**：自动检测流式响应并使用 `web.StreamResponse` 实时转发
- **日志记录**：[`setup_logger()`](main.py) 配置 JSON 格式的日志记录器

### 添加新功能

1. **新增 API 平台**：在 `API_MAPPING` 中添加映射
2. **自定义日志格式**：修改 `setup_logger()` 函数
3. **添加中间件**：在 `handle_request()` 中添加预处理逻辑
4. **性能优化**：考虑连接池、缓存等机制

### 贡献指南

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 🙏 致谢

- [aiohttp](https://docs.aiohttp.org/) - 高性能异步 HTTP 框架
- [OpenAI SDK](https://github.com/openai/openai-python) - OpenAI 官方 Python SDK
- [uv](https://github.com/astral-sh/uv) - 超快的 Python 包管理器

---

**注意**：本项目仅供学习和研究使用，请遵守各 API 平台的使用条款和法律法规。
