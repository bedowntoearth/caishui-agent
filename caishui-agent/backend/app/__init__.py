from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from app.core.config import settings
from app.core.database import Base, engine
from app.core.redis import get_redis, close_redis
from app.api.v1 import api_router
from app.api.v1.admin_pages import router as admin_page_router
from app.core.logger import logger
import app.models  # noqa: 确保所有模型被导入


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 启动中...")

    # 创建数据库表
    Base.metadata.create_all(bind=engine)
    logger.info("✅ 数据库表初始化完成")

    # 初始化Redis连接
    await get_redis()
    logger.info("✅ Redis连接成功")

    # 创建上传目录
    os.makedirs("uploads/financial", exist_ok=True)
    os.makedirs("logs", exist_ok=True)

    yield

    # 关闭时
    await close_redis()
    logger.info("👋 服务已关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="财税智能体系统 - 后端API",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS_LIST,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"未处理异常: {request.url} - {exc}")
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": "服务器内部错误，请稍后重试", "data": None},
    )


# 注册API路由
app.include_router(api_router, prefix="/api/v1")

# 注册管理端页面路由
app.include_router(admin_page_router)

# 静态文件（管理端前端资源）
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    """默认首页重定向到管理后台登录页"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/admin/login")


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.APP_NAME}
