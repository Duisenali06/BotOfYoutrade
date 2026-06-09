"""
Простой дашборд — воронка, конверсии, топ вопросов.
Отдельная страница /admin?key=xxx
"""
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_

from app.config import settings
from app.db import get_session
from app.models import User, Event, Message
from app.scenario import TOTAL_STEPS


async def admin_dashboard() -> str:
    async with get_session() as session:
        total_users = (await session.execute(select(func.count(User.id)))).scalar() or 0

        now = datetime.utcnow()
        day_ago = now - timedelta(hours=24)
        week_ago = now - timedelta(days=7)

        active_24h = (await session.execute(
            select(func.count(User.id)).where(User.last_seen_at >= day_ago)
        )).scalar() or 0

        active_7d = (await session.execute(
            select(func.count(User.id)).where(User.last_seen_at >= week_ago)
        )).scalar() or 0

        sales_funnel = {}
        sales_funnel["Старт"] = total_users
        sales_funnel["Welcome показан"] = (await session.execute(
            select(func.count(func.distinct(Event.user_id))).where(Event.event_type == "welcome_4_shown")
        )).scalar() or 0
        sales_funnel["Вступил в диалог"] = (await session.execute(
            select(func.count(func.distinct(Event.user_id))).where(Event.event_type == "ai_response")
        )).scalar() or 0
        sales_funnel["Кликнул оплату"] = (await session.execute(
            select(func.count(func.distinct(Event.user_id))).where(Event.event_type == "clicked_payment_link")
        )).scalar() or 0
        sales_funnel["Купил"] = (await session.execute(
            select(func.count(User.id)).where(User.purchased == True)
        )).scalar() or 0

        funnel = {}
        for step in range(TOTAL_STEPS + 1):
            count = (await session.execute(
                select(func.count(User.id)).where(and_(
                    User.purchased == True,
                    User.max_step_reached >= step,
                ))
            )).scalar() or 0
            funnel[step] = count

        completed = (await session.execute(
            select(func.count(User.id)).where(User.completed_at.is_not(None))
        )).scalar() or 0

        purchased = sales_funnel["Купил"]

        takeovers = (await session.execute(
            select(func.count(User.id)).where(User.human_takeover == True)
        )).scalar() or 0

        ab_stats = {}
        for group in ["A", "B", "C"]:
            total = (await session.execute(
                select(func.count(User.id)).where(User.ab_group == group)
            )).scalar() or 0
            completed_g = (await session.execute(
                select(func.count(User.id)).where(
                    and_(User.ab_group == group, User.completed_at.is_not(None))
                )
            )).scalar() or 0
            purchased_g = (await session.execute(
                select(func.count(User.id)).where(
                    and_(User.ab_group == group, User.purchased == True)
                )
            )).scalar() or 0
            clicked_g = (await session.execute(
                select(func.count(func.distinct(Event.user_id))).where(and_(
                    Event.event_type == "clicked_payment_link",
                    Event.user_id.in_(select(User.id).where(User.ab_group == group))
                ))
            )).scalar() or 0
            ab_stats[group] = {
                "total": total,
                "completed": completed_g,
                "purchased": purchased_g,
                "clicked": clicked_g,
                "completion_rate": round(completed_g / total * 100, 1) if total else 0,
                "purchase_rate": round(purchased_g / total * 100, 1) if total else 0,
                "click_rate": round(clicked_g / total * 100, 1) if total else 0,
            }

        recent_questions = (await session.execute(
            select(Message).where(
                and_(Message.direction == "in", Message.created_at >= day_ago)
            ).order_by(Message.created_at.desc()).limit(30)
        )).scalars().all()

    sales_rows = ""
    start_count = sales_funnel["Старт"] or 1
    for label, count in sales_funnel.items():
        pct = round(count / start_count * 100, 1)
        sales_rows += f"""
        <tr>
          <td>{label}</td>
          <td class="mono">{count}</td>
          <td class="mono">{pct}%</td>
          <td><div class="bar"><div class="bar-fill" style="width:{pct}%"></div></div></td>
        </tr>
        """

    funnel_rows = ""
    start = funnel.get(0, 0) or 1
    for step in range(TOTAL_STEPS + 1):
        count = funnel.get(step, 0)
        pct = round(count / start * 100, 1)
        step_label = "Start" if step == 0 else f"Step {step}"
        funnel_rows += f"""
        <tr>
          <td>{step_label}</td>
          <td class="mono">{count}</td>
          <td class="mono">{pct}%</td>
          <td><div class="bar"><div class="bar-fill" style="width:{pct}%"></div></div></td>
        </tr>
        """

    ab_rows = ""
    for g, s in ab_stats.items():
        ab_rows += f"""
        <tr>
          <td><b>{g}</b></td>
          <td class="mono">{s['total']}</td>
          <td class="mono">{s['clicked']} ({s['click_rate']}%)</td>
          <td class="mono">{s['purchased']} ({s['purchase_rate']}%)</td>
          <td class="mono">{s['completed']} ({s['completion_rate']}%)</td>
        </tr>
        """

    questions_rows = ""
    for q in recent_questions:
        time_str = q.created_at.strftime("%H:%M %d.%m")
        step_str = f"Step {q.step}" if q.step and q.step >= 0 else "sales"
        text_preview = q.content[:120] + ("…" if len(q.content) > 120 else "")
        questions_rows += f"""
        <tr>
          <td class="mono" style="white-space:nowrap">{time_str}</td>
          <td>{step_str}</td>
          <td>{text_preview}</td>
        </tr>
        """

    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>YouTrade Bot Admin</title>
<style>
  body{{font-family:system-ui,-apple-system,sans-serif;background:#08070c;color:#f0f0f5;margin:0;padding:20px;line-height:1.5}}
  h1{{font-size:22px;margin:0 0 8px}}
  h2{{font-size:16px;margin:32px 0 12px;color:#10b981}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px}}
  .card{{background:#111118;border:1px solid rgba(255,255,255,0.05);border-radius:12px;padding:16px}}
  .card .label{{font-size:11px;color:#7a7a90;text-transform:uppercase;letter-spacing:1px}}
  .card .val{{font-size:26px;font-weight:700;margin-top:4px;font-family:'JetBrains Mono',monospace}}
  table{{width:100%;border-collapse:collapse;background:#111118;border-radius:12px;overflow:hidden}}
  th,td{{padding:10px 14px;text-align:left;border-bottom:1px solid rgba(255,255,255,0.04);font-size:13px}}
  th{{background:#0e0d14;font-size:11px;color:#7a7a90;text-transform:uppercase;letter-spacing:1px}}
  .mono{{font-family:'JetBrains Mono',monospace}}
  .bar{{width:100%;height:6px;background:rgba(255,255,255,0.05);border-radius:3px;overflow:hidden}}
  .bar-fill{{height:6px;background:#10b981;border-radius:3px}}
  .meta{{font-size:12px;color:#7a7a90}}
  .nav{{display:flex;gap:12px;margin-bottom:20px}}
  .nav a{{padding:6px 14px;background:#111118;border:1px solid rgba(255,255,255,0.05);border-radius:8px;color:#10b981;text-decoration:none;font-size:13px}}
  .nav a:hover{{background:#1a1a24}}
</style>
</head>
<body>
  <h1>YouTrade Bot — Dashboard</h1>
  <p class="meta">Updated: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}</p>

  <div class="nav">
    <a href="/crm?key=KEY_PLACEHOLDER">🗂 CRM / Диалоги</a>
  </div>

  <div class="grid">
    <div class="card"><div class="label">Всего юзеров</div><div class="val">{total_users}</div></div>
    <div class="card"><div class="label">Активных 24ч</div><div class="val">{active_24h}</div></div>
    <div class="card"><div class="label">Активных 7д</div><div class="val">{active_7d}</div></div>
    <div class="card"><div class="label">Купили</div><div class="val" style="color:#10b981">{purchased}</div></div>
    <div class="card"><div class="label">Завершили онбординг</div><div class="val">{completed}</div></div>
    <div class="card"><div class="label">На руках у менеджеров</div><div class="val" style="color:#ef4444">{takeovers}</div></div>
  </div>

  <h2>Воронка продаж</h2>
  <table>
    <thead><tr><th>Этап</th><th>Юзеры</th><th>% от старта</th><th></th></tr></thead>
    <tbody>{sales_rows}</tbody>
  </table>

  <h2>Воронка онбординга (после покупки)</h2>
  <table>
    <thead><tr><th>Шаг</th><th>Юзеры</th><th>% от купивших</th><th></th></tr></thead>
    <tbody>{funnel_rows}</tbody>
  </table>

  <h2>A/B группы</h2>
  <table>
    <thead><tr><th>Группа</th><th>Всего</th><th>Кликнули оплату</th><th>Купили</th><th>Прошли онбординг</th></tr></thead>
    <tbody>{ab_rows}</tbody>
  </table>

  <h2>Последние вопросы (24ч)</h2>
  <table>
    <thead><tr><th>Время</th><th>Этап</th><th>Вопрос</th></tr></thead>
    <tbody>{questions_rows if questions_rows else '<tr><td colspan="3" class="meta">Нет вопросов за последние 24ч</td></tr>'}</tbody>
  </table>
</body>
</html>
"""
    html = html.replace("KEY_PLACEHOLDER", settings.ADMIN_DASHBOARD_KEY)
    return html
