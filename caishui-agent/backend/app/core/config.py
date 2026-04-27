from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # 应用配置
    APP_NAME: str = "财税智能体系统"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:8080"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8080"

    # 数据库配置
    DATABASE_URL: str = "mysql+pymysql://root:password@localhost:3306/caishui_agent"

    # Redis配置
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT配置
    SECRET_KEY: str = "change-this-secret-key-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # 微信小程序配置
    WECHAT_APPID: str = ""
    WECHAT_SECRET: str = ""

    # 大模型API配置
    AI_API_KEY: str = ""
    AI_API_BASE: str = "https://api.openai.com/v1"
    AI_MODEL: str = "gpt-4o-mini"
    AI_MAX_TOKENS: int = 2000
    AI_TEMPERATURE: float = 0.7

    @property
    def CORS_ORIGINS_LIST(self) -> List[str]:
        # 优先使用 CORS_ORIGINS，否则使用 ALLOWED_ORIGINS
        origins = self.CORS_ORIGINS if self.CORS_ORIGINS else self.ALLOWED_ORIGINS
        return [o.strip() for o in origins.split(",")]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
