"""风险指标管理API"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from io import BytesIO
from app.core.database import get_db
from app.models import SysUser
from app.models import RiskIndicator, Company, SysUser, RiskLevel, AiReport
from app.schemas import RiskIndicatorCreate, RiskIndicatorOut
from app.utils.dependencies import get_current_admin
from app.services.risk_engine import calculate_risk_indicators
from app.utils.xlsx_utils import export_risk_indicators, parse_import_file

router = APIRouter(prefix="/risk-indicators", tags=["风险指标管理"])

# 六项指标名称映射（管理端录入使用扁平化结构）
RISK_NAMES = {
    "risk1": "是否按期申报",
    "risk2": "库存现金是否异常",
    "risk3": "往来款项长期挂账",
    "risk4": "未分配利润异常",
    "risk5": "股东及关联方占款",
    "risk6": "暂估入账异常",
}


@router.get("/", summary="风险指标列表（按企业/等级筛选）")
async def list_risk_indicators(
    company_id: Optional[int] = Query(None),
    level: Optional[str] = Query(None, description="风险等级：normal/remind/warning/major"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    """返回平铺的风险指标列表（每个指标项一行）"""
    query = db.query(RiskIndicator)
    if company_id:
        query = query.filter(RiskIndicator.company_id == company_id)

    indicators_db = query.order_by(desc(RiskIndicator.updated_at)).all()

    # 展开六项指标为列表
    items = []
    for ind in indicators_db:
        for i in range(1, 7):
            ind_level = getattr(ind, f"risk{i}_level", "normal")
            ind_reason = getattr(ind, f"risk{i}_reason", None)
            if level and ind_level != level:
                continue
            items.append({
                "id": ind.id * 10 + i,   # 虚拟ID用于展示
                "real_id": ind.id,
                "company_id": ind.company_id,
                "risk_index": i,
                "name": RISK_NAMES.get(f"risk{i}", f"指标{i}"),
                "level": ind_level,
                "reason": ind_reason,
                "period": ind.period,
                "health_score": ind.health_score,
                "created_at": ind.created_at.isoformat() if ind.created_at else None,
                "updated_at": ind.updated_at.isoformat() if ind.updated_at else None,
            })

    total = len(items)
    start = (page - 1) * size
    paged_items = items[start: start + size]

    return {"code": 200, "data": {"total": total, "items": paged_items}, "message": "ok"}


@router.get("/overview", summary="风险指标总览")
async def risk_overview(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    risk_level: str = Query(""),
    keyword: str = Query(""),
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    query = (
        db.query(RiskIndicator, Company)
        .join(Company, RiskIndicator.company_id == Company.id)
    )
    if keyword:
        query = query.filter(Company.name.ilike(f"%{keyword}%"))
    if risk_level:
        query = query.filter(
            (RiskIndicator.risk1_level == risk_level) |
            (RiskIndicator.risk2_level == risk_level) |
            (RiskIndicator.risk3_level == risk_level) |
            (RiskIndicator.risk4_level == risk_level) |
            (RiskIndicator.risk5_level == risk_level) |
            (RiskIndicator.risk6_level == risk_level)
        )

    total = query.count()
    rows = (
        query.order_by(desc(RiskIndicator.updated_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for indicator, company in rows:
        def get_level_str(level_val):
            if hasattr(level_val, 'value'):
                return level_val.value
            return str(level_val) if level_val else "normal"
        
        items.append({
            "id": indicator.id,
            "company_id": company.id,
            "company_name": company.name,
            "credit_code": company.credit_code,
            "period": indicator.period,
            "health_score": indicator.health_score,
            "risk_levels": {
                "risk1": get_level_str(indicator.risk1_level),
                "risk2": get_level_str(indicator.risk2_level),
                "risk3": get_level_str(indicator.risk3_level),
                "risk4": get_level_str(indicator.risk4_level),
                "risk5": get_level_str(indicator.risk5_level),
                "risk6": get_level_str(indicator.risk6_level),
            },
            "updated_at": indicator.updated_at.isoformat() if indicator.updated_at else None,
        })

    return {"code": 200, "data": {"total": total, "page": page, "items": items}, "message": "ok"}


@router.get("/company/{company_id}/ai-reports", summary="获取企业AI评估历史")
async def get_company_ai_reports(
    company_id: int,
    risk_index: int = Query(0, description="风险指标编号，0表示全部"),
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    """获取企业的AI评估记录"""
    query = db.query(AiReport).filter(AiReport.company_id == company_id)
    if risk_index > 0:
        query = query.filter(AiReport.risk_index == risk_index)
    reports = query.order_by(desc(AiReport.created_at)).limit(20).all()
    return {
        "code": 200,
        "data": [
            {
                "id": r.id,
                "risk_index": r.risk_index,
                "report_content": r.report_content,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reports
        ],
        "message": "ok",
    }


@router.get("/company/{company_id}", summary="企业最新风险指标")
async def get_company_risk(
    company_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    indicator = (
        db.query(RiskIndicator)
        .filter(RiskIndicator.company_id == company_id)
        .order_by(desc(RiskIndicator.updated_at))
        .first()
    )
    if not indicator:
        raise HTTPException(status_code=404, detail="暂无风险数据")

    # 手动构建返回值，确保枚举转为字符串
    def get_level_str(level_val):
        if hasattr(level_val, 'value'):
            return level_val.value
        return str(level_val) if level_val else "normal"

    data = {
        "id": indicator.id,
        "company_id": indicator.company_id,
        "period": indicator.period,
        # 指标1
        "tax_declared": indicator.tax_declared,
        "overdue_count": indicator.overdue_count,
        "risk1_level": get_level_str(indicator.risk1_level),
        "risk1_reason": indicator.risk1_reason,
        # 指标2
        "cash_balance": indicator.cash_balance,
        "risk2_level": get_level_str(indicator.risk2_level),
        "risk2_reason": indicator.risk2_reason,
        # 指标3
        "ar_overdue_months": indicator.ar_overdue_months,
        "ap_overdue_months": indicator.ap_overdue_months,
        "other_ar_months": indicator.other_ar_months,
        "other_ap_months": indicator.other_ap_months,
        "risk3_level": get_level_str(indicator.risk3_level),
        "risk3_reason": indicator.risk3_reason,
        # 指标4
        "retained_earnings": indicator.retained_earnings,
        "total_assets": indicator.total_assets,
        "risk4_level": get_level_str(indicator.risk4_level),
        "risk4_reason": indicator.risk4_reason,
        # 指标5
        "shareholder_loan_months": indicator.shareholder_loan_months,
        "risk5_level": get_level_str(indicator.risk5_level),
        "risk5_reason": indicator.risk5_reason,
        # 指标6
        "estimated_entry_months": indicator.estimated_entry_months,
        "has_year_end_estimated": indicator.has_year_end_estimated,
        "risk6_level": get_level_str(indicator.risk6_level),
        "risk6_reason": indicator.risk6_reason,
        # 综合
        "health_score": indicator.health_score,
        "updated_at": indicator.updated_at,
    }
    return {"code": 200, "data": data, "message": "ok"}


@router.post("/", summary="录入/更新风险指标")
async def upsert_risk_indicator(
    body: RiskIndicatorCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_admin),
):
    company = db.query(Company).filter(Company.id == body.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="企业不存在")

    risk_result = calculate_risk_indicators(body)

    existing = (
        db.query(RiskIndicator)
        .filter(
            RiskIndicator.company_id == body.company_id,
            RiskIndicator.period == body.period,
        )
        .first()
    )

    data_dict = body.model_dump()
    data_dict.update(risk_result)
    data_dict["updated_by"] = current_user.id

    if existing:
        for k, v in data_dict.items():
            setattr(existing, k, v)
        db.commit()
        db.refresh(existing)
        return {"code": 200, "data": {"id": existing.id}, "message": "更新成功"}
    else:
        indicator = RiskIndicator(**data_dict)
        db.add(indicator)
        db.commit()
        db.refresh(indicator)
        return {"code": 200, "data": {"id": indicator.id}, "message": "录入成功"}


@router.put("/{indicator_id}", summary="修改风险指标")
async def update_risk_indicator(
    indicator_id: int,
    body: dict,
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    # 前端传递真实数据库ID，无需解析虚拟ID
    indicator = db.query(RiskIndicator).filter(RiskIndicator.id == indicator_id).first()
    if not indicator:
        raise HTTPException(status_code=404, detail="记录不存在")

    risk_index = body.get("risk_index")
    if risk_index and 1 <= risk_index <= 6:
        setattr(indicator, f"risk{risk_index}_level", body.get("level", "normal"))
        setattr(indicator, f"risk{risk_index}_reason", body.get("reason", ""))
    db.commit()
    return {"code": 200, "data": None, "message": "更新成功"}


@router.post("/batch-delete-records", summary="批量删除风险指标记录（按ID）")
async def batch_delete_risk_indicators(
    body: dict,
    db: Session = Depends(get_db),
    _: SysUser = Depends(get_current_admin),
):
    ids = body.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="请选择要删除的指标记录")
    if not isinstance(ids, list):
        raise HTTPException(status_code=400, detail="ids 必须为数组")
    deleted = 0
    for iid in ids:
        record = db.query(RiskIndicator).filter(RiskIndicator.id == iid).first()
        if record:
            db.delete(record)
            deleted += 1
    db.commit()
    return {"code": 200, "data": {"deleted": deleted}, "message": f"成功删除 {deleted} 条记录"}


@router.delete("/{indicator_id}", summary="删除风险指标记录")
async def delete_risk_indicator(
    indicator_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    # 前端传递真实数据库ID，无需解析虚拟ID
    indicator = db.query(RiskIndicator).filter(RiskIndicator.id == indicator_id).first()
    if not indicator:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(indicator)
    db.commit()
    return {"code": 200, "data": None, "message": "删除成功"}


@router.get("/template", summary="风险指标导入模板下载")
async def download_risk_template(
    _: SysUser = Depends(get_current_admin),
):
    wb = Workbook()
    ws = wb.active
    ws.title = "风险指标"
    headers = ["企业名称*","统计期间*","是否按期申报","逾期次数","库存现金余额",
               "应收账款挂账月数","应付账款挂账月数","其他应收款挂账月数","其他应付款挂账月数",
               "未分配利润","资产总额","股东借款挂账月数","暂估挂账月数","12月份暂估未冲销"]
    ws.append(headers)
    ws.append(["示例公司","2024-01","是","0","50000","","","","","100000","500000","","","否"])
    for col in range(1, len(headers)+1):
        ws.column_dimensions[ws.cell(1, col).column_letter].width = 16
    buf = BytesIO()
    wb.save(buf)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''risk_indicator_import_template.xlsx"},
    )


@router.get("/export", summary="导出风险指标")
async def export_risk_api(
    keyword: str = Query(""),
    risk_level: str = Query(""),
    db: Session = Depends(get_db),
    _: SysUser = Depends(get_current_admin),
):
    query = db.query(RiskIndicator)
    if keyword:
        cids = [c.id for c in db.query(Company).filter(Company.name.ilike(f"%{keyword}%")).all()]
        query = query.filter(RiskIndicator.company_id.in_(cids)) if cids else query.filter(False)

    indicators = query.order_by(desc(RiskIndicator.updated_at)).all()

    rows = []
    for ind in indicators:
        rows.append({
            "company_id": ind.company_id,
            "company_name": db.query(Company).filter(Company.id == ind.company_id).first().name if db.query(Company).filter(Company.id == ind.company_id).first() else "",
            "period": ind.period,
            "health_score": ind.health_score,
            "overall_level": ind.risk1_level,
            "risk_levels": {
                "risk1": ind.risk1_level,
                "risk2": ind.risk2_level,
                "risk3": ind.risk3_level,
                "risk4": ind.risk4_level,
                "risk5": ind.risk5_level,
                "risk6": ind.risk6_level,
            },
            "updated_at": ind.updated_at.isoformat() if ind.updated_at else None,
        })

    excel_bytes = export_risk_indicators(rows)
    filename = f"risk_indicators_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        iter([excel_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.post("/import", summary="批量导入风险指标")
async def import_risk_indicators(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_admin),
):
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xls 文件")

    content = await file.read()
    raw_rows = parse_import_file(content)

    created, skipped, errors = 0, 0, []
    for i, row in enumerate(raw_rows, 2):
        try:
            company_name = str(row.get("企业名称") or "").strip()
            period = str(row.get("统计期间") or "").strip()

            if not company_name or not period:
                skipped += 1
                errors.append(f"第{i}行：企业名称和统计期间不能为空")
                continue

            company = db.query(Company).filter(Company.name == company_name).first()
            if not company:
                skipped += 1
                errors.append(f"第{i}行：企业「{company_name}」不存在，跳过")
                continue

            existing = db.query(RiskIndicator).filter(
                RiskIndicator.company_id == company.id,
                RiskIndicator.period == period,
            ).first()
            if existing:
                skipped += 1
                errors.append(f"第{i}行：{company_name} {period} 已存在，跳过")
                continue

            body = RiskIndicatorCreate(
                company_id=company.id,
                period=period,
                tax_declared=str(row.get("是否按期申报", "是")).strip() in ("是", "true", "True"),
                overdue_count=int(row.get("逾期次数") or 0),
                cash_balance=float(row.get("库存现金余额")) if row.get("库存现金余额") else None,
                ar_overdue_months=float(row.get("应收账款挂账月数")) if row.get("应收账款挂账月数") else None,
                ap_overdue_months=float(row.get("应付账款挂账月数")) if row.get("应付账款挂账月数") else None,
                other_ar_months=float(row.get("其他应收款挂账月数")) if row.get("其他应收款挂账月数") else None,
                other_ap_months=float(row.get("其他应付款挂账月数")) if row.get("其他应付款挂账月数") else None,
                retained_earnings=float(row.get("未分配利润")) if row.get("未分配利润") else None,
                total_assets=float(row.get("资产总额")) if row.get("资产总额") else None,
                shareholder_loan_months=float(row.get("股东借款挂账月数")) if row.get("股东借款挂账月数") else None,
                estimated_entry_months=float(row.get("暂估挂账月数")) if row.get("暂估挂账月数") else None,
                has_year_end_estimated=str(row.get("12月份暂估未冲销", "否")).strip() in ("是", "true"),
            )
            risk_result = calculate_risk_indicators(body)
            data_dict = body.model_dump()
            data_dict.update(risk_result)
            data_dict["updated_by"] = current_user.id
            indicator = RiskIndicator(**data_dict)
            db.add(indicator)
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


@router.get("/{indicator_id}", summary="风险指标详情")
async def get_risk_indicator(
    indicator_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_admin),
):
    indicator = db.query(RiskIndicator).filter(RiskIndicator.id == indicator_id).first()
    if not indicator:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"code": 200, "data": RiskIndicatorOut.model_validate(indicator), "message": "ok"}

@router.post("/batch-delete", summary="批量删除风险指标（按企业+期间）")
async def batch_delete_risk_by_company_period(
    body: dict,
    db: Session = Depends(get_db),
    _: SysUser = Depends(get_current_admin),
):
    """
    批量删除：接收 [{company_id, period}] 数组，删除该企业该期间的所有风险指标记录。
    用于风险指标管理页的 overview 表格批量操作。
    """
    items = body.get("items", [])
    if not items:
        raise HTTPException(status_code=400, detail="请选择要删除的记录")
    deleted = 0
    for item in items:
        cid = item.get("company_id")
        period = item.get("period")
        if not cid or not period:
            continue
        records = db.query(RiskIndicator).filter(
            RiskIndicator.company_id == cid,
            RiskIndicator.period == period,
        ).all()
        for r in records:
            db.delete(r)
            deleted += 1
    db.commit()
    return {"code": 200, "data": {"deleted": deleted}, "message": f"成功删除 {deleted} 条记录"}

