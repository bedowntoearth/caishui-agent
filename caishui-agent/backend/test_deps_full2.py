"""测试 get_current_admin 依赖链的每个环节"""
import sys
sys.path.insert(0, 'e:/workspace/caishui-agent/backend')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import asyncio

# 直接导入需要的模块，避免触发 app.__init__ 的 FastAPI 初始化
from app.core.database import SessionLocal, get_db
from app.core.security import decode_token
from app.models import SysUser
import redis.asyncio as aioredis

# 单独实现 get_redis 和 token验证逻辑
from app.core.config import settings
import redis.asyncio as aioredis

async def get_redis_test():
    import redis.asyncio as aioredis
    from app.core.config import settings
    try:
        pool = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        return pool
    except Exception:
        return None

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwicm9sZSI6InN1cGVyX2FkbWluIiwiZXhwIjoxNzc3MDE4MDQ3LCJ0eXBlIjoiYWNjZXNzIn0.m6LoPGSnv64AFO_NmqIz1vJ5RidSXNz83eVabdGJv8Y"

async def get_current_admin_test(token: str, db, redis_conn):
    TOKEN_BLACKLIST_PREFIX = "token_blacklist:"
    credentials_exception = Exception("认证失败")

    # 检查Token黑名单
    if await redis_conn.exists(f"{TOKEN_BLACKLIST_PREFIX}{token}"):
        raise credentials_exception

    # 解码token
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    # 查用户
    user = db.query(SysUser).filter(SysUser.id == int(user_id)).first()
    if user is None:
        raise credentials_exception

    return user

print("=== Dependency chain test ===\n")

async def run():
    # 1. get_db
    print("[1] get_db (sync)...", end=" ", flush=True)
    db = next(get_db())
    print("OK, session=" + str(id(db)))

    # 2. get_redis
    print("[2] get_redis (async)...", end=" ", flush=True)
    redis_conn = await get_redis_test()
    pong = await redis_conn.ping()
    print("PING=" + str(pong))

    # 3. full chain
    print("[3] full get_current_admin chain...", end=" ", flush=True)
    try:
        user = await get_current_admin_test(TOKEN, db, redis_conn)
        print("OK, user=" + str(user.username))
    except Exception as e:
        print("ERROR: " + type(e).__name__ + ": " + str(e))
        import traceback; traceback.print_exc()

    # 4. test with FastAPI Depends pattern
    print("[4] FastAPI Depends pattern...", end=" ", flush=True)
    from fastapi import Depends
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

    # 模拟 Depends 调用
    async def simulated_depends(dep_fn, *args, **kwargs):
        sig = inspect.signature(dep_fn)
        # 如果需要 Depends(default)，则使用默认值
        for param_name, param in sig.parameters.items():
            if param.default is not None:
                if isinstance(param.default, Depends):
                    # 用 kwargs 中的值替换
                    if param_name in kwargs:
                        pass
        return await dep_fn(*args, **kwargs)

    # 手动执行 get_current_admin (as FastAPI would)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=TOKEN)
    try:
        # 直接 await 调用，不走 FastAPI 的 Depends 框架
        result = await get_current_admin_test(TOKEN, db, redis_conn)
        print("OK, user=" + str(result.username))
    except Exception as e:
        print("ERROR: " + type(e).__name__ + ": " + str(e))
        import traceback; traceback.print_exc()

    # 5. 通过 FastAPI app 的路由测试
    print("\n[5] Via FastAPI app (real /export endpoint)...", flush=True)

    # 直接导入 companies router 中的 export 函数
    from app.api.v1.companies import export_companies_api
    import inspect
    sig = inspect.signature(export_companies_api)
    print("    Signature: " + str(sig))

    # 尝试用 app 测试
    try:
        from app import app
        # 找到 /export 路由
        for route in app.routes:
            if hasattr(route, 'path') and route.path == '/export':
                print("    Found /export route: " + str(route))
    except Exception as e:
        print("    App import error: " + str(e))

    print("\n=== DONE ===")

asyncio.run(run())
