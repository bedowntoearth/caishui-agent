"""微信小程序相关服务"""
import httpx
import json
import base64
from Crypto.Cipher import AES
from app.core.config import settings


WECHAT_CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


async def code2session(code: str) -> dict:
    """通过code获取openid和session_key"""
    params = {
        "appid": settings.WECHAT_APPID,
        "secret": settings.WECHAT_SECRET,
        "js_code": code,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(WECHAT_CODE2SESSION_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        if "errcode" in data and data["errcode"] != 0:
            raise ValueError(f"微信code2session失败: {data.get('errmsg', '')}")
        return data


def decrypt_phone_number(session_key: str, encrypted_data: str, iv: str) -> str:
    """解密微信手机号加密数据"""
    session_key_bytes = base64.b64decode(session_key)
    encrypted_data_bytes = base64.b64decode(encrypted_data)
    iv_bytes = base64.b64decode(iv)

    cipher = AES.new(session_key_bytes, AES.MODE_CBC, iv_bytes)
    decrypted = cipher.decrypt(encrypted_data_bytes)

    # PKCS7 去填充
    pad = decrypted[-1]
    decrypted = decrypted[:-pad]

    result = json.loads(decrypted.decode("utf-8"))
    return result.get("phoneNumber", "")
