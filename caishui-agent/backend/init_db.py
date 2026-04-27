"""数据库初始化脚本，创建初始超级管理员账号"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import Base, engine, SessionLocal
from app.core.security import get_password_hash
from app.models import SysUser, UserRole, UserStatus
import app.models  # noqa


def init_db():
    print("正在初始化数据库...")
    Base.metadata.create_all(bind=engine)
    print("✅ 数据库表已创建")

    db = SessionLocal()
    try:
        # 检查是否已有超级管理员
        existing = db.query(SysUser).filter(SysUser.role == UserRole.super_admin).first()
        if existing:
            print(f"⚠️  超级管理员已存在: {existing.username}")
            return

        admin = SysUser(
            username="admin",
            password_hash=get_password_hash("Admin@2024!"),
            real_name="超级管理员",
            phone="13800000000",
            role=UserRole.super_admin,
            status=UserStatus.active,
            remark="系统初始管理员",
        )
        db.add(admin)
        db.commit()
        print("✅ 超级管理员创建成功")
        print("   用户名: admin")
        print("   密码: Admin@2024!")
        print("   ⚠️  请登录后立即修改默认密码！")
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
