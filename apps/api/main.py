from __future__ import annotations

from fastapi import FastAPI, Request, HTTPException
from aiogram.types import Update

from daily_checkin.config import settings
from daily_checkin.telegram.bot import create_bot, create_dispatcher
from daily_checkin.telegram.handlers import router

app = FastAPI()

bot = create_bot()
dp = create_dispatcher()
dp.include_router(router)


@app.on_event("startup")
async def on_startup():
    if settings.public_base_url:
        await bot.set_webhook(
            url=f"{settings.public_base_url}/webhook",
            secret_token=settings.webhook_secret,
        )


@app.post("/webhook")
async def webhook(request: Request):
    if settings.webhook_secret:
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if secret != settings.webhook_secret:
            raise HTTPException(status_code=403, detail="Invalid secret token")

    update = Update.model_validate(await request.json())
    await dp.feed_update(bot, update)
    return {"ok": True}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}