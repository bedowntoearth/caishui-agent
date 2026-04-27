"""
财务数据ETL处理管道
支持解析 DZZB.TXT（电子账簿）、KJKM.TXT（会计科目）、
JZPZ.TXT（记账凭证）、WLDW.TXT（往来单位）、CHXX.TXT（存货信息）
"""
import re
import json
from datetime import datetime
from typing import Optional
from app.core.logger import logger


# 科目编号到业务含义的映射（核心财税风险相关科目）
ACCOUNT_MAP = {
    "1001": "库存现金",
    "1002": "银行存款",
    "1122": "应收账款",
    "1123": "预付账款",
    "2201": "应付账款",
    "2202": "预收账款",
    "1221": "其他应收款",
    "2241": "其他应付款",
    "3101": "实收资本",
    "3131": "未分配利润",
    "1401": "原材料",
    "1405": "库存商品",
    "1601": "固定资产",
    "4001": "主营业务收入",
    "5001": "主营业务成本",
}


def clean_amount(value_str: str) -> Optional[float]:
    """清理金额字符串，统一转为浮点数"""
    if not value_str:
        return None
    # 去除货币符号、千位分隔符、空格
    cleaned = re.sub(r"[¥,$,，\s]", "", str(value_str))
    cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def normalize_date(date_str: str) -> Optional[str]:
    """标准化日期格式为 YYYY-MM-DD"""
    if not date_str:
        return None
    date_str = str(date_str).strip()
    # 尝试多种格式
    formats = [
        "%Y%m%d", "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d",
        "%Y年%m月%d日", "%y%m%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_kjkm(content: str) -> dict:
    """
    解析会计科目文件 KJKM.TXT
    格式示例（制表符分隔）：
    科目编号\t科目名称\t科目级次\t借贷方向\t期初余额\t本期借方\t本期贷方\t期末余额
    """
    accounts = {}
    lines = content.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "\t" not in line:
            continue
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) < 4:
            continue
        code = parts[0]
        name = parts[1] if len(parts) > 1 else ""
        opening_balance = clean_amount(parts[4]) if len(parts) > 4 else None
        current_debit = clean_amount(parts[5]) if len(parts) > 5 else None
        current_credit = clean_amount(parts[6]) if len(parts) > 6 else None
        closing_balance = clean_amount(parts[7]) if len(parts) > 7 else None

        accounts[code] = {
            "code": code,
            "name": name,
            "business_name": ACCOUNT_MAP.get(code, name),
            "opening_balance": opening_balance,
            "current_debit": current_debit,
            "current_credit": current_credit,
            "closing_balance": closing_balance,
        }
    return accounts


def parse_jzpz(content: str) -> list:
    """
    解析记账凭证 JZPZ.TXT
    格式示例（制表符分隔）：
    凭证号\t日期\t摘要\t科目编号\t借方金额\t贷方金额
    """
    entries = []
    lines = content.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "\t" not in line:
            continue
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) < 4:
            continue
        try:
            entry = {
                "voucher_no": parts[0],
                "date": normalize_date(parts[1]) if len(parts) > 1 else None,
                "summary": parts[2] if len(parts) > 2 else "",
                "account_code": parts[3] if len(parts) > 3 else "",
                "debit_amount": clean_amount(parts[4]) if len(parts) > 4 else 0.0,
                "credit_amount": clean_amount(parts[5]) if len(parts) > 5 else 0.0,
            }
            entries.append(entry)
        except Exception:
            continue
    return entries


def parse_dzzb(content: str) -> dict:
    """
    解析电子账簿 DZZB.TXT
    格式示例（制表符分隔）：
    科目编号\t科目名称\t期初余额\t本期借方\t本期贷方\t期末余额
    """
    ledger = {}
    lines = content.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "\t" not in line:
            continue
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) < 3:
            continue
        code = parts[0]
        ledger[code] = {
            "code": code,
            "name": parts[1] if len(parts) > 1 else "",
            "business_name": ACCOUNT_MAP.get(code, parts[1] if len(parts) > 1 else ""),
            "opening_balance": clean_amount(parts[2]) if len(parts) > 2 else None,
            "current_debit": clean_amount(parts[3]) if len(parts) > 3 else None,
            "current_credit": clean_amount(parts[4]) if len(parts) > 4 else None,
            "closing_balance": clean_amount(parts[5]) if len(parts) > 5 else None,
        }
    return ledger


def parse_wldw(content: str) -> list:
    """解析往来单位档案 WLDW.TXT"""
    units = []
    lines = content.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "\t" not in line:
            continue
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) < 2:
            continue
        units.append({
            "code": parts[0],
            "name": parts[1] if len(parts) > 1 else "",
            "type": parts[2] if len(parts) > 2 else "",  # 股东/关联方/普通往来
        })
    return units


def parse_chxx(content: str) -> list:
    """解析存货信息 CHXX.TXT"""
    inventory = []
    lines = content.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "\t" not in line:
            continue
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) < 3:
            continue
        inventory.append({
            "code": parts[0],
            "name": parts[1] if len(parts) > 1 else "",
            "quantity": clean_amount(parts[2]) if len(parts) > 2 else None,
            "unit_price": clean_amount(parts[3]) if len(parts) > 3 else None,
            "amount": clean_amount(parts[4]) if len(parts) > 4 else None,
        })
    return inventory


def extract_risk_features(
    accounts: dict,
    ledger: dict,
    vouchers: list,
) -> dict:
    """
    从标准化数据中提取风险指标特征值
    """
    features = {}

    # 从账簿或科目中获取余额（优先使用期末余额）
    def get_balance(code: str) -> Optional[float]:
        source = ledger or accounts
        if code in source:
            return source[code].get("closing_balance")
        return None

    # 1. 库存现金（科目1001）
    features["cash_balance"] = get_balance("1001")

    # 2. 应收账款（1122）
    features["ar_balance"] = get_balance("1122")

    # 3. 应付账款（2201）
    features["ap_balance"] = get_balance("2201")

    # 4. 其他应收款（1221）
    features["other_ar_balance"] = get_balance("1221")

    # 5. 其他应付款（2241）
    features["other_ap_balance"] = get_balance("2241")

    # 6. 未分配利润（3131）
    features["retained_earnings"] = get_balance("3131")

    # 7. 资产总额（所有资产类科目之和，1开头科目）
    total_assets = 0.0
    for code, data in (ledger or accounts).items():
        if code.startswith("1") and data.get("closing_balance"):
            total_assets += abs(data["closing_balance"])
    features["total_assets"] = total_assets if total_assets > 0 else None

    return features


async def process_financial_file(
    file_id: int,
    file_path: str,
    file_type: str,
    company_id: int,
):
    """后台异步处理上传的财务文件"""
    from app.core.database import SessionLocal
    from app.models import FinancialData, RiskIndicator
    from app.schemas import RiskIndicatorCreate
    from app.services.risk_engine import calculate_risk_indicators

    db = SessionLocal()
    try:
        fd = db.query(FinancialData).filter(FinancialData.id == file_id).first()
        if not fd:
            return

        fd.status = "processing"
        db.commit()

        # 读取文件内容
        encodings = ["utf-8", "gbk", "gb2312", "utf-8-sig"]
        content = None
        for enc in encodings:
            try:
                with open(file_path, "r", encoding=enc, errors="replace") as f:
                    content = f.read()
                break
            except Exception:
                continue

        if content is None:
            fd.status = "error"
            fd.error_msg = "无法读取文件，请检查文件编码"
            db.commit()
            return

        # 根据文件类型解析
        parsed_data = None
        record_count = 0

        accounts_data = {}
        ledger_data = {}

        if file_type == "KJKM":
            parsed_data = parse_kjkm(content)
            record_count = len(parsed_data)
            accounts_data = parsed_data
        elif file_type == "JZPZ":
            parsed_data = parse_jzpz(content)
            record_count = len(parsed_data)
        elif file_type == "DZZB":
            parsed_data = parse_dzzb(content)
            record_count = len(parsed_data)
            ledger_data = parsed_data
        elif file_type == "WLDW":
            parsed_data = parse_wldw(content)
            record_count = len(parsed_data)
        elif file_type == "CHXX":
            parsed_data = parse_chxx(content)
            record_count = len(parsed_data)

        if parsed_data is not None:
            # 将解析结果JSON化保存
            result_path = file_path + ".json"
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(parsed_data, f, ensure_ascii=False, default=str)

        fd.status = "done"
        fd.record_count = record_count
        db.commit()
        logger.info(f"文件处理完成: {file_path}, 记录数: {record_count}")

        # ===== 自动生成风险指标 =====
        features = extract_risk_features(accounts_data, ledger_data, [])
        period = fd.period or ""

        # 构造风险指标数据（只填充能从财务数据自动提取的字段）
        risk_data = RiskIndicatorCreate(
            company_id=company_id,
            period=period,
            cash_balance=features.get("cash_balance"),
            retained_earnings=features.get("retained_earnings"),
            total_assets=features.get("total_assets"),
            # 其他字段默认（按期申报、无逾期、无暂估）
            tax_declared=True,
            overdue_count=0,
            has_year_end_estimated=False,
        )

        # 调用风险引擎计算等级
        risk_result = calculate_risk_indicators(risk_data)
        risk_dict = risk_data.model_dump()
        risk_dict.update(risk_result)

        # 判断该期间是否已有记录，有则更新
        existing = db.query(RiskIndicator).filter(
            RiskIndicator.company_id == company_id,
            RiskIndicator.period == period,
        ).first()

        if existing:
            for k, v in risk_dict.items():
                if hasattr(existing, k):
                    setattr(existing, k, v)
            logger.info(f"风险指标已更新: company={company_id}, period={period}")
        else:
            indicator = RiskIndicator(**risk_dict)
            db.add(indicator)
            logger.info(f"风险指标已生成: company={company_id}, period={period}")

        db.commit()

    except Exception as e:
        logger.error(f"文件处理异常: {file_path}, 错误: {e}")
        if 'fd' in dir() and fd:
            fd.status = "error"
            fd.error_msg = str(e)[:500]
            db.commit()
    finally:
        db.close()
