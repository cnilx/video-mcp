"""API Key 认证中间件"""
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from loguru import logger

from src.utils.config import config


# HTTP Bearer 认证方案
security = HTTPBearer()


async def verify_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = None
) -> bool:
    """
    验证 API Key

    Args:
        credentials: HTTP 认证凭据

    Returns:
        验证是否通过

    Raises:
        HTTPException: 认证失败时抛出 401 错误
    """
    # 如果未配置 API Key，则跳过认证（仅用于开发环境）
    if not config.api_key:
        logger.warning("未配置 API_KEY，跳过认证检查")
        return True

    # 检查是否提供了认证凭据
    if credentials is None:
        logger.warning("请求未提供认证凭据")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 验证 API Key
    if credentials.credentials != config.api_key:
        logger.warning(f"API Key 验证失败: {credentials.credentials[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 API Key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return True


async def get_api_key_from_header(request: Request) -> Optional[str]:
    """
    从请求头中提取 API Key

    Args:
        request: FastAPI 请求对象

    Returns:
        API Key 或 None
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None

    # 解析 Bearer Token
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    return parts[1]


class AuthMiddleware:
    """认证中间件"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        """中间件调用"""
        if scope["type"] == "http":
            # 获取请求路径
            path = scope["path"]

            # 健康检查端点不需要认证
            if path == "/health":
                await self.app(scope, receive, send)
                return

            # 其他端点需要认证
            # 注意：实际的认证逻辑在路由处理函数中通过 Depends 实现
            # 这里的中间件主要用于日志记录和全局处理

        await self.app(scope, receive, send)
