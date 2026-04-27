"""JWT鉴权依赖注入"""
import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.security import decode_token
from app.core.database import get_db
from app.models import SysUser, UserStatus
from app.core.redis import get_redis

bearer_scheme = HTTPBearer()
wx_bearer_scheme = HTTPBearer()

TOKEN_BLACKLIST_PREFIX = "token_blacklist:"


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> SysUser:
    """获取当前登录的管理端用户"""
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="认证失败，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # 检查Token黑名单
    if await redis.exists(f"{TOKEN_BLACKLIST_PREFIX}{token}"):
        raise credentials_exception

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    user = db.query(SysUser).filter(SysUser.id == int(user_id)).first()
    if user is None or user.status == UserStatus.inactive:
        raise credentials_exception
    return user


async def get_current_super_admin(
    current_user: SysUser = Depends(get_current_admin),
) -> SysUser:
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足，需要超级管理员权限",
        )
    return current_user


async def get_current_wx_user_company_id(
    credentials: HTTPAuthorizationCredentials = Depends(wx_bearer_scheme),
    redis: aioredis.Redis = Depends(get_redis),
) -> int:
    """获取当前小程序用户关联的企业ID"""
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="请先完成微信授权登录",
    )
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise credentials_exception

    company_id = payload.get("company_id")
    if not company_id:
        raise credentials_exception
    return int(company_id)


async def get_admin_page_auth(request: Request) -> SysUser:
    """管理端页面认证：从 Cookie 中验证 token（用于保护 HTML 页面路由）"""
    from app.core.database import get_db
    from app.core.redis import get_redis
    import redis.asyncio as aioredis
    
    credentials_exception = HTTPException(
        status_code=302,  # 重定向到登录页
        headers={"Location": "/admin/login"},
    )
    
    # 从 Cookie 获取 token
    token = request.cookies.get("admin_token")
    if not token:
        raise credentials_exception
    
    # 获取数据库会话和 Redis 连接
    db_gen = get_db()
    db = next(db_gen)
    try:
        redis_conn = await get_redis()
        
        # 检查 Token 黑名单
        if await redis_conn.exists(f"{TOKEN_BLACKLIST_PREFIX}{token}"):
            raise credentials_exception
        
        payload = decode_token(token)
        if payload is None or payload.get("type") != "access":
            raise credentials_exception
        
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        
        user = db.query(SysUser).filter(SysUser.id == int(user_id)).first()
        if user is None or user.status == UserStatus.inactive:
            raise credentials_exception
        
        return user
    finally:
        db.close()
