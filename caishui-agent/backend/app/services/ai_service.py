"""AI风险评估服务（SSE流式输出）"""
import httpx
import json
from typing import AsyncGenerator
from app.core.config import settings
from app.models import RiskIndicator, Company, RiskLevel


RISK_NAMES = {
    1: "是否按期申报",
    2: "库存现金是否异常",
    3: "往来款项是否长期挂账",
    4: "未分配利润是否异常",
    5: "股东及关联方是否存在长期占款",
    6: "暂估入账是否异常",
}

SYSTEM_PROMPT = """你是一位专业的财税风险顾问，具备15年以上财税代理实务经验。你的服务对象是中小微企业老板，他们通常没有专业财务背景。
你的任务是：
1. 用通俗易懂的语言解释财税风险
2. 明确告知风险的严重程度和可能造成的后果
3. 给出具体、可操作的应对建议
4. 语言风格亲切专业，避免过于学术化

输出格式要求：
## 风险概述
[用1-2句话说明当前风险状况]

## 风险分析
[详细说明为什么会有这个风险，可能造成什么影响]

## 应对建议
[给出3-5条具体的行动建议，每条建议需要可执行]

## 注意事项
[特别提醒事项]
"""


def build_prompt(
    company: Company, 
    indicator: RiskIndicator, 
    risk_index: int,
    override_name: str = None,
    override_level: str = None,
    override_reason: str = None,
) -> str:
    level_map = {
        RiskLevel.normal: "正常",
        RiskLevel.remind: "提醒",
        RiskLevel.warning: "预警",
        RiskLevel.major_risk: "重大风险",
    }
    
    # 优先使用覆盖参数，否则使用数据库中的数据
    risk_name = override_name or RISK_NAMES.get(risk_index, f"风险指标{risk_index}")

    # 获取对应指标的具体数据
    level_attr = f"risk{risk_index}_level"
    reason_attr = f"risk{risk_index}_reason"
    
    if override_level:
        risk_level = override_level
    else:
        risk_level = getattr(indicator, level_attr, RiskLevel.normal)
    
    if override_reason:
        risk_reason = override_reason
    else:
        risk_reason = getattr(indicator, reason_attr, "")

    prompt = f"""请对以下企业的财税风险进行专业评估：

企业信息：
- 企业名称：{company.name}
- 纳税人性质：{"一般纳税人" if company.taxpayer_type == "general" else "小规模纳税人"}
- 所属行业：{company.industry or "未知"}
- 统计期间：{indicator.period}

待评估风险项：{risk_name}
当前风险等级：{level_map.get(risk_level, risk_level)}
触发原因：{risk_reason or "无"}

"""

    # 附加具体财务数据
    if risk_index == 1:
        prompt += f"具体情况：是否按期申报={indicator.tax_declared}，逾期次数={indicator.overdue_count}\n"
    elif risk_index == 2:
        prompt += f"具体情况：库存现金余额={indicator.cash_balance}元\n"
    elif risk_index == 3:
        prompt += (
            f"具体情况：应收账款挂账={indicator.ar_overdue_months}个月，"
            f"应付账款挂账={indicator.ap_overdue_months}个月，"
            f"其他应收款挂账={indicator.other_ar_months}个月，"
            f"其他应付款挂账={indicator.other_ap_months}个月\n"
        )
    elif risk_index == 4:
        prompt += f"具体情况：未分配利润={indicator.retained_earnings}元，资产总额={indicator.total_assets}元\n"
    elif risk_index == 5:
        prompt += f"具体情况：股东及关联方借款挂账={indicator.shareholder_loan_months}个月\n"
    elif risk_index == 6:
        prompt += (
            f"具体情况：暂估挂账={indicator.estimated_entry_months}个月，"
            f"12月份存在暂估未冲销={indicator.has_year_end_estimated}\n"
        )

    prompt += "\n请按照要求格式给出专业的风险评估报告。"
    return prompt


async def generate_risk_report(company: Company, indicator) -> str:
    """非流式 AI 综合评估（管理端/企业详情页使用）"""
    if indicator is None:
        prompt = f"企业「{company.name}」尚未录入风险指标数据，请给出一般性财税风险提示。"
    else:
        parts = []
        for i in range(1, 7):
            level = getattr(indicator, f"risk{i}_level", "normal")
            reason = getattr(indicator, f"risk{i}_reason", "") or ""
            name = RISK_NAMES.get(i, f"指标{i}")
            level_cn = {"normal": "正常", "remind": "提醒", "warning": "预警", "major_risk": "重大风险"}.get(level, level)
            parts.append(f"  {i}. {name}：{level_cn}{'（' + reason + '）' if reason else ''}")

        prompt = (
            f"请对企业「{company.name}」（{company.industry or '未知行业'}）"
            f"统计期间 {indicator.period} 的六项财税风险指标进行综合评估：\n"
            + "\n".join(parts)
            + "\n\n请给出综合风险评估报告，包括总体风险评级、重点风险分析和整改建议。"
        )

    headers = {
        "Authorization": f"Bearer {settings.AI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.AI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "temperature": 0.7,
        "max_tokens": settings.AI_MAX_TOKENS,
    }

    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            f"{settings.AI_API_BASE}/chat/completions",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        # MiniMax 等模型 content 可能为空，实际内容在 reasoning_content 中
        content = data["choices"][0]["message"].get("content") or \
                  data["choices"][0]["message"].get("reasoning_content") or \
                  data["choices"][0]["message"].get("reasoning") or ""
        return content


async def generate_single_indicator_report(
    company: Company,
    indicator_name: str,
    level: str,
    reason: str,
) -> str:
    """非流式 AI 单项指标评估（小程序端使用）"""
    import logging
    logger = logging.getLogger(__name__)
    
    level_cn = {"normal": "正常", "remind": "提醒", "warning": "预警", "major_risk": "重大风险", "major": "重大风险"}.get(level, level)
    prompt = (
        f"请对以下企业的财税风险进行专业评估：\n\n"
        f"企业：{company.name}（{company.industry or '未知行业'}）\n"
        f"风险指标：{indicator_name}\n"
        f"风险等级：{level_cn}\n"
        f"触发原因：{reason or '无'}\n\n"
        f"请按要求格式给出针对该指标的专业评估报告。"
    )

    headers = {
        "Authorization": f"Bearer {settings.AI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.AI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "temperature": 0.7,
        "max_tokens": settings.AI_MAX_TOKENS,
    }

    api_url = f"{settings.AI_API_BASE}/chat/completions"
    logger.info(f"AI评估请求: API={api_url}, Model={settings.AI_MODEL}")
    
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(api_url, headers=headers, json=payload)
        logger.info(f"AI响应状态: {resp.status_code}")
        
        if resp.status_code != 200:
            error_text = resp.text[:500] if resp.text else "无响应内容"
            raise Exception(f"API返回错误 {resp.status_code}: {error_text}")
        
        data = resp.json()
        if "choices" not in data or not data["choices"]:
            raise Exception(f"API响应格式异常，缺少choices: {str(data)[:200]}")
        
        msg = data["choices"][0]["message"]
        # MiniMax 等模型 content 可能为空，实际内容在 reasoning_content 中
        content = msg.get("content") or msg.get("reasoning_content") or msg.get("reasoning") or ""
        logger.info(f"AI评估成功，内容长度: {len(content)}")
        return content


async def stream_ai_evaluation(
    company: Company,
    indicator: RiskIndicator,
    risk_index: int,
    override_name: str = None,
    override_level: str = None,
    override_reason: str = None,
) -> AsyncGenerator[str, None]:
    """流式调用AI大模型，生成风险评估报告
    
    Args:
        override_name: 覆盖指标名称
        override_level: 覆盖风险等级
        override_reason: 覆盖触发原因
    """
    prompt = build_prompt(
        company, indicator, risk_index,
        override_name=override_name,
        override_level=override_level,
        override_reason=override_reason,
    )

    headers = {
        "Authorization": f"Bearer {settings.AI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.AI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": True,
        "temperature": 0.7,
        "max_tokens": 1500,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{settings.AI_API_BASE}/chat/completions",
            headers=headers,
            json=payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data["choices"][0].get("delta", {})
                        # 优先取 content 字段（正文），忽略 reasoning_content（思考过程）
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
