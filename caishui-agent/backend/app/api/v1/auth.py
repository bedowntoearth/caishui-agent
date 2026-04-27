"""管理端认证API"""
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_password, create_access_token, create_refresh_token, decode_token
from app.core.config import settings
from app.core.redis import get_redis
from app.models import SysUser, LoginLog, UserStatus
from app.schemas import LoginRequest, LoginResponse, RefreshTokenRequest, CaptchaResponse
from app.utils.captcha import create_captcha, verify_captcha
from app.utils.dependencies import get_current_admin, TOKEN_BLACKLIST_PREFIX
from app.core.logger import logger
import redis.asyncio as aioredis
from datetime import datetime

router = APIRouter(prefix="/auth", tags=["管理端认证"])

LOGIN_FAIL_PREFIX = "login_fail:"
LOGIN_FAIL_MAX = 5
LOGIN_FAIL_EXPIRE = 900  # 15分钟锁定


@router.get("/captcha", response_model=CaptchaResponse)
async def get_captcha():
    """获取图形验证码"""
    return await create_captcha()


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    body: LoginRequest,
    db: Session = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """管理端登录"""
    # 验证码校验
    if not await verify_captcha(body.captcha_key, body.captcha_code):
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    ip = request.client.host if request.client else "unknown"

    # 防暴力破解：检查失败次数
    fail_key = f"{LOGIN_FAIL_PREFIX}{ip}:{body.username}"
    fail_count = await redis.get(fail_key)
    if fail_count and int(fail_count) >= LOGIN_FAIL_MAX:
        raise HTTPException(status_code=429, detail="登录失败次数过多，请15分钟后重试")

    user = db.query(SysUser).filter(SysUser.username == body.username).first()

    def record_fail(reason: str):
        log = LoginLog(
            user_id=user.id if user else 0,
            ip_address=ip,
            login_result="fail",
            fail_reason=reason,
        )
        if user:
            db.add(log)
            db.commit()

    if not user or not verify_password(body.password, user.password_hash):
        import asyncio
        asyncio.create_task(redis.incr(fail_key))
        asyncio.create_task(redis.expire(fail_key, LOGIN_FAIL_EXPIRE))
        if user:
            record_fail("密码错误")
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if user.status == UserStatus.inactive:
        raise HTTPException(status_code=403, detail="账号已被禁用，请联系管理员")

    # 清除失败计数
    await redis.delete(fail_key)

    # 生成Token
    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    # 更新最后登录信息
    user.last_login_ip = ip
    user.last_login_at = datetime.utcnow()
    log = LoginLog(user_id=user.id, ip_address=ip, login_result="success")
    db.add(log)
    db.commit()

    logger.info(f"用户 {user.username} 登录成功，IP: {ip}")

    # 创建响应，包含设置 Cookie
    resp = Response(
        content=LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user_info={
                "id": user.id,
                "username": user.username,
                "real_name": user.real_name,
                "role": user.role,
            },
        ).model_dump_json(),
        media_type="application/json",
    )
    
    # 设置 HTTP-only Cookie（服务端session）
    resp.set_cookie(
        key="admin_token",
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=False,  # 开发环境设为 False，生产环境应设为 True
    )
    
    return resp


@router.post("/refresh")
async def refresh_token(
    body: RefreshTokenRequest,
    db: Session = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """刷新Access Token"""
    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Refresh Token无效或已过期")

    user_id = payload.get("sub")
    user = db.query(SysUser).filter(SysUser.id == int(user_id)).first()
    if not user or user.status == UserStatus.inactive:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")

    new_access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role},
    )
    return {"access_token": new_access_token, "token_type": "bearer"}


@router.post("/logout")
async def logout(
    current_user: SysUser = Depends(get_current_admin),
    redis: aioredis.Redis = Depends(get_redis),
    credentials=Depends(__import__("app.utils.dependencies", fromlist=["bearer_scheme"]).bearer_scheme),
):
    """安全退出，将Token加入黑名单"""
    token = credentials.credentials
    await redis.setex(
        f"{TOKEN_BLACKLIST_PREFIX}{token}",
        settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "1",
    )
    return {"message": "已安全退出"}


@router.get("/me")
async def get_me(current_user: SysUser = Depends(get_current_admin)):
    """获取当前登录用户信息"""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "real_name": current_user.real_name,
        "phone": current_user.phone,
        "role": current_user.role,
        "status": current_user.status,
        "last_login_at": current_user.last_login_at,
        "last_login_ip": current_user.last_login_ip,
    }
