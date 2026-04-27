"""系统用户管理API（管理端）
包含：SysUser（运营人员）管理 + WxUser（小程序用户）管理
"""
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from app.core.database import get_db
from app.core.security import get_password_hash
from app.models import SysUser, UserStatus, WxUser, Company
from app.schemas import SysUserCreate, SysUserUpdate, SysUserOut
from app.utils.dependencies import get_current_admin, get_current_super_admin
from app.utils.xlsx_utils import export_sys_users, parse_import_file
from datetime import datetime

router = APIRouter(prefix="/users", tags=["用户管理"])


# ===== 小程序用户（管理端查看/管理） =====

@router.get("/", summary="小程序用户列表")
async def list_wx_users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", description="手机号/昵称搜索"),
    has_company: Optional[str] = Query("", description="绑定状态：bound=已绑定，unbound=未绑定，空=全部"),
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    query = db.query(WxUser)
    if keyword:
        query = query.filter(
            (WxUser.phone.ilike(f"%{keyword}%"))
        )
    if has_company == "bound":
        query = query.filter(WxUser.company_id.isnot(None))
    elif has_company == "unbound":
        query = query.filter(WxUser.company_id.is_(None))

    total = query.count()
    # 统计已绑定/未绑定总数（不受 has_company 过滤影响，使用全量统计）
    total_bound = db.query(WxUser).filter(WxUser.company_id.isnot(None)).count()
    total_unbound = db.query(WxUser).filter(WxUser.company_id.is_(None)).count()
    total_all = db.query(WxUser).count()

    items = query.order_by(desc(WxUser.created_at)).offset((page - 1) * size).limit(size).all()

    result = []
    for u in items:
        company = db.query(Company).filter(Company.id == u.company_id).first() if u.company_id else None
        result.append({
            "id": u.id,
            "phone": u.phone,
            "nickname": u.phone,  # WxUser 暂用手机号作昵称
            "avatar_url": None,
            "openid": u.openid[:8] + "****" if u.openid else None,  # 脱敏
            "company_id": u.company_id,
            "company_name": company.name if company else None,
            "role": "user",
            "is_active": True,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        })

    return {"code": 200, "data": {
        "total": total,
        "total_all": total_all,
        "total_bound": total_bound,
        "total_unbound": total_unbound,
        "items": result
    }, "message": "ok"}


@router.put("/{user_id}", summary="修改小程序用户（绑定企业/状态）")
async def update_wx_user(
    user_id: int,
    body: dict,
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    user = db.query(WxUser).filter(WxUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if "company_id" in body:
        user.company_id = body["company_id"] or None
    if "phone" in body and body["phone"]:
        user.phone = body["phone"]

    db.commit()
    return {"code": 200, "data": None, "message": "更新成功"}


@router.delete("/{user_id}", summary="删除小程序用户")
async def delete_wx_user(
    user_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_super_admin),
):
    user = db.query(WxUser).filter(WxUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    db.delete(user)
    db.commit()
    return {"code": 200, "data": None, "message": "删除成功"}


# ===== 系统运营人员（SysUser）管理 =====

@router.get("/sys/list", summary="运营人员列表")
async def list_sys_users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    keyword: str = Query(""),
    role: str = Query(""),
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    query = db.query(SysUser)
    if keyword:
        query = query.filter(
            (SysUser.real_name.ilike(f"%{keyword}%")) |
            (SysUser.phone.ilike(f"%{keyword}%")) |
            (SysUser.username.ilike(f"%{keyword}%"))
        )
    if role:
        query = query.filter(SysUser.role == role)

    total = query.count()
    items = query.order_by(desc(SysUser.created_at)).offset((page - 1) * size).limit(size).all()
    return {
        "code": 200,
        "data": {
            "total": total,
            "items": [SysUserOut.model_validate(u) for u in items],
        },
        "message": "ok",
    }


@router.post("/sys", summary="新增运营人员")
async def create_sys_user(
    body: SysUserCreate,
    db: Session = Depends(get_db),
    _=Depends(get_current_super_admin),
):
    if db.query(SysUser).filter(SysUser.username == body.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    if db.query(SysUser).filter(SysUser.phone == body.phone).first():
        raise HTTPException(status_code=400, detail="手机号已存在")
    user = SysUser(
        username=body.username,
        password_hash=get_password_hash(body.password),
        real_name=body.real_name,
        phone=body.phone,
        role=body.role,
        remark=body.remark,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"code": 200, "data": {"id": user.id}, "message": "新增成功"}


@router.put("/sys/{user_id}", summary="修改运营人员")
async def update_sys_user(
    user_id: int,
    body: SysUserUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_super_admin),
):
    user = db.query(SysUser).filter(SysUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    db.commit()
    return {"code": 200, "data": None, "message": "更新成功"}


@router.delete("/sys/{user_id}", summary="删除运营人员")
async def delete_sys_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_super_admin),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")
    user = db.query(SysUser).filter(SysUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    db.delete(user)
    db.commit()
    return {"code": 200, "data": None, "message": "删除成功"}


@router.get("/sys/template", summary="系统用户导入模板下载")
async def download_user_template(
    _: SysUser = Depends(get_current_admin),
):
    wb = Workbook()
    ws = wb.active
    ws.title = "系统用户"
    ws.append(["用户名*","真实姓名*","手机号*","初始密码","角色","备注"])
    ws.append(["admin2","王五","13900139000","Caishui@2025","运营人员","财务人员账号"])
    ws.column_dimensions['A'].width = 16
    ws.column_dimensions['B'].width = 14
    ws.column_dimensions['C'].width = 14
    ws.column_dimensions['D'].width = 16
    ws.column_dimensions['E'].width = 14
    ws.column_dimensions['F'].width = 22
    buf = BytesIO()
    wb.save(buf)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''sys_user_import_template.xlsx"},
    )


@router.get("/sys/export", summary="导出系统用户")
async def export_sys_users_api(
    keyword: str = Query(""),
    role: str = Query(""),
    db: Session = Depends(get_db),
    _: SysUser = Depends(get_current_admin),
):
    query = db.query(SysUser)
    if keyword:
        query = query.filter(
            (SysUser.real_name.ilike(f"%{keyword}%")) |
            (SysUser.phone.ilike(f"%{keyword}%")) |
            (SysUser.username.ilike(f"%{keyword}%"))
        )
    if role:
        query = query.filter(SysUser.role == role)

    users = query.order_by(desc(SysUser.created_at)).all()
    rows = [{
        "id": u.id,
        "username": u.username,
        "real_name": u.real_name,
        "phone": u.phone,
        "role": u.role,
        "status": u.status,
        "remark": u.remark or "",
        "last_login_ip": u.last_login_ip or "",
        "last_login_at": u.last_login_at,
        "created_at": u.created_at,
    } for u in users]

    excel_bytes = export_sys_users(rows)
    filename = f"sys_users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        iter([excel_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.post("/sys/import", summary="批量导入系统用户")
async def import_sys_users(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_super_admin),
):
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xls 文件")

    content = await file.read()
    raw_rows = parse_import_file(content)

    ROLE_MAP  = {"超级管理员": "super_admin", "管理员": "admin", "运营人员": "operator", "财税分析师": "analyst"}
    STATUS_MAP = {"启用": "active", "禁用": "inactive"}

    created, skipped, errors = 0, 0, []
    for i, row in enumerate(raw_rows, 2):
        try:
            username  = str(row.get("用户名") or "").strip()
            real_name = str(row.get("真实姓名") or "").strip()
            phone     = str(row.get("手机号") or "").strip()
            password  = str(row.get("初始密码") or "Caishui@2025").strip()
            role_raw  = str(row.get("角色") or "运营人员").strip()
            role      = ROLE_MAP.get(role_raw, "operator")
            remark    = str(row.get("备注") or "").strip() or None

            if not username or not real_name or not phone:
                skipped += 1
                errors.append(f"第{i}行：用户名、真实姓名、手机号不能为空")
                continue

            if db.query(SysUser).filter(SysUser.username == username).first():
                skipped += 1
                errors.append(f"第{i}行：用户名 {username} 已存在，跳过")
                continue

            if db.query(SysUser).filter(SysUser.phone == phone).first():
                skipped += 1
                errors.append(f"第{i}行：手机号 {phone} 已存在，跳过")
                continue

            user = SysUser(
                username=username,
                password_hash=get_password_hash(password),
                real_name=real_name,
                phone=phone,
                role=role,
                remark=remark,
                created_by=current_user.id,
            )
            db.add(user)
            created += 1
        except Exception as e:
            skipped += 1
            errors.append(f"第{i}行：{str(e)}")

    db.commit()
    return {
        "code": 200,
        "data": {"created": created, "skipped": skipped, "errors": errors[:20]},
        "message": f"导入完成：成功 {created} 条，跳过 {skipped} 条",
    }
