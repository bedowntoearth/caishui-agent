"""风险指标自动计算引擎"""
from app.models import RiskIndicator, RiskLevel
from app.schemas import RiskIndicatorCreate


def calculate_risk_indicators(data: RiskIndicatorCreate) -> dict:
    """根据输入数据自动计算六项风险等级"""
    result = {}

    # ---- 指标1：是否按期申报 ----
    if not data.tax_declared or data.overdue_count >= 1:
        result["risk1_level"] = RiskLevel.major_risk
        result["risk1_reason"] = f"存在{data.overdue_count}次报税逾期，未按期完成申报"
    else:
        result["risk1_level"] = RiskLevel.normal
        result["risk1_reason"] = "按期申报，无逾期记录"

    # ---- 指标2：库存现金是否异常 ----
    cash = data.cash_balance
    if cash is None:
        result["risk2_level"] = RiskLevel.normal
        result["risk2_reason"] = "暂无数据"
    elif cash < 0:
        result["risk2_level"] = RiskLevel.major_risk
        result["risk2_reason"] = f"库存现金为负数（{cash:.2f}元），存在账务异常"
    elif cash > 10000:
        result["risk2_level"] = RiskLevel.warning
        result["risk2_reason"] = f"库存现金金额较大（{cash:.2f}元），超过10,000元，存在大额现金风险"
    else:
        result["risk2_level"] = RiskLevel.normal
        result["risk2_reason"] = f"库存现金正常（{cash:.2f}元）"

    # ---- 指标3：往来款项是否长期挂账 ----
    months_list = [
        m for m in [
            data.ar_overdue_months,
            data.ap_overdue_months,
            data.other_ar_months,
            data.other_ap_months,
        ] if m is not None
    ]
    if not months_list:
        result["risk3_level"] = RiskLevel.normal
        result["risk3_reason"] = "暂无往来款数据"
    else:
        max_months = max(months_list)
        details = []
        if data.ar_overdue_months and data.ar_overdue_months > 0:
            details.append(f"应收账款挂账{data.ar_overdue_months:.0f}个月")
        if data.ap_overdue_months and data.ap_overdue_months > 0:
            details.append(f"应付账款挂账{data.ap_overdue_months:.0f}个月")
        if data.other_ar_months and data.other_ar_months > 0:
            details.append(f"其他应收款挂账{data.other_ar_months:.0f}个月")
        if data.other_ap_months and data.other_ap_months > 0:
            details.append(f"其他应付款挂账{data.other_ap_months:.0f}个月")

        if max_months >= 12:
            result["risk3_level"] = RiskLevel.major_risk
            result["risk3_reason"] = "；".join(details) + "，挂账超过12个月，判定为重大风险"
        elif max_months >= 6:
            result["risk3_level"] = RiskLevel.warning
            result["risk3_reason"] = "；".join(details) + "，挂账超过6个月，预警"
        elif max_months >= 3:
            result["risk3_level"] = RiskLevel.remind
            result["risk3_reason"] = "；".join(details) + "，挂账超过3个月，请关注"
        else:
            result["risk3_level"] = RiskLevel.normal
            result["risk3_reason"] = "往来款项挂账未超过3个月，正常"

    # ---- 指标4：未分配利润是否异常 ----
    earnings = data.retained_earnings
    assets = data.total_assets
    if earnings is None or assets is None or assets == 0:
        result["risk4_level"] = RiskLevel.normal
        result["risk4_reason"] = "暂无数据"
    elif earnings < 0 and abs(earnings) > assets * 0.5:
        result["risk4_level"] = RiskLevel.major_risk
        ratio = abs(earnings) / assets * 100
        result["risk4_reason"] = f"未分配利润为负数（{earnings:.2f}元），累计亏损占资产总额的{ratio:.1f}%（>50%），存在严重亏损风险"
    elif earnings > 0 and earnings > assets * 0.6:
        ratio = earnings / assets * 100
        result["risk4_level"] = RiskLevel.warning
        result["risk4_reason"] = f"未分配利润（{earnings:.2f}元）占资产总额的{ratio:.1f}%（>60%），利润长期累积未分配"
    else:
        result["risk4_level"] = RiskLevel.normal
        result["risk4_reason"] = f"未分配利润（{earnings:.2f}元）正常"

    # ---- 指标5：股东及关联方占款 ----
    loan_months = data.shareholder_loan_months
    if loan_months is None:
        result["risk5_level"] = RiskLevel.normal
        result["risk5_reason"] = "暂无数据"
    elif loan_months >= 3:
        result["risk5_level"] = RiskLevel.major_risk
        result["risk5_reason"] = f"股东及关联方借款挂账{loan_months:.0f}个月（>3个月），存在占款风险"
    else:
        result["risk5_level"] = RiskLevel.normal
        result["risk5_reason"] = f"股东及关联方借款挂账{loan_months:.0f}个月，暂无异常"

    # ---- 指标6：暂估入账是否异常 ----
    est_months = data.estimated_entry_months
    if est_months is None and not data.has_year_end_estimated:
        result["risk6_level"] = RiskLevel.normal
        result["risk6_reason"] = "本期无暂估入账"
    elif data.has_year_end_estimated:
        result["risk6_level"] = RiskLevel.major_risk
        result["risk6_reason"] = "12月份仍存在暂估未冲销，判定为跨年风险，需重点处理"
    elif est_months and est_months >= 3:
        result["risk6_level"] = RiskLevel.warning
        result["risk6_reason"] = f"暂估入账已挂账{est_months:.0f}个月（>3个月），超期未冲销，预警"
    elif est_months and est_months > 0:
        result["risk6_level"] = RiskLevel.remind
        result["risk6_reason"] = f"本月存在暂估入账（挂账{est_months:.0f}个月），请及时处理"
    else:
        result["risk6_level"] = RiskLevel.normal
        result["risk6_reason"] = "暂估入账正常"

    # ---- 综合健康度得分（100分制）----
    level_scores = {
        RiskLevel.normal: 100,
        RiskLevel.remind: 70,
        RiskLevel.warning: 40,
        RiskLevel.major_risk: 0,
    }
    weights = [0.2, 0.15, 0.2, 0.15, 0.15, 0.15]  # 六项权重
    levels = [
        result["risk1_level"],
        result["risk2_level"],
        result["risk3_level"],
        result["risk4_level"],
        result["risk5_level"],
        result["risk6_level"],
    ]
    score = sum(level_scores[lv] * w for lv, w in zip(levels, weights))
    result["health_score"] = round(score, 1)

    return result
