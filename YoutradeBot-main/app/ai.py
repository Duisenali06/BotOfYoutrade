"""
Claude API — для свободных ответов на вопросы.
Переключается между Аружан (sales) и Алией (support) по флагу user.purchased.
"""
import anthropic
from app.config import settings
from app.aruzhan_prompt import ARUZHAN_SYSTEM_PROMPT
from app.aliya_prompt import ALIYA_SYSTEM_PROMPT


client = anthropic.AsyncAnthropic(api_key=settings.CLAUDE_API_KEY)


def build_system_prompt(context: dict) -> str:
    """Выбираем промпт по статусу юзера и добавляем контекст."""
    purchased = context.get("purchased", False)

    if purchased:
        base = ALIYA_SYSTEM_PROMPT
        context_note = "\n\n[КОНТЕКСТ: юзер уже купил челлендж, режим support]"
        if context.get("current_step") is not None:
            context_note += f"\n[Текущий шаг онбординга: {context['current_step']} из 8]"
    else:
        base = ARUZHAN_SYSTEM_PROMPT
        context_note = "\n\n[КОНТЕКСТ: юзер ещё не купил, режим sales]"
        if context.get("welcome_completed"):
            context_note += "\n[Welcome-флоу отправлен, клиент видел инфу о компании и топ выплат]"

    ab_group = context.get("ab_group")
    if ab_group:
        context_note += f"\n[A/B группа: {ab_group}]"

    source = context.get("source")
    if source and source != "unknown":
        context_note += f"\n[Источник: {source}]"

    return base + context_note


async def ask_claude(user_message: str, context: dict | None = None) -> str:
    """Вызываем Claude с адаптивным промптом."""
    if context is None:
        context = {}

    try:
        system_prompt = build_system_prompt(context)

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text
    except Exception as e:
        print(f"[claude error] {e}")
        return (
            "Извините, что-то пошло не так. Попробуйте переформулировать вопрос или "
            "напишите нашей команде в WhatsApp: +7 708 190 6251"
        )
