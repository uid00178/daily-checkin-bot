from __future__ import annotations

import asyncio
import contextlib

from fastapi import FastAPI, Request, HTTPException
from aiogram.types import Update

from daily_checkin.config import settings
from daily_checkin.telegram.bot import create_bot, create_dispatcher
from daily_checkin.telegram.handlers import router

app = FastAPI()

bot = create_bot()
dp = create_dispatcher()
dp.include_router(router)
polling_task: asyncio.Task | None = None


@app.on_event("startup")
async def on_startup():
    if settings.public_base_url:
        await bot.set_webhook(
            url=f"{settings.public_base_url}/webhook",
            secret_token=settings.webhook_secret,
        )
    else:
        # Polling mode for local/dev when no public URL is configured.
        await bot.delete_webhook(drop_pending_updates=True)
        global polling_task
        polling_task = asyncio.create_task(dp.start_polling(bot))


@app.on_event("shutdown")
async def on_shutdown():
    if polling_task:
        polling_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await polling_task


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
