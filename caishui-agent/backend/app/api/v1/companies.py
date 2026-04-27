"""企业信息管理API"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from app.core.database import get_db
from app.models import Company, SysUser, FinancialData, FinancialDataType, RiskIndicator, WxUser
from app.schemas import CompanyCreate, CompanyUpdate, CompanyOut
from app.utils.dependencies import get_current_admin, get_current_super_admin
from app.data_pipeline.etl import process_financial_file
from app.services.ai_service import generate_risk_report
from app.utils.xlsx_utils import export_companies, parse_import_file
from io import BytesIO
from openpyxl import Workbook
import aiofiles
import os
import uuid

router = APIRouter(prefix="/companies", tags=["企业信息管理"])

UPLOAD_DIR = "uploads/financial"


# ===== 仪表板统计 =====

@router.get("/dashboard/stats", summary="仪表板统计数据", tags=["仪表板"])
async def dashboard_stats(
    db: Session = Depends(get_db),
    _: SysUser = Depends(get_current_admin),
):
    total_companies = db.query(Company).count()
    total_users = db.query(WxUser).count()

    # 近30天上传趋势
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    trend_rows = (
        db.query(
            func.date(FinancialData.created_at).label("date"),
            func.count(FinancialData.id).label("count"),
        )
        .filter(FinancialData.created_at >= thirty_days_ago)
        .group_by(func.date(FinancialData.created_at))
        .order_by(func.date(FinancialData.created_at))
        .all()
    )
    upload_trend = [{"date": str(r.date), "count": r.count} for r in trend_rows]

    # 统计风险分布（获取每个企业的最新风险指标）
    risk_distribution = {"normal": 0, "remind": 0, "warning": 0, "major_risk": 0}
    warning_companies = 0
    major_risk_companies = 0

    # 获取所有企业的最新风险指标
    from sqlalchemy.orm import aliased
    subquery = (
        db.query(
            RiskIndicator.company_id,
            func.max(RiskIndicator.updated_at).label("max_updated")
        )
        .group_by(RiskIndicator.company_id)
        .subquery()
    )
    latest_indicators = (
        db.query(RiskIndicator)
        .join(subquery, (RiskIndicator.company_id == subquery.c.company_id) & (RiskIndicator.updated_at == subquery.c.max_updated))
        .all()
    )

    for ind in latest_indicators:
        # 获取各项风险等级
        levels = []
        for i in range(1, 7):
            level_val = getattr(ind, f"risk{i}_level", None)
            if level_val:
                if hasattr(level_val, 'value'):
                    levels.append(level_val.value)
                else:
                    levels.append(str(level_val))

        # 计算最高风险等级
        risk_order = {"normal": 0, "remind": 1, "warning": 2, "major_risk": 3}
        max_level = "normal"
        if levels:
            max_level = max(levels, key=lambda x: risk_order.get(x, 0))

        # 统计
        if max_level in risk_distribution:
            risk_distribution[max_level] += 1
        if max_level in ["warning", "major_risk"]:
            warning_companies += 1
        if max_level == "major_risk":
            major_risk_companies += 1

    # 兼容前端的 major 字段
    risk_distribution["major"] = risk_distribution.get("major_risk", 0)

    return {
        "total_companies": total_companies,
        "total_users": total_users,
        "warning_companies": warning_companies,
        "major_risk_companies": major_risk_companies,
        "risk_distribution": risk_distribution,
        "upload_trend": upload_trend,
    }


# ===== 企业列表与CRUD =====

@router.get("/simple-list", summary="企业简列（下拉用，全量不分页）")
async def simple_list_companies(
    db: Session = Depends(get_db),
    _: SysUser = Depends(get_current_admin),
):
    """仅返回 id + name，用于下拉框绑定企业，不分页。"""
    items = db.query(Company.id, Company.name).order_by(Company.name).all()
    return {
        "code": 200,
        "data": [{"id": c.id, "name": c.name} for c in items],
        "message": "ok",
    }


@router.get("/", summary="企业列表")

async def list_companies(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100, alias="size"),
    page_size: int = Query(None, ge=1, le=100),
    keyword: str = Query("", description="企业名称/信用代码/手机号搜索"),
    status: str = Query(""),
    risk_level: str = Query("", description="风险等级筛选"),
    db: Session = Depends(get_db),
    _: SysUser = Depends(get_current_admin),
):
    limit = page_size or size
    query = db.query(Company)
    if keyword:
        query = query.filter(
            (Company.name.ilike(f"%{keyword}%")) |
            (Company.credit_code.ilike(f"%{keyword}%")) |
            (Company.contact_phone.ilike(f"%{keyword}%")) |
            (Company.contact_name.ilike(f"%{keyword}%"))
        )
    if status:
        query = query.filter(Company.status == status)

    total = query.count()
    items = query.order_by(Company.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    result = []
    for c in items:
        # 获取企业最新风险指标
        latest_risk = (
            db.query(RiskIndicator)
            .filter(RiskIndicator.company_id == c.id)
            .order_by(desc(RiskIndicator.updated_at))
            .first()
        )
        max_risk_level = "normal"
        if latest_risk:
            levels = []
            for i in range(1, 7):
                level_val = getattr(latest_risk, f"risk{i}_level", None)
                if level_val:
                    # 兼容枚举和字符串
                    if hasattr(level_val, 'value'):
                        levels.append(level_val.value)
                    else:
                        levels.append(str(level_val))
            # 按风险严重程度排序：normal < remind < warning < major_risk
            risk_order = {"normal": 0, "remind": 1, "warning": 2, "major_risk": 3}
            if levels:
                max_level = max(levels, key=lambda x: risk_order.get(x, 0))
                max_risk_level = max_level

        item = {
            "id": c.id,
            "name": c.name,
            "credit_code": c.credit_code,
            "legal_person": c.legal_person,
            "contact_name": c.contact_name,
            "contact_phone": c.contact_phone,
            "industry": c.industry,
            "taxpayer_type": c.taxpayer_type,
            "status": c.status,
            "max_risk_level": max_risk_level,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            "bound_users": len(c.wx_users),
        }
        result.append(item)

    return {
        "code": 200,
        "data": {"total": total, "page": page, "size": limit, "items": result},
        "message": "ok",
    }


@router.post("/", summary="新增企业")
async def create_company(
    body: CompanyCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_admin),
):
    if db.query(Company).filter(Company.credit_code == body.credit_code).first():
        raise HTTPException(status_code=400, detail="统一社会信用代码已存在")
    if db.query(Company).filter(Company.contact_phone == body.contact_phone).first():
        raise HTTPException(status_code=400, detail="联系人手机号已存在")

    company = Company(**body.model_dump(), created_by=current_user.id)
    db.add(company)
    db.commit()
    db.refresh(company)
    return {"code": 200, "data": {"id": company.id}, "message": "新增成功"}


@router.get("/template", summary="企业导入模板下载")
async def download_company_template(
    _: SysUser = Depends(get_current_admin),
):
    wb = Workbook()
    ws = wb.active
    ws.title = "企业信息"
    ws.append(["企业名称*","统一社会信用代码*","法定代表人*","联系人*","联系人电话*","所属行业","纳税人类型","主管税务机关","签约日期","到期日期","状态"])
    ws.append(["示例公司","91110000XXXXXXXXXX","张三","李四","13800138000","制造业","小规模","北京市海淀区税务局","2024-01-01","2025-01-01","服务中"])
    ws.column_dimensions['A'].width = 24
    ws.column_dimensions['B'].width = 22
    buf = BytesIO()
    wb.save(buf)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''company_import_template.xlsx"},
    )


@router.get("/export", summary="导出企业信息")
async def export_companies_api(
    keyword: str = Query(""),
    status: str = Query(""),
    ids: str = Query("", description="逗号分隔的企业ID列表，优先使用"),
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_admin),
):
    # 优先按指定ID导出（批量选中场景）
    if ids:
        id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        companies = db.query(Company).filter(Company.id.in_(id_list)).all()
    else:
        query = db.query(Company)
        if keyword:
            query = query.filter(
                (Company.name.ilike(f"%{keyword}%")) |
                (Company.credit_code.ilike(f"%{keyword}%")) |
                (Company.contact_phone.ilike(f"%{keyword}%")) |
                (Company.contact_name.ilike(f"%{keyword}%"))
            )
        if status:
            query = query.filter(Company.status == status)
        companies = query.order_by(Company.created_at.desc()).all()

    rows = [{
        "id": c.id,
        "name": c.name,
        "credit_code": c.credit_code,
        "legal_person": c.legal_person,
        "contact_name": c.contact_name,
        "contact_phone": c.contact_phone,
        "industry": c.industry,
        "taxpayer_type": c.taxpayer_type,
        "tax_authority": c.tax_authority,
        "sign_date": c.sign_date,
        "expire_date": c.expire_date,
        "status": c.status,
    } for c in companies]

    excel_bytes = export_companies(rows)
    # 用纯 ASCII 文件名，避免 HTTP header 编码问题
    filename = f"companies_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        iter([excel_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.post("/import", summary="批量导入企业")
async def import_companies(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_admin),
):
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xls 文件")

    content = await file.read()
    rows = parse_import_file(content)

    created, skipped, errors = 0, 0, []
    for i, row in enumerate(rows, 2):
        try:
            name = str(row.get("企业名称") or "").strip()
            credit_code = str(row.get("统一社会信用代码") or "").strip().upper()
            legal_person = str(row.get("法定代表人") or "").strip()
            contact_name = str(row.get("联系人") or "").strip()
            contact_phone = str(row.get("联系人电话") or "").strip()
            industry = str(row.get("所属行业") or "").strip() or None
            taxpayer_type = str(row.get("纳税人类型") or "小规模").strip()
            if taxpayer_type not in ("general", "small"):
                taxpayer_type = "small"
            tax_authority = str(row.get("主管税务机关") or "").strip() or None
            status = str(row.get("状态") or "active").strip()
            if status in ("服务中", "active"): status = "active"
            elif status in ("已到期", "expired"): status = "expired"
            else: status = "active"

            sign_date_raw = row.get("签约日期")
            expire_date_raw = row.get("到期日期")
            sign_date = None
            expire_date = None
            if sign_date_raw:
                if isinstance(sign_date_raw, str):
                    sign_date = datetime.strptime(sign_date_raw.split(" ")[0].strip(), "%Y-%m-%d").date() if "-" in sign_date_raw else None
                elif hasattr(sign_date_raw, 'date'):
                    sign_date = sign_date_raw.date()
            if expire_date_raw:
                if isinstance(expire_date_raw, str):
                    expire_date = datetime.strptime(expire_date_raw.split(" ")[0].strip(), "%Y-%m-%d").date() if "-" in expire_date_raw else None
                elif hasattr(expire_date_raw, 'date'):
                    expire_date = expire_date_raw.date()

            if not name or not credit_code or not contact_phone:
                skipped += 1
                errors.append(f"第{i}行：必填字段不完整")
                continue

            existing = db.query(Company).filter(Company.credit_code == credit_code).first()
            if existing:
                skipped += 1
                errors.append(f"第{i}行：信用代码 {credit_code} 已存在，跳过")
                continue

            from app.schemas import CompanyCreate
            body = CompanyCreate(
                name=name, credit_code=credit_code, legal_person=legal_person,
                contact_name=contact_name, contact_phone=contact_phone,
                industry=industry, taxpayer_type=taxpayer_type,
                tax_authority=tax_authority, sign_date=sign_date, expire_date=expire_date,
            )
            company = Company(**body.model_dump(), created_by=current_user.id, status=status)
            db.add(company)
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


@router.get("/{company_id}", summary="企业详情")
async def get_company(
    company_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="企业不存在")
    return {
        "code": 200,
        "data": {
            "id": company.id,
            "name": company.name,
            "credit_code": company.credit_code,
            "legal_person": company.legal_person,
            "contact_name": company.contact_name,
            "contact_phone": company.contact_phone,
            "industry": company.industry,
            "taxpayer_type": company.taxpayer_type,
            "status": company.status,
            "sign_date": company.sign_date.isoformat() if company.sign_date else None,
            "expire_date": company.expire_date.isoformat() if company.expire_date else None,
        },
        "message": "ok",
    }


@router.put("/{company_id}", summary="更新企业信息")
async def update_company(
    company_id: int,
    body: CompanyUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="企业不存在")
    if body.contact_phone and db.query(Company).filter(
        Company.contact_phone == body.contact_phone, Company.id != company_id
    ).first():
        raise HTTPException(status_code=400, detail="联系人手机号已被其他企业使用")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(company, field, value)
    db.commit()
    return {"code": 200, "data": None, "message": "更新成功"}


@router.post("/batch-delete", summary="批量删除企业")
async def batch_delete_companies(
    body: dict,
    db: Session = Depends(get_db),
    _: SysUser = Depends(get_current_super_admin),
):
    ids = body.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="请选择要删除的企业")
    if not isinstance(ids, list):
        raise HTTPException(status_code=400, detail="ids 必须为数组")
    deleted = 0
    for cid in ids:
        company = db.query(Company).filter(Company.id == cid).first()
        if company:
            db.delete(company)
            deleted += 1
    db.commit()
    return {"code": 200, "data": {"deleted": deleted}, "message": f"成功删除 {deleted} 条企业记录"}


@router.delete("/{company_id}", summary="删除企业")
async def delete_company(
    company_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_super_admin),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="企业不存在")
    db.delete(company)
    db.commit()
    return {"code": 200, "data": None, "message": "删除成功"}


# ===== 文件上传接口（前端用 /upload） =====

@router.post("/{company_id}/upload", summary="上传TXT财税数据（简化接口）")
async def upload_file_simple(
    company_id: int,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_admin),
):
    """前端直接调用的上传接口，不需要指定 file_type 和 period"""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="企业不存在")

    os.makedirs(f"{UPLOAD_DIR}/{company_id}", exist_ok=True)
    file_ext = os.path.splitext(file.filename or "data.txt")[1] or ".txt"
    save_name = f"{uuid.uuid4().hex}{file_ext}"
    save_path = f"{UPLOAD_DIR}/{company_id}/{save_name}"

    async with aiofiles.open(save_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    fd = FinancialData(
        company_id=company_id,
        file_type=FinancialDataType.dzzb,
        file_name=file.filename or save_name,
        file_path=save_path,
        period=datetime.utcnow().strftime("%Y-%m"),
        status="pending",
        uploaded_by=current_user.id,
    )
    db.add(fd)
    db.commit()
    db.refresh(fd)

    # 异步ETL处理
    background_tasks.add_task(process_financial_file, fd.id, save_path, fd.file_type, company_id)

    return {
        "code": 200,
        "data": {
            "file_id": fd.id,
            "total_indicators": 0,
            "saved": 0,
            "skipped": 0,
            "message": "文件已上传，正在后台处理",
        },
        "message": "上传成功",
    }


@router.post("/{company_id}/upload-financial", summary="上传财务数据文件（完整接口）")
async def upload_financial_file(
    company_id: int,
    file_type: FinancialDataType,
    period: str = Query(..., description="数据期间，格式YYYY-MM"),
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_admin),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="企业不存在")

    os.makedirs(f"{UPLOAD_DIR}/{company_id}", exist_ok=True)
    file_ext = os.path.splitext(file.filename or "file.txt")[1] or ".txt"
    save_name = f"{uuid.uuid4().hex}{file_ext}"
    save_path = f"{UPLOAD_DIR}/{company_id}/{save_name}"

    async with aiofiles.open(save_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    fd = FinancialData(
        company_id=company_id,
        file_type=file_type,
        file_name=file.filename or save_name,
        file_path=save_path,
        period=period,
        status="pending",
        uploaded_by=current_user.id,
    )
    db.add(fd)
    db.commit()
    db.refresh(fd)
    background_tasks.add_task(process_financial_file, fd.id, save_path, file_type, company_id)

    return {"code": 200, "data": {"message": "上传成功，正在处理", "file_id": fd.id}, "message": "ok"}


@router.get("/{company_id}/financial-files", summary="企业财务文件列表")
async def list_financial_files(
    company_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    files = (
        db.query(FinancialData)
        .filter(FinancialData.company_id == company_id)
        .order_by(desc(FinancialData.created_at))
        .all()
    )
    return {
        "code": 200,
        "data": [
            {
                "id": f.id,
                "file_type": f.file_type,
                "file_name": f.file_name,
                "period": f.period,
                "status": f.status,
                "error_msg": f.error_msg,
                "record_count": f.record_count,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in files
        ],
        "message": "ok",
    }


@router.post("/{company_id}/ai-evaluate", summary="触发企业AI综合风险评估")
async def ai_evaluate_company(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_admin),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="企业不存在")

    # 获取最新风险指标
    latest = (
        db.query(RiskIndicator)
        .filter(RiskIndicator.company_id == company_id)
        .order_by(desc(RiskIndicator.created_at))
        .first()
    )

    try:
        content = await generate_risk_report(company, latest)
        return {
            "code": 200,
            "data": {"content": content, "summary": content[:200] + "..." if len(content) > 200 else content},
            "message": "评估完成",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI评估失败: {str(e)}")


@router.get("/{company_id}/evaluations", summary="企业AI评估历史")
async def list_evaluations(
    company_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    from app.models import AiReport
    query = db.query(AiReport).filter(AiReport.company_id == company_id)
    total = query.count()
    items = query.order_by(desc(AiReport.created_at)).offset((page - 1) * size).limit(size).all()
    return {
        "code": 200,
        "data": {
            "total": total,
            "items": [
                {
                    "id": r.id,
                    "risk_index": r.risk_index,
                    "summary": (r.report_content or "")[:150],
                    "content": r.report_content,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in items
            ],
        },
        "message": "ok",
    }



