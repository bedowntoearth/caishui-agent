from typing import Optional, Any
from datetime import datetime
from pydantic import BaseModel, field_validator, model_validator
import re


# ====== 通用响应结构 ======
class Response(BaseModel):
    code: int = 200
    message: str = "success"
    data: Optional[Any] = None


class PageInfo(BaseModel):
    page: int = 1
    page_size: int = 20
    total: int = 0
    items: list = []


# ====== 管理员认证相关 ======
class LoginRequest(BaseModel):
    username: str
    password: str
    captcha_key: str
    captcha_code: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_info: dict


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class CaptchaResponse(BaseModel):
    key: str
    image: str  # base64


# ====== 系统用户 ======
class SysUserCreate(BaseModel):
    username: str
    password: str
    confirm_password: str
    real_name: str
    phone: str
    role: str = "operator"
    remark: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(r"^1[3-9]\d{9}$", v):
            raise ValueError("手机号格式不正确")
        return v

    @model_validator(mode="after")
    def check_passwords(self):
        if self.password != self.confirm_password:
            raise ValueError("两次密码不一致")
        if len(self.password) < 8:
            raise ValueError("密码长度至少8位")
        return self


class SysUserUpdate(BaseModel):
    real_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    remark: Optional[str] = None


class SysUserOut(BaseModel):
    id: int
    username: str
    real_name: str
    phone: str
    role: str
    status: str
    remark: Optional[str]
    last_login_ip: Optional[str]
    last_login_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


# ====== 企业信息 ======
class CompanyCreate(BaseModel):
    name: str
    credit_code: str
    legal_person: str
    contact_name: str
    contact_phone: str
    sign_date: Optional[datetime] = None
    expire_date: Optional[datetime] = None
    industry: Optional[str] = None
    taxpayer_type: str = "small"
    tax_authority: Optional[str] = None

    @field_validator("credit_code")
    @classmethod
    def validate_credit_code(cls, v: str) -> str:
        if len(v) != 18:
            raise ValueError("统一社会信用代码必须为18位")
        return v.upper()

    @field_validator("contact_phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(r"^1[3-9]\d{9}$", v):
            raise ValueError("手机号格式不正确")
        return v


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    legal_person: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    sign_date: Optional[datetime] = None
    expire_date: Optional[datetime] = None
    industry: Optional[str] = None
    taxpayer_type: Optional[str] = None
    tax_authority: Optional[str] = None
    status: Optional[str] = None


class CompanyOut(BaseModel):
    id: int
    name: str
    credit_code: str
    legal_person: str
    contact_name: str
    contact_phone: str
    sign_date: Optional[datetime]
    expire_date: Optional[datetime]
    industry: Optional[str]
    taxpayer_type: str
    tax_authority: Optional[str]
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CompanyMiniOut(BaseModel):
    """小程序端展示（部分字段脱敏）"""
    id: int
    name: str
    credit_code_masked: str  # 前6后4，中间*
    legal_person: str
    industry: Optional[str]
    status: str
    sign_date: Optional[datetime]
    expire_date: Optional[datetime]
    days_remaining: Optional[int]  # 剩余天数

    model_config = {"from_attributes": True}


# ====== 风险指标 ======
class RiskIndicatorCreate(BaseModel):
    company_id: int
    period: str  # YYYY-MM
    # 指标1
    tax_declared: bool = True
    overdue_count: int = 0
    # 指标2
    cash_balance: Optional[float] = None
    # 指标3
    ar_overdue_months: Optional[float] = None
    ap_overdue_months: Optional[float] = None
    other_ar_months: Optional[float] = None
    other_ap_months: Optional[float] = None
    # 指标4
    retained_earnings: Optional[float] = None
    total_assets: Optional[float] = None
    # 指标5
    shareholder_loan_months: Optional[float] = None
    # 指标6
    estimated_entry_months: Optional[float] = None
    has_year_end_estimated: bool = False


class RiskIndicatorOut(BaseModel):
    id: int
    company_id: int
    period: str
    tax_declared: bool
    overdue_count: int
    cash_balance: Optional[float]
    risk1_level: str
    risk1_reason: Optional[str]
    ar_overdue_months: Optional[float]
    ap_overdue_months: Optional[float]
    other_ar_months: Optional[float]
    other_ap_months: Optional[float]
    risk2_level: str
    risk2_reason: Optional[str]
    risk3_level: str
    risk3_reason: Optional[str]
    retained_earnings: Optional[float]
    total_assets: Optional[float]
    risk4_level: str
    risk4_reason: Optional[str]
    shareholder_loan_months: Optional[float]
    risk5_level: str
    risk5_reason: Optional[str]
    estimated_entry_months: Optional[float]
    has_year_end_estimated: bool
    risk6_level: str
    risk6_reason: Optional[str]
    health_score: Optional[float]
    updated_at: datetime

    model_config = {"from_attributes": True}


# ====== 微信小程序登录 ======
class WxLoginRequest(BaseModel):
    code: str           # wx.login() 获取的code
    encrypted_data: str  # 加密手机号数据
    iv: str             # 加密向量


class WxLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    company_id: Optional[int] = None
    is_matched: bool = False


# ====== AI评估 ======
class AiEvalRequest(BaseModel):
    risk_index: int  # 1-6
    company_id: int


class AiReportOut(BaseModel):
    id: int
    risk_index: int
    report_content: str
    created_at: datetime

    model_config = {"from_attributes": True}
