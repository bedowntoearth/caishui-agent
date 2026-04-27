"""图形验证码生成与校验"""
import uuid
import base64
import io
import random
import string
from captcha.image import ImageCaptcha
from app.core.redis import get_redis

CAPTCHA_EXPIRE = 300  # 5分钟过期
CAPTCHA_PREFIX = "captcha:"


def generate_captcha_code(length: int = 4) -> str:
    chars = string.digits + string.ascii_uppercase
    chars = chars.replace("0", "").replace("O", "").replace("I", "").replace("1", "")
    return "".join(random.choices(chars, k=length))


async def create_captcha() -> dict:
    """生成验证码，返回key和base64图片"""
    code = generate_captcha_code()
    key = str(uuid.uuid4())

    image = ImageCaptcha(width=120, height=40, font_sizes=(30,))
    data = image.generate(code)
    img_bytes = data.read()
    img_b64 = base64.b64encode(img_bytes).decode()

    redis = await get_redis()
    await redis.setex(f"{CAPTCHA_PREFIX}{key}", CAPTCHA_EXPIRE, code.upper())

    return {"key": key, "image": f"data:image/png;base64,{img_b64}"}


async def verify_captcha(key: str, code: str) -> bool:
    """校验验证码（一次性）"""
    redis = await get_redis()
    stored = await redis.get(f"{CAPTCHA_PREFIX}{key}")
    if not stored:
        return False
    await redis.delete(f"{CAPTCHA_PREFIX}{key}")
    return stored.upper() == code.upper()
