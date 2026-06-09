"""
FastAPI приложение — принимает webhooks от Telegram и WhatsApp (Botcorp).
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from typing import Optional

from app.config import settings
from app.db import init_db, close_db, get_session
from app.bot import process_update
from app.admin import admin_dashboard
from app.crm import router as crm_router
from app.models import Event, User
from app.whatsapp_bot import handle_wa_message
from sqlalchemy import select


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    print("[startup] Database initialized")
    yield
    await close_db()


app = FastAPI(lifespan=lifespan)
app.include_router(crm_router)


# ─── Telegram webhook ─────────────────────────────────────────────────────────

@app.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None),
):
    if x_telegram_bot_api_secret_token != settings.TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid secret token")

    try:
        update_dict = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    await process_update(update_dict)
    return JSONResponse({"ok": True})


# ─── WhatsApp (Botcorp) webhook ───────────────────────────────────────────────

@app.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    """
    Принимает входящие сообщения от Botcorp.
    Этот URL нужно указать в настройках канала в личном кабинете Botcorp:
      https://bot.youtrade.kz/whatsapp/webhook
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    print(f"[whatsapp webhook] payload: {payload}")
    await handle_wa_message(payload)
    return JSONResponse({"ok": True})


@app.get("/whatsapp/webhook")
async def whatsapp_webhook_verify(request: Request):
    """
    GET-запрос используется Botcorp для верификации вебхука.
    Возвращаем 200 OK.
    """
    return JSONResponse({"ok": True, "status": "webhook active"})


# ─── Служебные эндпоинты ──────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/admin", response_class=HTMLResponse)
async def admin(key: str = ""):
    if key != settings.ADMIN_DASHBOARD_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return await admin_dashboard()


@app.get("/pay")
async def pay_redirect(uid: int = 0, plan: str = ""):
    """
    Редирект на страницу оплаты с логированием клика.
    Бот даёт ссылку вида: /pay?uid=123&plan=2step_5k
    Мы логируем клик и редиректим на реальную оплату.
    """
    async with get_session() as session:
        if uid:
            user = (await session.execute(select(User).where(User.id == uid))).scalar_one_or_none()
            if user:
                session.add(Event(
                    user_id=user.id,
                    event_type="clicked_payment_link",
                    payload=plan,
                ))

    return RedirectResponse(url=settings.CHALLENGE_URL, status_code=302)
