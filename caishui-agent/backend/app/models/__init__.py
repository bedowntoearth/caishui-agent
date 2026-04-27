from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, Text,
    ForeignKey, Index, Enum as SAEnum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
import enum


class UserRole(str, enum.Enum):
    super_admin = "super_admin"
    admin = "admin"
    operator = "operator"
    analyst = "analyst"


class UserStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"


class SysUser(Base):
    """系统用户（管理端运营人员）"""
    __tablename__ = "sys_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, comment="用户名")
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="密码哈希")
    real_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="真实姓名")
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, comment="手机号")
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), default=UserRole.operator, comment="角色")
    status: Mapped[UserStatus] = mapped_column(SAEnum(UserStatus), default=UserStatus.active, comment="状态")
    remark: Mapped[Optional[str]] = mapped_column(String(200), comment="备注")
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(50), comment="最近登录IP")
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="最近登录时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    login_logs: Mapped[list["LoginLog"]] = relationship("LoginLog", back_populates="user")

    __table_args__ = (
        Index("idx_sys_users_phone", "phone"),
        Index("idx_sys_users_role", "role"),
    )


class TaxpayerType(str, enum.Enum):
    general = "general"      # 一般纳税人
    small = "small"          # 小规模纳税人


class CompanyStatus(str, enum.Enum):
    active = "active"        # 服务中
    expired = "expired"      # 已到期


class Company(Base):
    """代账企业信息"""
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="企业全称")
    credit_code: Mapped[str] = mapped_column(String(18), unique=True, nullable=False, comment="统一社会信用代码")
    legal_person: Mapped[str] = mapped_column(String(50), nullable=False, comment="法定代表人")
    contact_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="企业联系人姓名")
    contact_phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, comment="联系人手机号（跨端唯一主键）")
    sign_date: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="签约日期")
    expire_date: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="服务到期日")
    industry: Mapped[Optional[str]] = mapped_column(String(100), comment="所属行业分类")
    taxpayer_type: Mapped[TaxpayerType] = mapped_column(SAEnum(TaxpayerType), default=TaxpayerType.small, comment="纳税人性质")
    tax_authority: Mapped[Optional[str]] = mapped_column(String(100), comment="所属主管税务机关")
    status: Mapped[CompanyStatus] = mapped_column(SAEnum(CompanyStatus), default=CompanyStatus.active, comment="服务状态")
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("sys_users.id"), comment="创建人")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    risk_indicators: Mapped[list["RiskIndicator"]] = relationship("RiskIndicator", back_populates="company")
    financial_data: Mapped[list["FinancialData"]] = relationship("FinancialData", back_populates="company")
    wx_users: Mapped[list["WxUser"]] = relationship("WxUser", back_populates="company")

    __table_args__ = (
        Index("idx_companies_credit_code", "credit_code"),
        Index("idx_companies_contact_phone", "contact_phone"),
        Index("idx_companies_status", "status"),
    )


class RiskLevel(str, enum.Enum):
    normal = "normal"          # 正常（绿色）
    remind = "remind"          # 提醒（黄色）
    warning = "warning"        # 预警（橙色）
    major_risk = "major_risk"  # 重大风险（红色）


class RiskIndicator(Base):
    """六项风险指标"""
    __tablename__ = "risk_indicators"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False)
    period: Mapped[str] = mapped_column(String(20), nullable=False, comment="统计期数，如2026-03")

    # 指标1：是否按期申报
    tax_declared: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否按期申报")
    overdue_count: Mapped[int] = mapped_column(Integer, default=0, comment="逾期次数")
    risk1_level: Mapped[RiskLevel] = mapped_column(SAEnum(RiskLevel), default=RiskLevel.normal)
    risk1_reason: Mapped[Optional[str]] = mapped_column(String(500), comment="触发原因")

    # 指标2：库存现金是否异常
    cash_balance: Mapped[Optional[float]] = mapped_column(Float, comment="库存现金余额")
    risk2_level: Mapped[RiskLevel] = mapped_column(SAEnum(RiskLevel), default=RiskLevel.normal)
    risk2_reason: Mapped[Optional[str]] = mapped_column(String(500))

    # 指标3：往来款项是否长期挂账（月数）
    ar_overdue_months: Mapped[Optional[float]] = mapped_column(Float, comment="应收账款最长挂账月数")
    ap_overdue_months: Mapped[Optional[float]] = mapped_column(Float, comment="应付账款最长挂账月数")
    other_ar_months: Mapped[Optional[float]] = mapped_column(Float, comment="其他应收款最长挂账月数")
    other_ap_months: Mapped[Optional[float]] = mapped_column(Float, comment="其他应付款最长挂账月数")
    risk3_level: Mapped[RiskLevel] = mapped_column(SAEnum(RiskLevel), default=RiskLevel.normal)
    risk3_reason: Mapped[Optional[str]] = mapped_column(String(500))

    # 指标4：未分配利润是否异常
    retained_earnings: Mapped[Optional[float]] = mapped_column(Float, comment="未分配利润")
    total_assets: Mapped[Optional[float]] = mapped_column(Float, comment="资产总额")
    risk4_level: Mapped[RiskLevel] = mapped_column(SAEnum(RiskLevel), default=RiskLevel.normal)
    risk4_reason: Mapped[Optional[str]] = mapped_column(String(500))

    # 指标5：股东及关联方占款
    shareholder_loan_months: Mapped[Optional[float]] = mapped_column(Float, comment="股东及关联方借款挂账月数")
    risk5_level: Mapped[RiskLevel] = mapped_column(SAEnum(RiskLevel), default=RiskLevel.normal)
    risk5_reason: Mapped[Optional[str]] = mapped_column(String(500))

    # 指标6：暂估入账是否异常
    estimated_entry_months: Mapped[Optional[float]] = mapped_column(Float, comment="暂估挂账月数")
    has_year_end_estimated: Mapped[bool] = mapped_column(Boolean, default=False, comment="12月份是否存在暂估未冲销")
    risk6_level: Mapped[RiskLevel] = mapped_column(SAEnum(RiskLevel), default=RiskLevel.normal)
    risk6_reason: Mapped[Optional[str]] = mapped_column(String(500))

    # 综合健康度得分（0-100）
    health_score: Mapped[Optional[float]] = mapped_column(Float, comment="综合健康度得分")

    updated_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("sys_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company: Mapped["Company"] = relationship("Company", back_populates="risk_indicators")
    ai_reports: Mapped[list["AiReport"]] = relationship("AiReport", back_populates="risk_indicator")

    __table_args__ = (
        Index("idx_risk_indicators_company_period", "company_id", "period"),
    )


class FinancialDataType(str, enum.Enum):
    dzzb = "DZZB"   # 电子账簿
    kjkm = "KJKM"   # 会计科目
    jzpz = "JZPZ"   # 记账凭证
    wldw = "WLDW"   # 往来单位档案
    chxx = "CHXX"   # 存货信息


class FinancialData(Base):
    """财务数据文件上传记录"""
    __tablename__ = "financial_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False)
    file_type: Mapped[FinancialDataType] = mapped_column(SAEnum(FinancialDataType), comment="文件类型")
    file_name: Mapped[str] = mapped_column(String(200), comment="原始文件名")
    file_path: Mapped[str] = mapped_column(String(500), comment="存储路径")
    period: Mapped[Optional[str]] = mapped_column(String(20), comment="数据期间")
    status: Mapped[str] = mapped_column(String(20), default="pending", comment="处理状态: pending/processing/done/error")
    error_msg: Mapped[Optional[str]] = mapped_column(Text, comment="错误信息")
    record_count: Mapped[Optional[int]] = mapped_column(Integer, comment="有效记录数")
    uploaded_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("sys_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company: Mapped["Company"] = relationship("Company", back_populates="financial_data")

    __table_args__ = (
        Index("idx_financial_data_company", "company_id", "file_type"),
    )


class AiReport(Base):
    """AI风险评估报告"""
    __tablename__ = "ai_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False)
    risk_indicator_id: Mapped[int] = mapped_column(Integer, ForeignKey("risk_indicators.id"), nullable=False)
    risk_index: Mapped[int] = mapped_column(Integer, comment="风险指标编号 1-6")
    wx_openid: Mapped[Optional[str]] = mapped_column(String(100), comment="请求用户openid")
    prompt_snapshot: Mapped[Optional[str]] = mapped_column(Text, comment="Prompt快照")
    report_content: Mapped[Optional[str]] = mapped_column(Text, comment="AI生成报告内容")
    token_used: Mapped[Optional[int]] = mapped_column(Integer, comment="消耗token数")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    risk_indicator: Mapped["RiskIndicator"] = relationship("RiskIndicator", back_populates="ai_reports")

    __table_args__ = (
        Index("idx_ai_reports_company", "company_id"),
        Index("idx_ai_reports_indicator", "risk_indicator_id", "risk_index"),
    )


class WxUser(Base):
    """微信小程序用户"""
    __tablename__ = "wx_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    openid: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, comment="微信openid")
    unionid: Mapped[Optional[str]] = mapped_column(String(100), comment="微信unionid")
    phone: Mapped[Optional[str]] = mapped_column(String(20), comment="手机号")
    company_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("companies.id"), comment="关联企业ID")
    session_key: Mapped[Optional[str]] = mapped_column(String(100), comment="微信session_key（加密存储）")
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company: Mapped[Optional["Company"]] = relationship("Company", back_populates="wx_users")

    __table_args__ = (
        Index("idx_wx_users_phone", "phone"),
        Index("idx_wx_users_company", "company_id"),
    )


class LoginLog(Base):
    """登录审计日志"""
    __tablename__ = "login_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("sys_users.id"), nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50))
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))
    login_result: Mapped[str] = mapped_column(String(20), default="success", comment="success/fail")
    fail_reason: Mapped[Optional[str]] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["SysUser"] = relationship("SysUser", back_populates="login_logs")

    __table_args__ = (
        Index("idx_login_logs_user", "user_id"),
        Index("idx_login_logs_created", "created_at"),
    )
