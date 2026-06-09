"""
CRM-интерфейс для команды:
- Список всех диалогов с фильтрами
- Просмотр полной истории сообщений
- Takeover: остановить бота, отвечать вручную
- Return to bot: вернуть диалог боту
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy import select, func, and_, or_, desc

from app.config import settings
from app.db import get_session
from app.models import User, Message, Event


router = APIRouter()


def check_auth(key: str) -> bool:
    return key == settings.ADMIN_DASHBOARD_KEY


@router.get("/crm", response_class=HTMLResponse)
async def crm_list(key: str = "", filter: str = "all", page: int = 0):
    if not check_auth(key):
        raise HTTPException(status_code=401, detail="Unauthorized")

    PAGE_SIZE = 50
    async with get_session() as session:
        stmt = select(User)

        if filter == "active":
            day_ago = datetime.utcnow() - timedelta(days=1)
            stmt = stmt.where(User.last_seen_at >= day_ago)
        elif filter == "purchased":
            stmt = stmt.where(User.purchased == True)
        elif filter == "takeover":
            stmt = stmt.where(User.human_takeover == True)
        elif filter == "stuck":
            day_ago = datetime.utcnow() - timedelta(days=1)
            stmt = stmt.where(and_(
                User.last_seen_at < day_ago,
                User.purchased == False,
            ))

        stmt = stmt.order_by(desc(User.last_seen_at)).offset(page * PAGE_SIZE).limit(PAGE_SIZE)
        users = (await session.execute(stmt)).scalars().all()

        counts = {}
        for f, cond in [
            ("all", None),
            ("active", User.last_seen_at >= datetime.utcnow() - timedelta(days=1)),
            ("purchased", User.purchased == True),
            ("takeover", User.human_takeover == True),
            ("stuck", and_(
                User.last_seen_at < datetime.utcnow() - timedelta(days=1),
                User.purchased == False,
            )),
        ]:
            q = select(func.count(User.id))
            if cond is not None:
                q = q.where(cond)
            counts[f] = (await session.execute(q)).scalar() or 0

    rows = ""
    for u in users:
        name = (u.first_name or "") + (" " + u.last_name if u.last_name else "")
        name = name.strip() or (u.username or f"id:{u.telegram_id}")
        username = f"@{u.username}" if u.username else ""

        badges = []
        if u.purchased:
            badges.append('<span class="badge badge-green">PAID</span>')
        if u.human_takeover:
            badges.append('<span class="badge badge-red">TAKEOVER</span>')
        if u.completed_at:
            badges.append('<span class="badge badge-blue">DONE</span>')
        badges_html = " ".join(badges)

        last_seen = u.last_seen_at.strftime("%d.%m %H:%M") if u.last_seen_at else "-"
        step = f"step {u.current_step}" if u.current_step >= 0 else "welcome"

        rows += f"""
        <tr onclick="window.location='/crm/chat?key={key}&uid={u.id}'">
          <td>{name}<br><small>{username}</small></td>
          <td class="mono">{last_seen}</td>
          <td>{step}</td>
          <td>{u.ab_group}</td>
          <td>{badges_html}</td>
        </tr>
        """

    filter_tabs = ""
    for f, label in [("all", "Все"), ("active", "Активные"), ("purchased", "Купили"),
                     ("takeover", "На руках"), ("stuck", "Застрявшие")]:
        active = " active" if filter == f else ""
        filter_tabs += f'<a href="/crm?key={key}&filter={f}" class="tab{active}">{label} ({counts[f]})</a>'

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>YouTrade CRM</title>
<style>
body{{font-family:system-ui,sans-serif;background:#08070c;color:#f0f0f5;margin:0;padding:20px}}
h1{{font-size:20px;margin:0 0 20px}}
.tabs{{display:flex;gap:4px;margin-bottom:16px;flex-wrap:wrap}}
.tab{{padding:6px 14px;background:#111118;border-radius:8px;text-decoration:none;color:#7a7a90;font-size:13px;border:1px solid rgba(255,255,255,0.05)}}
.tab.active{{background:#10b981;color:#08070c;font-weight:600}}
table{{width:100%;border-collapse:collapse;background:#111118;border-radius:12px;overflow:hidden}}
th,td{{padding:12px 14px;text-align:left;border-bottom:1px solid rgba(255,255,255,0.04);font-size:13px}}
th{{background:#0e0d14;font-size:11px;color:#7a7a90;text-transform:uppercase;letter-spacing:1px}}
tr:hover{{background:rgba(255,255,255,0.02);cursor:pointer}}
.mono{{font-family:'JetBrains Mono',monospace;color:#7a7a90}}
small{{color:#7a7a90}}
.badge{{display:inline-block;padding:2px 8px;border-radius:12px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px}}
.badge-green{{background:rgba(16,185,129,0.15);color:#10b981}}
.badge-red{{background:rgba(239,68,68,0.15);color:#ef4444}}
.badge-blue{{background:rgba(59,130,246,0.15);color:#3b82f6}}
a{{color:#10b981}}
</style>
</head>
<body>
<h1>YouTrade CRM</h1>
<div class="tabs">{filter_tabs}</div>
<table>
<thead><tr><th>Клиент</th><th>Последний раз</th><th>Этап</th><th>A/B</th><th>Статус</th></tr></thead>
<tbody>{rows if rows else '<tr><td colspan="5" style="color:#7a7a90;padding:40px;text-align:center">Нет диалогов</td></tr>'}</tbody>
</table>
<div style="margin-top:16px;text-align:center">
<a href="/admin?key={key}" style="font-size:13px">← Обычная статистика</a>
</div>
</body>
</html>
"""


@router.get("/crm/chat", response_class=HTMLResponse)
async def crm_chat(key: str = "", uid: int = 0):
    if not check_auth(key):
        raise HTTPException(status_code=401, detail="Unauthorized")

    async with get_session() as session:
        user = (await session.execute(select(User).where(User.id == uid))).scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404)

        messages = (await session.execute(
            select(Message).where(Message.user_id == uid)
            .order_by(Message.created_at).limit(200)
        )).scalars().all()

    name = (user.first_name or "") + (" " + user.last_name if user.last_name else "")
    name = name.strip() or (user.username or f"id:{user.telegram_id}")

    msgs_html = ""
    for m in messages:
        time_str = m.created_at.strftime("%d.%m %H:%M")
        if m.direction == "in":
            msgs_html += f"""
            <div class="msg msg-in">
              <div class="msg-bubble">{m.content.replace('<', '&lt;').replace('>', '&gt;')}</div>
              <div class="msg-meta">{time_str}</div>
            </div>
            """
        else:
            badge = "AI" if m.is_ai else "BOT"
            if "[HUMAN]" in m.content:
                badge = "👤 Менеджер"
                content = m.content.replace("[HUMAN] ", "")
            else:
                content = m.content
            msgs_html += f"""
            <div class="msg msg-out">
              <div class="msg-bubble">
                <div class="msg-badge">{badge}</div>
                {content.replace('<', '&lt;').replace('>', '&gt;')}
              </div>
              <div class="msg-meta">{time_str}</div>
            </div>
            """

    takeover_button = ""
    if user.human_takeover:
        takeover_button = f"""
        <div style="background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.2);border-radius:10px;padding:12px;margin-bottom:12px">
          <div style="color:#ef4444;font-weight:600;margin-bottom:4px">🔴 Бот выключен</div>
          <div style="font-size:12px;color:#7a7a90">Отвечает {user.takeover_by or 'оператор'} с {user.takeover_at.strftime('%d.%m %H:%M') if user.takeover_at else '—'}</div>
          <form method="post" action="/crm/return-bot" style="margin-top:8px">
            <input type="hidden" name="key" value="{key}">
            <input type="hidden" name="uid" value="{uid}">
            <button type="submit" style="padding:6px 14px;background:#3b82f6;color:#fff;border:none;border-radius:6px;font-size:12px;cursor:pointer">Вернуть боту</button>
          </form>
        </div>
        """
    else:
        takeover_button = f"""
        <form method="post" action="/crm/takeover" style="margin-bottom:12px">
          <input type="hidden" name="key" value="{key}">
          <input type="hidden" name="uid" value="{uid}">
          <button type="submit" style="width:100%;padding:10px;background:#ef4444;color:#fff;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer">🎙 Взять диалог на себя (остановить бота)</button>
        </form>
        """

    mark_purchased_button = ""
    if not user.purchased:
        mark_purchased_button = f"""
        <form method="post" action="/crm/mark-purchased" style="margin-bottom:12px">
          <input type="hidden" name="key" value="{key}">
          <input type="hidden" name="uid" value="{uid}">
          <button type="submit" style="width:100%;padding:10px;background:#10b981;color:#08070c;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer">✅ Отметить что купил (переключить в support)</button>
        </form>
        """

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Chat: {name}</title>
<style>
body{{font-family:system-ui,sans-serif;background:#08070c;color:#f0f0f5;margin:0;padding:20px;max-width:800px;margin:0 auto}}
h1{{font-size:18px;margin:0 0 4px}}
.sub{{color:#7a7a90;font-size:13px;margin-bottom:20px}}
.chat{{background:#111118;border-radius:12px;padding:16px;max-height:60vh;overflow-y:auto;margin-bottom:16px}}
.msg{{margin-bottom:12px;display:flex;flex-direction:column}}
.msg-in{{align-items:flex-start}}
.msg-out{{align-items:flex-end}}
.msg-bubble{{max-width:80%;padding:10px 14px;border-radius:14px;font-size:14px;line-height:1.5;white-space:pre-wrap}}
.msg-in .msg-bubble{{background:#1a1a24;color:#f0f0f5}}
.msg-out .msg-bubble{{background:rgba(16,185,129,0.1);color:#f0f0f5;border:1px solid rgba(16,185,129,0.15)}}
.msg-meta{{font-size:10px;color:#7a7a90;margin-top:4px}}
.msg-badge{{font-size:9px;color:#10b981;font-weight:600;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px}}
textarea{{width:100%;padding:12px;background:#111118;color:#f0f0f5;border:1px solid rgba(255,255,255,0.08);border-radius:10px;font-family:inherit;font-size:14px;min-height:80px;resize:vertical}}
textarea:focus{{outline:none;border-color:#10b981}}
.send-btn{{padding:12px 24px;background:#10b981;color:#08070c;border:none;border-radius:8px;font-weight:600;cursor:pointer;margin-top:8px}}
.back{{color:#7a7a90;text-decoration:none;font-size:13px}}
.info{{font-size:12px;color:#7a7a90;margin-bottom:16px}}
</style>
</head>
<body>
<a href="/crm?key={key}" class="back">← К списку диалогов</a>
<h1>{name}</h1>
<div class="sub">@{user.username or '—'} · id:{user.telegram_id} · A/B группа: {user.ab_group}</div>

<div class="info">
  Этап: {'шаг ' + str(user.current_step) if user.current_step >= 0 else 'welcome-флоу'}
  · {'✅ куплено' if user.purchased else '❌ не купил'}
  · Источник: {user.source or '—'}
</div>

{takeover_button}
{mark_purchased_button}

<div class="chat" id="chat">{msgs_html}</div>

<form method="post" action="/crm/send">
  <input type="hidden" name="key" value="{key}">
  <input type="hidden" name="uid" value="{uid}">
  <textarea name="text" placeholder="{'Отправить сообщение клиенту от имени менеджера...' if user.human_takeover else 'Взять диалог на себя чтобы отправлять сообщения'}"{'  disabled' if not user.human_takeover else ''}></textarea>
  <button type="submit" class="send-btn" {'disabled' if not user.human_takeover else ''}>Отправить</button>
</form>

<script>
var chat = document.getElementById('chat');
chat.scrollTop = chat.scrollHeight;
</script>
</body>
</html>
"""


@router.post("/crm/takeover")
async def crm_takeover(key: str = Form(...), uid: int = Form(...)):
    if not check_auth(key):
        raise HTTPException(status_code=401)
    async with get_session() as session:
        user = (await session.execute(select(User).where(User.id == uid))).scalar_one_or_none()
        if user:
            user.human_takeover = True
            user.takeover_at = datetime.utcnow()
            user.takeover_by = "manager"
            session.add(Event(user_id=uid, event_type="human_takeover"))
    return RedirectResponse(f"/crm/chat?key={key}&uid={uid}", status_code=303)


@router.post("/crm/return-bot")
async def crm_return_bot(key: str = Form(...), uid: int = Form(...)):
    if not check_auth(key):
        raise HTTPException(status_code=401)
    async with get_session() as session:
        user = (await session.execute(select(User).where(User.id == uid))).scalar_one_or_none()
        if user:
            user.human_takeover = False
            user.takeover_by = None
            user.takeover_at = None
            session.add(Event(user_id=uid, event_type="returned_to_bot"))
    return RedirectResponse(f"/crm/chat?key={key}&uid={uid}", status_code=303)


@router.post("/crm/mark-purchased")
async def crm_mark_purchased(key: str = Form(...), uid: int = Form(...)):
    if not check_auth(key):
        raise HTTPException(status_code=401)
    async with get_session() as session:
        user = (await session.execute(select(User).where(User.id == uid))).scalar_one_or_none()
        if user:
            user.purchased = True
            user.purchase_at = datetime.utcnow()
            user.current_step = 0
            session.add(Event(user_id=uid, event_type="marked_purchased_manually"))
    return RedirectResponse(f"/crm/chat?key={key}&uid={uid}", status_code=303)


@router.post("/crm/send")
async def crm_send_message(key: str = Form(...), uid: int = Form(...), text: str = Form(...)):
    if not check_auth(key):
        raise HTTPException(status_code=401)

    from app.bot import bot
    from app.models import Message

    async with get_session() as session:
        user = (await session.execute(select(User).where(User.id == uid))).scalar_one_or_none()
        if not user or not user.human_takeover:
            raise HTTPException(status_code=400, detail="Takeover not active")

        try:
            await bot.send_message(chat_id=user.telegram_id, text=text)
            session.add(Message(
                user_id=uid, direction="out", content=f"[HUMAN] {text}",
                step=user.current_step, is_ai=False
            ))
            session.add(Event(user_id=uid, event_type="human_message_sent"))
        except Exception as e:
            print(f"[crm send] error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(f"/crm/chat?key={key}&uid={uid}", status_code=303)
