"""FastAPI HTTP 服务入口"""
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from loguru import logger

from src.auth import security, verify_api_key
from src.utils.config import config


# 配置日志
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    logger.info("=" * 60)
    logger.info("视频分析 MCP 服务启动中...")
    logger.info(f"服务地址: http://{config.server_host}:{config.server_port}")
    logger.info(f"MCP 端点: http://{config.server_host}:{config.server_port}/mcp")
    logger.info(f"健康检查: http://{config.server_host}:{config.server_port}/health")
    logger.info(f"超时设置: {config.server_timeout} 秒")
    logger.info(f"工作目录: {config.workspace_base_dir}")

    if config.api_key:
        logger.info("✓ API Key 认证已启用")
    else:
        logger.warning("✗ API Key 认证未启用（开发模式）")

    if config.dashscope_api_key:
        logger.info("✓ 阿里百炼 API Key 已配置")
    else:
        logger.warning("✗ 阿里百炼 API Key 未配置")

    logger.info("=" * 60)

    yield

    # 关闭时执行
    logger.info("视频分析 MCP 服务正在关闭...")


# 创建 FastAPI 应用
app = FastAPI(
    title="视频分析 MCP 服务",
    description="基于 MCP 协议的视频分析服务，提供视频下载、音频转录、图像识别等功能",
    version="1.0.0",
    lifespan=lifespan
)


# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """
    健康检查端点

    Returns:
        服务状态信息
    """
    return {
        "status": "healthy",
        "service": "video-mcp",
        "version": "1.0.0",
        "config": {
            "api_key_enabled": bool(config.api_key),
            "dashscope_enabled": bool(config.dashscope_api_key),
            "workspace_dir": config.workspace_base_dir,
            "timeout": config.server_timeout
        }
    }


@app.post("/mcp")
async def mcp_endpoint(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    MCP 协议 HTTP 端点

    Args:
        request: FastAPI 请求对象
        credentials: HTTP 认证凭据

    Returns:
        MCP 协议响应
    """
    # 验证 API Key
    await verify_api_key(credentials)

    try:
        # 读取请求体
        body = await request.json()
        logger.info(f"收到 MCP 请求: {body.get('method', 'unknown')}")

        # TODO: 集成 MCP SDK 处理请求
        # 这里暂时返回一个占位响应
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": {
                    "message": "MCP SDK 集成待实现"
                }
            }
        )

    except Exception as e:
        logger.error(f"处理 MCP 请求失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"处理请求失败: {str(e)}"
        )


@app.get("/mcp/sse")
async def mcp_sse_endpoint(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    MCP 协议 SSE 端点（可选）

    Args:
        request: FastAPI 请求对象
        credentials: HTTP 认证凭据

    Returns:
        SSE 流响应
    """
    # 验证 API Key
    await verify_api_key(credentials)

    # TODO: 实现 SSE 支持
    return JSONResponse(
        content={"message": "SSE 端点待实现"},
        status_code=status.HTTP_501_NOT_IMPLEMENTED
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP 异常处理器"""
    logger.warning(f"HTTP 异常: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.status_code,
                "message": exc.detail
            }
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """通用异常处理器"""
    logger.error(f"未处理的异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": 500,
                "message": "服务器内部错误",
                "detail": str(exc)
            }
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.server:app",
        host=config.server_host,
        port=config.server_port,
        reload=True,
        timeout_keep_alive=config.server_timeout
    )
