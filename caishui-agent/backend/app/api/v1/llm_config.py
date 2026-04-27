"""大模型（LLM）配置管理 API"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.models import SysUser
from app.utils.dependencies import get_current_admin, get_current_super_admin
from app.core.config import settings
import os

router = APIRouter(prefix="/llm-config", tags=["大模型配置"])

ENV_FILE = ".env"  # 与 config.py 读取同一个 .env


class LLMConfigOut(BaseModel):
    ai_api_key: str
    ai_api_base: str
    ai_model: str
    ai_max_tokens: int
    ai_temperature: float


class LLMConfigIn(BaseModel):
    ai_api_key: str
    ai_api_base: str
    ai_model: str
    ai_max_tokens: int
    ai_temperature: float


def _read_env() -> dict:
    """读取 .env 文件为 dict，注释行和空行保持原样"""
    lines = []
    data = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines:
            stripped = line.strip()
            if "=" in stripped and not stripped.startswith("#"):
                key, _, val = stripped.partition("=")
                data[key.strip()] = val.strip()
    return lines, data


def _write_env(lines: list, updates: dict):
    """写回 .env，保留注释，新增/覆盖配置项"""
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        for line in lines:
            stripped = line.strip()
            if "=" in stripped and not stripped.startswith("#"):
                key = stripped.partition("=")[0].strip()
                if key in updates:
                    f.write(f"{key}={updates[key]}\n")
                    del updates[key]
                    continue
            f.write(line)
        # 写入新增的key（按固定顺序）
        order = ["AI_API_KEY", "AI_API_BASE", "AI_MODEL", "AI_MAX_TOKENS", "AI_TEMPERATURE"]
        for key in order:
            if key in updates:
                f.write(f"{key}={updates[key]}\n")


def _get_current_settings() -> dict:
    """获取当前生效的配置（从 Settings 实例读取）"""
    return {
        "ai_api_key": settings.AI_API_KEY,
        "ai_api_base": settings.AI_API_BASE,
        "ai_model": settings.AI_MODEL,
        "ai_max_tokens": settings.AI_MAX_TOKENS,
        "ai_temperature": settings.AI_TEMPERATURE,
    }


@router.get("", response_model=LLMConfigOut)
async def get_llm_config(
    current_user: SysUser = Depends(get_current_admin),
):
    """获取当前大模型配置（所有登录管理员可查看）"""
    return LLMConfigOut(**_get_current_settings())


@router.put("", response_model=LLMConfigOut)
async def update_llm_config(
    body: LLMConfigIn,
    current_user: SysUser = Depends(get_current_super_admin),
):
    """更新大模型配置（仅超级管理员可操作）"""
    lines, data = _read_env()
    new_values = {
        "AI_API_KEY": body.ai_api_key,
        "AI_API_BASE": body.ai_api_base,
        "AI_MODEL": body.ai_model,
        "AI_MAX_TOKENS": str(body.ai_max_tokens),
        "AI_TEMPERATURE": str(body.ai_temperature),
    }
    _write_env(lines, new_values)

    # 注意：运行时 settings 是进程启动时加载的，修改 .env 后需重启服务才生效
    return LLMConfigOut(**_get_current_settings())
