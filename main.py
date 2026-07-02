#!/usr/bin/env python3
"""
通用大模型 API 转发代理 - 简化版
核心功能：透明转发 + 完整日志记录
"""
import asyncio
import json
import logging
import time
import argparse
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from aiohttp import web, ClientSession, ClientTimeout, ClientError

# ==================== 配置区域 ====================

# API 映射配置：路径前缀 -> 上游 base_url
API_MAPPING = {
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
    "deepseek": "https://api.deepseek.com",
    "dashscope-openai": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "dashscope-anthropic": "https://dashscope.aliyuncs.com/apps/anthropic",
}

DEFAULT_PORT = 8881
LOG_FILE = "proxy_requests.log"
REQUEST_TIMEOUT = 3000

# ==================== 日志配置 ====================

def setup_logger(log_file: str = LOG_FILE) -> logging.Logger:
    """配置 JSON 格式日志记录器"""
    logger = logging.getLogger("proxy")
    logger.setLevel(logging.INFO)
    
    # 文件处理器
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    logger.addHandler(fh)
    
    # 控制台处理器
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "%(asctime)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    ch.setFormatter(console_formatter)
    logger.addHandler(ch)
    
    return logger

logger: Optional[logging.Logger] = None

# ==================== 工具函数 ====================

def safe_json_parse(value: str) -> Any:
    """安全地将字符串解析为JSON，如果解析失败则返回原字符串"""
    if not value or not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value

def extract_path_prefix(path: str) -> tuple[str, str]:
    """从路径中提取前缀和剩余路径"""
    parts = path.strip("/").split("/", 1)
    if not parts or not parts[0]:
        return "", path
    
    prefix = parts[0]
    remaining = "/" + parts[1] if len(parts) > 1 else "/"
    return prefix, remaining

def build_upstream_url(prefix: str, remaining_path: str, query_string: str) -> Optional[str]:
    """构建上游 URL"""
    if prefix not in API_MAPPING:
        return None
    
    base_url = API_MAPPING[prefix].rstrip("/")
    upstream_url = base_url + remaining_path
    
    if query_string:
        upstream_url += "?" + query_string
    
    return upstream_url

# ==================== 流式响应适配器 ====================

@dataclass
class StreamChunk:
    """统一的流式响应块结构"""
    content: str = ""
    reasoning_content: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None

class StreamAdapter(ABC):
    """流式响应适配器基类"""
    
    @abstractmethod
    def parse_chunk(self, line: str) -> Optional[StreamChunk]:
        """解析单个数据块"""
        pass
    
    @abstractmethod
    def can_handle(self, first_chunk: str) -> bool:
        """判断是否能处理该格式的数据"""
        pass
    
    def aggregate(self, chunks: List[StreamChunk]) -> Dict[str, Any]:
        """聚合所有块，返回统一格式"""
        content_parts = []
        reasoning_parts = []
        all_tool_calls = []
        finish_reason = None
        usage = None
        
        for chunk in chunks:
            if chunk.content:
                content_parts.append(chunk.content)
            if chunk.reasoning_content:
                reasoning_parts.append(chunk.reasoning_content)
            if chunk.tool_calls:
                all_tool_calls.extend(chunk.tool_calls)
            if chunk.finish_reason:
                finish_reason = chunk.finish_reason
            if chunk.usage:
                usage = chunk.usage
        
        merged_tool_calls = self._merge_tool_calls(all_tool_calls)
        
        return {
            "content": "".join(content_parts),
            "reasoning_content": "".join(reasoning_parts),
            "tool_calls": merged_tool_calls,
            "finish_reason": finish_reason,
            "usage": usage
        }
    
    def _merge_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """合并相同 index 的 tool_calls"""
        if not tool_calls:
            return []
        
        merged = {}
        for tc in tool_calls:
            index = tc.get("index", 0)
            if index not in merged:
                merged[index] = {
                    "index": index,
                    "id": tc.get("id", ""),
                    "type": tc.get("type", "function"),
                    "function": {
                        "name": "",
                        "arguments": ""
                    }
                }
            
            if "function" in tc:
                if "name" in tc["function"] and tc["function"]["name"]:
                    merged[index]["function"]["name"] = tc["function"]["name"]
                if "arguments" in tc["function"] and tc["function"]["arguments"]:
                    merged[index]["function"]["arguments"] += tc["function"]["arguments"]
        
        # 对 arguments 进行 JSON 解析
        for item in merged.values():
            if "function" in item and "arguments" in item["function"]:
                item["function"]["arguments"] = safe_json_parse(item["function"]["arguments"])
        
        return sorted(merged.values(), key=lambda x: x["index"])

class OpenAIAdapter(StreamAdapter):
    """OpenAI 格式适配器"""
    
    def can_handle(self, first_chunk: str) -> bool:
        try:
            data = json.loads(first_chunk)
            return "choices" in data or "model" in data
        except:
            return False
    
    def parse_chunk(self, line: str) -> Optional[StreamChunk]:
        if not line or line.strip() == "[DONE]":
            return None

        try:
            data = json.loads(line)
            chunk = StreamChunk()

            # usage 可能出现在最终不含 choices 的块中 (stream_options.include_usage)
            if "usage" in data:
                chunk.usage = data["usage"]

            if "choices" in data and len(data["choices"]) > 0:
                choice = data["choices"][0]
                chunk.finish_reason = choice.get("finish_reason")

                delta = choice.get("delta", {})
                chunk.content = delta.get("content", "")

                # 兼容不同厂商的 reasoning 字段名和位置
                # - OpenAI: delta.reasoning_content
                # - DeepSeek: delta.reasoning_content 或 choice.reasoning_content
                # - Sensenova: delta.reasoning 或 choice.reasoning
                reasoning = (
                    delta.get("reasoning_content")
                    or delta.get("reasoning")
                    or choice.get("reasoning_content")
                    or choice.get("reasoning")
                )
                if reasoning:
                    chunk.reasoning_content = reasoning

                if "tool_calls" in delta:
                    chunk.tool_calls = delta["tool_calls"]

            return chunk
        except:
            return None

class AnthropicAdapter(StreamAdapter):
    """Anthropic 格式适配器"""
    
    def can_handle(self, first_chunk: str) -> bool:
        try:
            data = json.loads(first_chunk)
            return "type" in data and data["type"] in ["message_start", "content_block_start", "ping"]
        except:
            return False
    
    def parse_chunk(self, line: str) -> Optional[StreamChunk]:
        if not line:
            return None
        
        try:
            data = json.loads(line)
            chunk = StreamChunk()
            event_type = data.get("type", "")
            
            if event_type == "content_block_start":
                content_block = data.get("content_block", {})
                block_type = content_block.get("type", "")
                
                # 解析 tool_use 开始
                if block_type == "tool_use":
                    chunk.tool_calls = [{
                        "index": data.get("index", 0),
                        "id": content_block.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": content_block.get("name", ""),
                            "arguments": ""
                        }
                    }]
            
            elif event_type == "content_block_delta":
                delta = data.get("delta", {})
                delta_type = delta.get("type", "")
                
                if delta_type == "text_delta":
                    chunk.content = delta.get("text", "")
                elif delta_type == "thinking_delta":
                    chunk.reasoning_content = delta.get("thinking", "")
                # 解析 tool_use 的参数增量
                elif delta_type == "input_json_delta":
                    partial_json = delta.get("partial_json", "")
                    chunk.tool_calls = [{
                        "index": data.get("index", 0),
                        "function": {
                            "arguments": partial_json
                        }
                    }]
            
            elif event_type == "message_delta":
                delta = data.get("delta", {})
                chunk.finish_reason = delta.get("stop_reason")
                
                if "usage" in data:
                    chunk.usage = data.get("usage")
            
            return chunk
        except:
            return None

class GenericAdapter(StreamAdapter):
    """通用适配器 - 用于未知格式"""
    
    def can_handle(self, first_chunk: str) -> bool:
        return True
    
    def parse_chunk(self, line: str) -> Optional[StreamChunk]:
        if not line:
            return None
        
        chunk = StreamChunk()
        try:
            data = json.loads(line)
            chunk.content = data.get("content", data.get("text", data.get("delta", "")))
            chunk.reasoning_content = data.get("reasoning_content", data.get("reasoning", ""))
            chunk.tool_calls = data.get("tool_calls", [])
            chunk.finish_reason = data.get("finish_reason")
            chunk.usage = data.get("usage")
        except:
            chunk.content = line
        
        return chunk

class AdapterRegistry:
    """适配器注册表"""
    
    _adapters: List[StreamAdapter] = [
        OpenAIAdapter(),
        AnthropicAdapter(),
        GenericAdapter(),
    ]
    
    @classmethod
    def get_adapter(cls, first_chunk: str) -> StreamAdapter:
        """获取合适的适配器"""
        for adapter in cls._adapters:
            if adapter.can_handle(first_chunk):
                return adapter
        return cls._adapters[-1]

class StreamingLogPipeline:
    """流式响应日志管道"""
    
    def __init__(self, path: str):
        self.path = path
        self.adapter: Optional[StreamAdapter] = None
        self.chunks: List[StreamChunk] = []
        self.start_time = time.time()
        self.first_token_time: Optional[float] = None
        self.is_initialized = False
        self.event_type = "message"
    
    def process_line(self, line: str):
        """处理 SSE 数据行"""
        line = line.rstrip('\n')
        
        if not self.is_initialized and line.startswith("data: "):
            first_data = line[6:]
            if first_data and first_data != "[DONE]":
                self.adapter = AdapterRegistry.get_adapter(first_data)
                self.is_initialized = True
        
        if line.startswith("event: "):
            self.event_type = line[7:]
        elif line.startswith("data: "):
            data = line[6:]
            if data and data != "[DONE]":
                if self.first_token_time is None:
                    self.first_token_time = time.time()
                
                if self.adapter:
                    chunk = self.adapter.parse_chunk(data)
                    if chunk:
                        self.chunks.append(chunk)
        elif line.startswith(":"):
            pass
        elif line == "":
            self.event_type = "message"
    
    def finalize(self) -> Dict[str, Any]:
        """完成处理并生成统一格式的日志"""
        completion_time = time.time()
        elapsed = completion_time - self.start_time
        ttft = self.first_token_time - self.start_time if self.first_token_time else None
        
        if self.adapter and self.chunks:
            aggregated_body = self.adapter.aggregate(self.chunks)
        else:
            aggregated_body = {
                "content": "",
                "reasoning_content": "",
                "tool_calls": [],
                "finish_reason": None,
                "usage": None
            }
        
        response_body = {
            "content": aggregated_body.get("content", ""),
            "reasoning_content": aggregated_body.get("reasoning_content", ""),
            "tool_calls": aggregated_body.get("tool_calls", []),
            "finish_reason": aggregated_body.get("finish_reason"),
            "usage": aggregated_body.get("usage"),
            "_meta": {
                "total_chunks": len(self.chunks),
                "first_token_seconds": round(ttft, 3) if ttft else None,
                "total_seconds": round(elapsed, 3),
                "content_length": len(aggregated_body.get("content", "")),
            }
        }
        
        return response_body

# ==================== 请求处理 ====================

async def handle_request(request: web.Request) -> web.StreamResponse:
    """处理所有请求 - 透明转发"""
    start_time = time.time()
    method = request.method
    original_path = request.path
    query_string = request.rel_url.query_string
    
    # 解析路径前缀并构建上游 URL
    prefix, remaining_path = extract_path_prefix(original_path)
    upstream_url = build_upstream_url(prefix, remaining_path, query_string)
    
    if not upstream_url:
        error_msg = f"未知的前缀: {prefix}，支持的: {list(API_MAPPING.keys())}"
        if logger:
            logger.warning(error_msg)
        return web.Response(
            status=404,
            content_type="application/json",
            text=json.dumps({"error": error_msg}, ensure_ascii=False)
        )
    
    # 读取请求体
    try:
        body = await request.read()
    except Exception:
        body = b""
    
    # 预解析请求体用于日志
    request_body_log = safe_json_parse(body.decode("utf-8", errors="replace")) if body else ""
    
    # 复制请求头
    headers = {k: v for k, v in request.headers.items()}
    headers.pop("Host", None)
    if body and "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"
    
    timeout = ClientTimeout(total=REQUEST_TIMEOUT)
    
    try:
        async with ClientSession(timeout=timeout) as session:
            async with session.request(
                method, upstream_url, headers=headers, data=body
            ) as upstream_resp:
                
                # 检查是否是流式响应（通过 headers 或 path 判断）
                content_type = upstream_resp.headers.get('Content-Type', '').lower()
                is_streaming = (
                    'text/event-stream' in content_type or 
                    'stream' in content_type
                )
                
                if is_streaming:
                    # 流式响应处理
                    resp_headers = {}
                    for k, v in upstream_resp.headers.items():
                        key_lower = k.lower()
                        if key_lower not in ("transfer-encoding", "connection", "keep-alive", "content-encoding"):
                            resp_headers[k] = v
                    
                    resp = web.StreamResponse(
                        status=upstream_resp.status,
                        headers=resp_headers,
                    )
                    
                    # 创建日志管道用于聚合流式数据（在 try 块外初始化以避免作用域问题）
                    log_pipeline = StreamingLogPipeline(original_path)
                    
                    try:
                        await resp.prepare(request)
                        
                        # 缓冲区收集原始数据用于转发
                        raw_buffer = bytearray()
                        
                        async for chunk, _ in upstream_resp.content.iter_chunks():
                            raw_buffer.extend(chunk)
                            
                            # 解析 chunk 中的 SSE 事件行
                            chunk_text = chunk.decode('utf-8', errors='replace')
                            for line in chunk_text.split('\n'):
                                log_pipeline.process_line(line)
                            
                            try:
                                await resp.write(chunk)
                            except (ConnectionResetError, BrokenPipeError, ConnectionError) as write_err:
                                # 客户端连接已关闭，停止写入但继续读取上游数据用于日志
                                if logger:
                                    logger.warning(f"客户端连接中断: {write_err}")
                                break
                        
                        try:
                            await resp.write_eof()
                        except (ConnectionResetError, BrokenPipeError, ConnectionError):
                            # 忽略关闭时的连接错误
                            pass
                        
                        elapsed = time.time() - start_time
                        
                        # 生成聚合后的结构化日志
                        aggregated_log = log_pipeline.finalize()
                        
                        # 记录完整日志（流式响应 - 聚合版本）
                        log_entry = {
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "request": {
                                "method": method,
                                "path": original_path,
                                "upstream_url": upstream_url,
                                "headers": dict(headers),
                                "body": safe_json_parse(body.decode("utf-8", errors="replace")) if body else ""
                            },
                            "response": {
                                "status_code": upstream_resp.status,
                                "elapsed_seconds": round(elapsed, 3),
                                "headers": {k: v for k, v in upstream_resp.headers.items() 
                                           if k.lower() not in ("transfer-encoding", "connection", "keep-alive")},
                                "body": aggregated_log,
                                "is_streaming": True
                            }
                        }
                        
                        if logger:
                            logger.info(json.dumps(log_entry, ensure_ascii=False))
                        
                        return resp
                    
                    except (ConnectionResetError, BrokenPipeError, ConnectionError) as e:
                        # 准备响应时就失败（连接已关闭）
                        elapsed = time.time() - start_time
                        
                        # 即使连接失败，也要生成已有的聚合日志
                        aggregated_log = log_pipeline.finalize() if log_pipeline else None
                        
                        if logger:
                            logger.warning(f"流式响应连接失败: {e}")
                        
                        error_log = {
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "request": {
                                "method": method,
                                "path": original_path,
                                "upstream_url": upstream_url,
                                "headers": dict(headers),
                                "body": safe_json_parse(body.decode("utf-8", errors="replace")) if body else ""
                            },
                            "response": {
                                "status_code": upstream_resp.status,
                                "elapsed_seconds": round(elapsed, 3),
                                "error": f"Client connection closed: {str(e)}",
                                "body": aggregated_log,
                                "is_streaming": True
                            }
                        }
                        if logger:
                            logger.warning(json.dumps(error_log, ensure_ascii=False))
                        
                        # 即使连接失败，也要返回一个响应对象
                        raise web.HTTPBadRequest(text="Client disconnected")

                else:
                    # 非流式响应处理
                    resp_body = await upstream_resp.read()
                    
                    # 构建响应头（移除 hop-by-hop 头部）
                    resp_headers = {}
                    for k, v in upstream_resp.headers.items():
                        key_lower = k.lower()
                        if key_lower not in ("transfer-encoding", "connection", "keep-alive", "content-encoding"):
                            resp_headers[k] = v
                    
                    resp_headers["Content-Length"] = str(len(resp_body))
                    if "content-type" not in resp_headers:
                        resp_headers["Content-Type"] = "application/json"
                    
                    # 创建响应
                    resp = web.Response(
                        body=resp_body,
                        status=upstream_resp.status,
                        headers=resp_headers,
                    )
                    
                    elapsed = time.time() - start_time
                    
                    # 记录完整日志（非流式响应）
                    log_entry = {
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "request": {
                            "method": method,
                            "path": original_path,
                            "upstream_url": upstream_url,
                            "headers": dict(headers),
                            "body": safe_json_parse(body.decode("utf-8", errors="replace")) if body else ""
                        },
                        "response": {
                            "status_code": upstream_resp.status,
                            "elapsed_seconds": round(elapsed, 3),
                            "headers": dict(upstream_resp.headers),
                            "body": safe_json_parse(resp_body.decode("utf-8", errors="replace")) if resp_body else "",
                            "is_streaming": False
                        }
                    }
                    
                    if logger:
                        logger.info(json.dumps(log_entry, ensure_ascii=False))
                    
                    return resp
    
    except ClientError as e:
        elapsed = time.time() - start_time
        if logger:
            logger.error(f"上游请求失败: {e}")
        
        error_response = {"error": {"message": f"Bad Gateway: {str(e)}", "type": "upstream_error"}}
        
        # 记录错误日志
        error_log = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "request": {
                "method": method,
                "path": original_path,
                "upstream_url": upstream_url,
                "headers": dict(headers),
                "body": safe_json_parse(body.decode("utf-8", errors="replace")) if body else ""
            },
            "response": {
                "status_code": 502,
                "elapsed_seconds": round(elapsed, 3),
                "error": str(e)
            }
        }
        if logger:
            logger.error(json.dumps(error_log, ensure_ascii=False))
        
        return web.Response(
            status=502,
            content_type="application/json",
            text=json.dumps(error_response, ensure_ascii=False)
        )
    
    except Exception as e:
        elapsed = time.time() - start_time
        if logger:
            logger.exception("代理内部错误")
        
        error_response = {"error": {"message": "Internal Proxy Error", "type": "proxy_error"}}
        
        # 记录错误日志
        error_log = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "request": {
                "method": method,
                "path": original_path,
                "upstream_url": upstream_url,
                "headers": dict(headers),
                "body": safe_json_parse(body.decode("utf-8", errors="replace")) if body else ""
            },
            "response": {
                "status_code": 500,
                "elapsed_seconds": round(elapsed, 3),
                "error": str(e)
            }
        }
        if logger:
            logger.error(json.dumps(error_log, ensure_ascii=False))
        
        return web.Response(
            status=500,
            content_type="application/json",
            text=json.dumps(error_response, ensure_ascii=False)
        )


# ==================== 主函数 ====================

async def main():
    global logger
    
    parser = argparse.ArgumentParser(description="通用大模型 API 转发代理")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"监听端口 (默认 {DEFAULT_PORT})")
    parser.add_argument("--log-file", type=str, default=LOG_FILE, help=f"日志文件路径 (默认 {LOG_FILE})")
    args = parser.parse_args()
    
    logger = setup_logger(args.log_file)
    
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", handle_request)
    
    if logger:
        logger.info(f"代理启动，监听 0.0.0.0:{args.port}")
        logger.info(f"支持的 API 前缀: {list(API_MAPPING.keys())}")
        logger.info(f"日志文件: {args.log_file}")
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", args.port)
    await site.start()
    
    # 保持运行
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
