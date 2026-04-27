# 财税智能体系统 - 部署与开发文档

## 项目概述

财税智能体系统，为中小企业提供财税风险量化评估与AI智能解读服务。

### 技术栈
- **后端**：Python 3.11 + FastAPI + SQLAlchemy + MySQL + Redis
- **管理端**：Jinja2 模板 + Bootstrap 5（内嵌于后端服务）
- **用户端**：微信小程序（原生框架）

---

## 目录结构

```
caishui-agent/
├── backend/                    # 后端服务
│   ├── app/
│   │   ├── __init__.py         # FastAPI 应用入口
│   │   ├── api/v1/             # API路由
│   │   │   ├── auth.py         # 认证（登录/注册/刷新token）
│   │   │   ├── users.py        # 用户管理
│   │   │   ├── companies.py    # 企业管理 + 数据上传
│   │   │   ├── risk_indicators.py  # 风险指标CRUD
│   │   │   ├── miniapp.py      # 小程序专用接口
│   │   │   └── admin_pages.py  # 管理端页面路由
│   │   ├── core/
│   │   │   ├── config.py       # 环境变量配置
│   │   │   ├── database.py     # 数据库连接
│   │   │   ├── redis.py        # Redis连接
│   │   │   ├── security.py     # JWT + 密码加密
│   │   │   └── logger.py       # 日志配置
│   │   ├── models/             # SQLAlchemy数据库模型
│   │   ├── schemas/            # Pydantic请求/响应模型
│   │   ├── services/
│   │   │   ├── risk_engine.py  # 风险指标计算引擎
│   │   │   ├── ai_service.py   # AI大模型评估服务
│   │   │   └── wechat_service.py  # 微信登录服务
│   │   ├── utils/              # 工具函数
│   │   └── data_pipeline/
│   │       └── etl.py          # TXT数据解析清洗
│   ├── templates/admin/        # 管理端Jinja2模板
│   │   ├── login.html          # 登录页
│   │   ├── layout.html         # 侧边栏布局
│   │   ├── dashboard.html      # 仪表板
│   │   ├── companies.html      # 企业列表
│   │   ├── company_detail.html # 企业详情
│   │   ├── users.html          # 用户管理
│   │   └── risk_indicators.html  # 风险指标管理
│   ├── static/                 # 静态资源（CSS/JS/图片）
│   ├── requirements.txt        # Python依赖
│   ├── .env.example            # 环境变量示例
│   ├── init_db.py              # 数据库初始化脚本
│   └── run.py                  # 启动入口
│
└── miniprogram/                # 微信小程序
    ├── app.js                  # 全局入口（token检查/用户信息）
    ├── app.json                # 全局配置（页面路由/导航栏）
    ├── app.wxss                # 全局样式
    ├── pages/
    │   ├── login/              # 登录页（手机号+验证码）
    │   ├── index/              # 首页（企业概览）
    │   ├── risk/               # 风险指标列表
    │   └── ai-eval/            # AI风险评估详情
    ├── utils/
    │   ├── request.js          # HTTP请求封装
    │   └── util.js             # 工具函数
    ├── project.config.json     # 小程序配置
    └── sitemap.json
```

---

## 快速启动

### 1. 准备环境

```bash
# 要求 Python 3.10+
python --version

# 安装依赖
cd backend
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# 复制示例文件
cp .env.example .env

# 编辑 .env，填写：
# - 数据库连接信息
# - Redis连接信息
# - 微信小程序 AppID 和 Secret
# - AI大模型 API Key
```

### 3. 初始化数据库

```bash
# 确保 MySQL 已创建数据库
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS caishui_agent CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 运行初始化脚本（建表 + 创建管理员账号）
python init_db.py
```

### 4. 启动服务

```bash
python run.py
# 或使用 uvicorn
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### 5. 访问管理后台

浏览器打开：`http://localhost:8000/admin/login`

默认管理员账号：
- 手机号：`13800000000`（或 `.env` 中配置的 `ADMIN_PHONE`）
- 密码：`Admin@2024!`（或 `.env` 中配置的 `ADMIN_PASSWORD`）

### 6. API文档

- Swagger UI：`http://localhost:8000/api/docs`
- ReDoc：`http://localhost:8000/api/redoc`

---

## 微信小程序配置

### 1. 修改服务器地址

打开 `miniprogram/utils/request.js`，将 `BASE_URL` 改为实际服务器地址：

```js
const BASE_URL = 'https://your-domain.com';  // 生产环境需HTTPS
```

### 2. 配置 AppID

打开 `miniprogram/project.config.json`，将 `appid` 改为实际的小程序 AppID。

### 3. 微信开发者工具导入

- 打开微信开发者工具
- 选择「导入项目」
- 目录选择 `miniprogram/`
- 填写 AppID

---

## 核心 API 说明

### 管理端认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/admin/login` | 管理员账号密码登录 |
| POST | `/api/v1/auth/refresh` | 刷新访问令牌 |

### 企业管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/companies` | 企业列表（支持分页/搜索/风险筛选） |
| POST | `/api/v1/companies` | 新增企业 |
| PUT | `/api/v1/companies/{id}` | 修改企业信息 |
| DELETE | `/api/v1/companies/{id}` | 删除企业 |
| POST | `/api/v1/companies/{id}/upload` | 上传TXT财税数据文件 |
| POST | `/api/v1/companies/{id}/ai-evaluate` | 触发AI综合评估 |

### 风险指标

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/risk-indicators` | 指标列表（按企业/等级筛选） |
| POST | `/api/v1/risk-indicators` | 手动录入指标 |
| PUT | `/api/v1/risk-indicators/{id}` | 修改指标 |
| DELETE | `/api/v1/risk-indicators/{id}` | 删除指标 |

### 小程序端

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/miniapp/login` | 微信授权登录 |
| POST | `/api/v1/miniapp/bind-phone` | 绑定手机号 |
| GET | `/api/v1/miniapp/company/info` | 获取绑定企业信息 |
| GET | `/api/v1/miniapp/company/risk-indicators` | 获取风险指标列表 |
| POST | `/api/v1/miniapp/ai-evaluate` | 触发AI风险评估 |

---

## TXT 数据格式说明

系统支持解析多种异构TXT格式，ETL管道会自动识别以下模式：

### 格式1：键值对
```
应收账款周转天数: 182天
资产负债率: 78.5%
净利润: -120万元
```

### 格式2：表格式
```
指标名称    数值      单位
应收账款    182       天
净利润      -120      万元
```

### 格式3：段落描述
```
【财务分析】
本期应收账款周转天数为182天，较上期增加35天，回款速度明显放缓。
资产负债率达78.5%，超过行业均值65%的警戒线。
```

---

## 风险等级定义

| 等级 | 代码 | 说明 |
|------|------|------|
| 正常 | normal | 指标在合理范围内 |
| 提醒 | remind | 轻微偏离，需关注 |
| 预警 | warning | 明显异常，需处理 |
| 重大风险 | major | 严重问题，须立即处理 |

---

## 生产部署

### 推荐方案：Nginx + Gunicorn

```nginx
# nginx.conf
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location /static/ {
        alias /app/caishui-agent/backend/static/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }
}
```

```bash
# 使用 gunicorn 启动
pip install gunicorn
gunicorn app:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

---

## 注意事项

1. **微信小程序需要HTTPS**：生产环境必须配置SSL证书
2. **AI API Key**：支持 OpenAI 兼容接口（可替换为国内大模型如智谱/通义/文心）
3. **数据库备份**：建议配置 MySQL 定期备份
4. **Redis持久化**：生产环境建议开启 AOF 持久化
