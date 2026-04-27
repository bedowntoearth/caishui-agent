"""微信小程序API"""
from datetime import timedelta, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import json
import asyncio

from app.core.database import get_db
from app.core.security import create_access_token
from app.core.config import settings
from app.models import WxUser, Company, RiskIndicator, AiReport
from app.schemas import WxLoginRequest, WxLoginResponse, CompanyMiniOut, RiskIndicatorOut
from app.utils.dependencies import get_current_wx_user_company_id
from app.services.wechat_service import code2session, decrypt_phone_number
from app.services.ai_service import stream_ai_evaluation
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/miniapp", tags=["微信小程序"])


@router.post("/login", response_model=WxLoginResponse, summary="微信小程序授权登录")
async def wx_login(
    body: WxLoginRequest,
    db: Session = Depends(get_db),
):
    """
    1. code换取openid+session_key
    2. 解密手机号
    3. 手机号匹配企业
    4. 签发JWT
    """
    # 调用微信接口
    wx_data = await code2session(body.code)
    openid = wx_data.get("openid")
    session_key = wx_data.get("session_key")

    if not openid or not session_key:
        raise HTTPException(status_code=400, detail="微信授权失败，请重试")

    # 解密手机号
    phone = ""
    try:
        phone = decrypt_phone_number(session_key, body.encrypted_data, body.iv)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"手机号解密失败: {str(e)}")

    if not phone:
        raise HTTPException(status_code=400, detail="未能获取手机号，请确认授权")

    # 查找或创建WxUser
    wx_user = db.query(WxUser).filter(WxUser.openid == openid).first()
    company = db.query(Company).filter(Company.contact_phone == phone).first()
    company_id = company.id if company else None

    if wx_user:
        wx_user.phone = phone
        wx_user.company_id = company_id
        wx_user.session_key = session_key
        wx_user.last_login_at = datetime.now(timezone.utc)
    else:
        wx_user = WxUser(
            openid=openid,
            phone=phone,
            company_id=company_id,
            session_key=session_key,
            last_login_at=datetime.now(timezone.utc),
        )
        db.add(wx_user)
    db.commit()

    # 签发Token（包含company_id）
    access_token = create_access_token(
        data={"sub": openid, "company_id": company_id, "type": "access"},
        expires_delta=timedelta(days=7),
    )

    return WxLoginResponse(
        access_token=access_token,
        company_id=company_id,
        is_matched=company_id is not None,
    )


@router.get("/company/info", summary="获取当前用户关联企业信息")
async def get_company_info(
    company_id: int = Depends(get_current_wx_user_company_id),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="未找到关联企业")

    # 计算剩余天数
    days_remaining = None
    if company.expire_date:
        delta = company.expire_date - datetime.now(timezone.utc).replace(tzinfo=None)
        days_remaining = max(0, delta.days)

    # 信用代码脱敏：前6位 + ****** + 后4位
    code = company.credit_code
    credit_code_masked = code[:6] + "********" + code[-4:] if len(code) >= 10 else code

    return {
        "id": company.id,
        "name": company.name,
        "credit_code_masked": credit_code_masked,
        "legal_person": company.legal_person,
        "industry": company.industry,
        "taxpayer_type": company.taxpayer_type,
        "status": company.status,
        "sign_date": company.sign_date,
        "expire_date": company.expire_date,
        "days_remaining": days_remaining,
        "is_expiring_soon": days_remaining is not None and days_remaining <= 30,
    }


@router.get("/risk/indicators", summary="获取当前企业六项风险指标")
async def get_risk_indicators(
    company_id: int = Depends(get_current_wx_user_company_id),
    db: Session = Depends(get_db),
):
    indicator = (
        db.query(RiskIndicator)
        .filter(RiskIndicator.company_id == company_id)
        .order_by(RiskIndicator.updated_at.desc())
        .first()
    )
    if not indicator:
        return {"has_data": False, "indicators": []}

    risk_items = [
        {
            "id": indicator.id,
            "index": 1,
            "name": "是否按期申报",
            "level": indicator.risk1_level,
            "reason": indicator.risk1_reason,
        },
        {
            "id": indicator.id,
            "index": 2,
            "name": "库存现金是否异常",
            "level": indicator.risk2_level,
            "reason": indicator.risk2_reason,
        },
        {
            "id": indicator.id,
            "index": 3,
            "name": "往来款项是否长期挂账",
            "level": indicator.risk3_level,
            "reason": indicator.risk3_reason,
        },
        {
            "id": indicator.id,
            "index": 4,
            "name": "未分配利润是否异常",
            "level": indicator.risk4_level,
            "reason": indicator.risk4_reason,
        },
        {
            "id": indicator.id,
            "index": 5,
            "name": "股东及关联方是否存在长期占款",
            "level": indicator.risk5_level,
            "reason": indicator.risk5_reason,
        },
        {
            "id": indicator.id,
            "index": 6,
            "name": "暂估入账是否异常",
            "level": indicator.risk6_level,
            "reason": indicator.risk6_reason,
        },
    ]

    # 将非正常的指标排在前面
    level_order = {"major_risk": 0, "warning": 1, "remind": 2, "normal": 3}
    risk_items.sort(key=lambda x: level_order.get(x["level"], 99))

    return {
        "has_data": True,
        "period": indicator.period,
        "health_score": indicator.health_score,
        "updated_at": indicator.updated_at,
        "indicators": risk_items,
    }


@router.get("/risk/ai-eval/{risk_index}", summary="AI风险评估（SSE流式输出）")
async def ai_evaluate(
    risk_index: int,
    indicator_name: str = None,
    level: str = None,
    reason: str = None,
    company_id: int = Depends(get_current_wx_user_company_id),
    db: Session = Depends(get_db),
):
    if risk_index not in range(1, 7):
        raise HTTPException(status_code=400, detail="风险指标编号必须在1-6之间")

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="企业不存在")

    indicator = (
        db.query(RiskIndicator)
        .filter(RiskIndicator.company_id == company_id)
        .order_by(RiskIndicator.updated_at.desc())
        .first()
    )
    if not indicator:
        raise HTTPException(status_code=404, detail="暂无风险指标数据")

    async def event_generator():
        full_content = []
        try:
            async for chunk in stream_ai_evaluation(
                company, indicator, risk_index,
                override_name=indicator_name,
                override_level=level,
                override_reason=reason,
            ):
                full_content.append(chunk)
                # SSE 格式：data: {"content": "xxx"}\n\n
                yield {"event": "message", "data": '{"content": ' + json.dumps(chunk) + '}'}
                await asyncio.sleep(0)  # 让出控制权

            # 保存报告快照
            report = AiReport(
                company_id=company_id,
                risk_indicator_id=indicator.id,
                risk_index=risk_index,
                report_content="".join(full_content),
            )
            db.add(report)
            db.commit()
            yield {"event": "done", "data": str(report.id)}
        except Exception as e:
            yield {"event": "error", "data": str(e)}

    return EventSourceResponse(event_generator())


@router.get("/company/risk-indicators", summary="获取企业风险指标（小程序用）")
async def get_company_risk_indicators(
    company_id: int = Depends(get_current_wx_user_company_id),
    db: Session = Depends(get_db),
):
    """与 /risk/indicators 相同，提供别名路径供小程序调用"""
    indicator = (
        db.query(RiskIndicator)
        .filter(RiskIndicator.company_id == company_id)
        .order_by(RiskIndicator.updated_at.desc())
        .first()
    )
    if not indicator:
        return {"has_data": False, "indicators": [], "period": "", "health_score": 100}

    risk_items = [
        {"id": indicator.id, "index": 1, "name": "是否按期申报",         "level": indicator.risk1_level, "reason": indicator.risk1_reason},
        {"id": indicator.id, "index": 2, "name": "库存现金是否异常",      "level": indicator.risk2_level, "reason": indicator.risk2_reason},
        {"id": indicator.id, "index": 3, "name": "往来款项是否长期挂账",  "level": indicator.risk3_level, "reason": indicator.risk3_reason},
        {"id": indicator.id, "index": 4, "name": "未分配利润是否异常",    "level": indicator.risk4_level, "reason": indicator.risk4_reason},
        {"id": indicator.id, "index": 5, "name": "股东及关联方长期占款",  "level": indicator.risk5_level, "reason": indicator.risk5_reason},
        {"id": indicator.id, "index": 6, "name": "暂估入账是否异常",      "level": indicator.risk6_level, "reason": indicator.risk6_reason},
    ]
    level_order = {"major_risk": 0, "warning": 1, "remind": 2, "normal": 3}
    risk_items.sort(key=lambda x: level_order.get(x["level"], 99))

    return {
        "has_data": True,
        "period": indicator.period,
        "health_score": indicator.health_score,
        "indicators": risk_items,
    }


@router.post("/ai-evaluate", summary="AI风险评估（小程序非流式）")
async def ai_evaluate_post(
    body: dict,
    company_id: int = Depends(get_current_wx_user_company_id),
    db: Session = Depends(get_db),
):
    """
    小程序端点击「AI分析」触发评估，返回完整报告文本
    body: { company_id, indicator_id, indicator_name, level, reason }
    """
    from app.services.ai_service import generate_single_indicator_report
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="企业不存在")

    indicator_name = body.get("indicator_name", "")
    level = body.get("level", "warning")
    reason = body.get("reason", "")

    try:
        content = await generate_single_indicator_report(
            company=company,
            indicator_name=indicator_name,
            level=level,
            reason=reason,
        )
        # 保存记录
        indicator = (
            db.query(RiskIndicator)
            .filter(RiskIndicator.company_id == company_id)
            .order_by(RiskIndicator.updated_at.desc())
            .first()
        )
        if indicator:
            report = AiReport(
                company_id=company_id,
                risk_indicator_id=indicator.id,
                risk_index=body.get("risk_index", 1),
                report_content=content,
            )
            db.add(report)
            db.commit()
        return {"content": content, "result": content}
    except httpx.HTTPStatusError as e:
        # AI API 返回错误状态码
        try:
            error_detail = e.response.json()
        except:
            error_detail = e.response.text
        raise HTTPException(status_code=500, detail=f"AI服务HTTP错误: {e.response.status_code}, 详情: {error_detail}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI评估失败: {str(e)}")


@router.get("/risk/ai-history/{risk_index}", summary="获取历史AI评估报告")
async def get_ai_history(
    risk_index: int,
    company_id: int = Depends(get_current_wx_user_company_id),
    db: Session = Depends(get_db),
):
    reports = (
        db.query(AiReport)
        .filter(AiReport.company_id == company_id, AiReport.risk_index == risk_index)
        .order_by(AiReport.created_at.desc())
        .limit(5)
        .all()
    )
    return [
        {
            "id": r.id,
            "risk_index": r.risk_index,
            "report_content": r.report_content,
            "created_at": r.created_at,
        }
        for r in reports
    ]
