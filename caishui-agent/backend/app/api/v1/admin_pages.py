"""管理端前端路由（Jinja2模板 + 独立页面）"""
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.utils.dependencies import get_admin_page_auth
from app.models import SysUser
import os

router = APIRouter(prefix="/admin", tags=["管理端页面"])
templates = Jinja2Templates(directory="templates", auto_reload=True)


@router.get("/", response_class=HTMLResponse)
async def admin_index(request: Request, _: SysUser = Depends(get_admin_page_auth)):
    """默认跳转至 dashboard"""
    return templates.TemplateResponse("admin/dashboard.html", {"request": request})


@router.get("/login", response_class=HTMLResponse)
async def admin_login(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request})


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request, _: SysUser = Depends(get_admin_page_auth)):
    """数据总览 - 使用独立页面"""
    return templates.TemplateResponse("admin/dashboard.html", {"request": request})


@router.get("/companies", response_class=HTMLResponse)
async def admin_companies(request: Request, _: SysUser = Depends(get_admin_page_auth)):
    """企业信息管理 - 使用独立页面"""
    return templates.TemplateResponse("admin/companies.html", {"request": request})


@router.get("/companies/{company_id}", response_class=HTMLResponse)
async def admin_company_detail(request: Request, company_id: int, _: SysUser = Depends(get_admin_page_auth)):
    return templates.TemplateResponse(
        "admin/company_detail.html",
        {"request": request, "page": "companies", "company_id": company_id},
    )


@router.get("/users", response_class=HTMLResponse)
async def admin_users(request: Request, _: SysUser = Depends(get_admin_page_auth)):
    """系统用户管理 - 使用独立页面"""
    return templates.TemplateResponse("admin/users.html", {"request": request})


@router.get("/wx-users", response_class=HTMLResponse)
async def admin_wx_users(request: Request, _: SysUser = Depends(get_admin_page_auth)):
    """微信小程序用户管理 - 使用独立页面"""
    return templates.TemplateResponse("admin/wx_users.html", {"request": request})


@router.get("/risk-indicators", response_class=HTMLResponse)
async def admin_risk_indicators(request: Request, _: SysUser = Depends(get_admin_page_auth)):
    """风险指标管理 - 使用独立页面"""
    return templates.TemplateResponse("admin/risk_indicators.html", {"request": request})


@router.get("/llm-config", response_class=HTMLResponse)
async def admin_llm_config(request: Request, _: SysUser = Depends(get_admin_page_auth)):
    """大模型配置 - 保留 SPA 模式"""
    return templates.TemplateResponse("admin/layout.html", {"request": request})


@router.post("/logout")
async def admin_logout(response: Response):
    """退出登录，清除 Cookie"""
    response.delete_cookie(key="admin_token")
    return {"message": "已退出登录"}
