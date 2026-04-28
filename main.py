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
from typing import Optional, Dict, Any
from aiohttp import web, ClientSession, ClientTimeout, ClientError

# ==================== 配置区域 ====================

# API 映射配置：路径前缀 -> 上游 base_url
API_MAPPING = {
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
    "deepseek": "https://api.deepseek.com",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
}

DEFAULT_PORT = 8080
LOG_FILE = "proxy_requests.log"
REQUEST_TIMEOUT = 300

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
                    'stream' in content_type or 
                    request.path.endswith('/chat/completions')  # 假设 chat 接口可能是流式的
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
                    await resp.prepare(request)
                    
                    # 缓冲区收集完整响应用于日志
                    full_response_buffer = bytearray()
                    
                    async for chunk, _ in upstream_resp.content.iter_chunks():
                        full_response_buffer.extend(chunk)
                        await resp.write(chunk)
                    
                    await resp.write_eof()
                    
                    elapsed = time.time() - start_time
                    
                    # 记录完整日志（流式响应）
                    log_entry = {
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "request": {
                            "method": method,
                            "path": original_path,
                            "upstream_url": upstream_url,
                            "headers": dict(headers),
                            "body": body.decode("utf-8", errors="replace") if body else ""
                        },
                        "response": {
                            "status_code": upstream_resp.status,
                            "elapsed_seconds": round(elapsed, 3),
                            "headers": dict(upstream_resp.headers),
                            "body": bytes(full_response_buffer).decode("utf-8", errors="replace"),
                            "is_streaming": True
                        }
                    }
                    
                    if logger:
                        logger.info(json.dumps(log_entry, ensure_ascii=False))
                    
                    return resp
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
                            "body": body.decode("utf-8", errors="replace") if body else ""
                        },
                        "response": {
                            "status_code": upstream_resp.status,
                            "elapsed_seconds": round(elapsed, 3),
                            "headers": dict(upstream_resp.headers),
                            "body": resp_body.decode("utf-8", errors="replace") if resp_body else "",
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
                "body": body.decode("utf-8", errors="replace") if body else ""
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
                "body": body.decode("utf-8", errors="replace") if body else ""
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
