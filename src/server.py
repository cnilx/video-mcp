"""FastAPI HTTP 服务入口"""
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from src.mcp_app import mcp
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
        logger.info("API Key 认证已启用")
    else:
        logger.warning("API Key 认证未启用（开发模式）")

    if config.dashscope_api_key:
        logger.info("阿里百炼 API Key 已配置")
    else:
        logger.warning("阿里百炼 API Key 未配置")

    # 列出已注册的 MCP 工具
    tools = await mcp.list_tools()
    logger.info(f"已注册 MCP 工具: {[t.name for t in tools]}")
    logger.info("=" * 60)

    async with mcp.session_manager.run():
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


# Bearer Token 认证中间件：拦截 /mcp 路径
@app.middleware("http")
async def mcp_auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/mcp") and config.api_key:
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"error": "未提供认证凭据"})
        token = auth_header[7:]
        if token != config.api_key:
            return JSONResponse(status_code=401, content={"error": "无效的 API Key"})
    return await call_next(request)


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


# 挂载 MCP Streamable HTTP 到 /mcp 路径
app.mount("/mcp", mcp.streamable_http_app())


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
