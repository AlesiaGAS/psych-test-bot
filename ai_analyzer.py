import html
import json
import logging
import re
import aiohttp

logger = logging.getLogger(__name__)

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)


def _format_ai_html(text: str) -> str:
    """Безопасно экранирует HTML и превращает **жирный** в <b>жирный</b>."""
    safe = html.escape(text.strip())
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)


def _build_mbti_answers_log(questions: list[dict], answers: list[str]) -> str:
    lines = []
    for idx, (q, trait) in enumerate(zip(questions, answers), start=1):
        chosen_text = next(
            (opt["text"] for opt in q["options"] if opt["trait"] == trait),
            trait,
        )
        lines.append(f"{idx}. {q['text']} -> {chosen_text} [{trait}]")
    return "\n".join(lines)


def _build_disc_answers_log(blocks: list[dict], answers: list[dict[str, str]]) -> str:
    lines = []
    for idx, (block, ans) in enumerate(zip(blocks, answers), start=1):
        most_text = next(
            (opt["text"] for opt in block["options"] if opt["trait"] == ans["most"]),
            ans["most"],
        )
        least_text = next(
            (opt["text"] for opt in block["options"] if opt["trait"] == ans["least"]),
            ans["least"],
        )
        lines.append(
            f"Блок {idx}: НАИБОЛЕЕ подходит «{most_text}» [{ans['most']}] | "
            f"НАИМЕНЕЕ подходит «{least_text}» [{ans['least']}]"
        )
    return "\n".join(lines)


def _build_leadership_answers_log(questions: list[dict], answers: list[dict]) -> str:
    lines = []
    for idx, (q, ans) in enumerate(zip(questions, answers), start=1):
        opt = q["options"][ans["opt_idx"]]
        lines.append(
            f"Кейс {idx} [{q['scale']}, балл {ans['score']}/3]: {q['text']} -> «{opt['text']}»"
        )
    return "\n".join(lines)


async def _call_gemini(api_key: str, prompt: str) -> str | None:
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 2048,
        },
    }
    timeout = aiohttp.ClientTimeout(total=45)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{GEMINI_URL}?key={api_key}",
                json=payload,
            ) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    logger.error("Gemini API error %s: %s", resp.status, err)
                    return None
                data = await resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.error("Ошибка запроса к Gemini API: %s", e)
        return None


async def generate_mbti_ai_portrait(
    api_key: str | None,
    full_name: str,
    result: dict,
    questions: list[dict],
    answers: list[str],
) -> str | None:
    if not api_key:
        return None

    scales_str = ", ".join(
        f"{k}: {v['left']}={v['left_pct']}% / {v['right']}={v['right_pct']}%"
        for k, v in result["scales"].items()
    )
    answers_log = _build_mbti_answers_log(questions, answers)

    prompt = (
        f"Ты — опытный организационный психолог и HR-аналитик. "
        f"Проанализируй результаты теста MBTI кандидата {full_name}.\n\n"
        f"Итоговый тип: {result['type']} ({result['profile']['title']})\n"
        f"Шкалы: {scales_str}\n\n"
        f"Все 70 ответов кандидата:\n{answers_log}\n\n"
        f"Напиши глубокий, практичный отчёт для руководителя/HR на русском языке (до 2500 символов). "
        f"Опирайся именно на конкретные ответы и их сочетания, а не на общие шаблоны.\n"
        f"Структура (используй **жирный** для заголовков, без символов #):\n"
        f"**1. Психологический портрет**\n"
        f"**2. Нюансы и противоречия в ответах**\n"
        f"**3. Сильные стороны и главная мотивация**\n"
        f"**4. Зоны риска и триггеры стресса**\n"
        f"**5. Как управлять и общаться** (3–4 конкретные рекомендации)"
    )

    raw_text = await _call_gemini(api_key, prompt)
    return _format_ai_html(raw_text) if raw_text else None


async def generate_disc_ai_portrait(
    api_key: str | None,
    full_name: str,
    result: dict,
    blocks: list[dict],
    answers: list[dict[str, str]],
) -> str | None:
    if not api_key:
        return None

    scales_str = ", ".join(
        f"{k}: {result['pct'][k]}% (Итог {result['net'][k]:+d}, Наиб +{result['most'][k]}, Наим -{result['least'][k]})"
        for k in ("D", "I", "S", "C")
    )
    answers_log = _build_disc_answers_log(blocks, answers)

    prompt = (
        f"Ты — опытный организационный психолог и HR-аналитик. "
        f"Проанализируй результаты теста DISC кандидата {full_name}.\n\n"
        f"Итоговый профиль: {result['code']} ({result['profile']['title']})\n"
        f"Шкалы: {scales_str}\n\n"
        f"Все 24 блока ответов кандидата:\n{answers_log}\n\n"
        f"Напиши глубокий, практичный отчёт для руководителя/HR на русском языке (до 2500 символов). "
        f"Опирайся на конкретные выборы «наиболее/наименее подходит».\n"
        f"Структура (используй **жирный** для заголовков, без символов #):\n"
        f"**1. Поведенческий портрет**\n"
        f"**2. Разница между адаптивным и естественным стилем** (анализ Наиб vs Наим)\n"
        f"**3. Сильные стороны и драйверы мотивации**\n"
        f"**4. Зоны риска и слепые пятна**\n"
        f"**5. Рекомендации по управлению и постановке задач**"
    )

    raw_text = await _call_gemini(api_key, prompt)
    return _format_ai_html(raw_text) if raw_text else None


async def generate_leadership_ai_portrait(
    api_key: str | None,
    full_name: str,
    result: dict,
    questions: list[dict],
    answers: list[dict],
) -> str | None:
    if not api_key:
        return None

    scales_str = ", ".join(
        f"{s['name']}: {s['pct']}% ({s['level_label']})"
        for s in result["scales"].values()
    )
    answers_log = _build_leadership_answers_log(questions, answers)

    prompt = (
        f"Ты — опытный HRD и эксперт по оценке управленческого потенциала (Assessment Center). "
        f"Проанализируй ответы кандидата {full_name} в тесте ситуационных суждений (SJT).\n\n"
        f"Общий индекс: {result['overall_pct']}% ({result['overall_label']})\n"
        f"Шкалы: {scales_str}\n\n"
        f"Конкретные выборы в 24 кейсах:\n{answers_log}\n\n"
        f"Напиши жёсткий, честный и практичный разбор для руководителя на русском языке (до 2500 символов).\n"
        f"Структура (используй **жирный** для заголовков, без символов #):\n"
        f"**1. Готовность к руководству** (на какую роль готов сейчас: исполнитель / тимлид / руководитель отдела)\n"
        f"**2. Поведение в хаосе и под критикой** (реальные паттерны из кейсов)\n"
        f"**3. Скрытые управленческие риски** (например, высокие амбиции при слабой устойчивости к критике или склонность к микроменеджменту)\n"
        f"**4. План развития на ближайшие 3–6 месяцев** (что прокачать перед повышением)"
    )

    raw_text = await _call_gemini(api_key, prompt)
    return _format_ai_html(raw_text) if raw_text else None


async def generate_dossier_ai_summary(
    api_key: str | None,
    full_name: str,
    records: list[dict],
) -> str | None:
    if not api_key or not records:
        return None

    summary_blocks = []
    for rec in records:
        summary_blocks.append(
            f"Тест {rec['test_type']}: итог {rec['result_code']}\n"
            f"Детали шкал: {json.dumps(rec['scales_json'], ensure_ascii=False)}"
        )

    prompt = (
        f"Ты — опытный HRD и организационный психолог. "
        f"Перед тобой сводное досье кандидата {full_name} по всем пройденным тестам:\n\n"
        f"{chr(10).join(summary_blocks)}\n\n"
        f"Синтезируй единый, целостный портрет кандидата на русском языке (до 2800 символов). "
        f"Найди пересечения, усиления и внутренние конфликты между разными тестами.\n"
        f"Структура (используй **жирный** для заголовков, без символов #):\n"
        f"**1. Итоговый профиль кандидата** (кто этот человек в работе)\n"
        f"**2. Синергия и противоречия между тестами**\n"
        f"**3. Идеальная роль и масштаб задач** (где даст максимум результата)\n"
        f"**4. Главные риски найма / повышения**\n"
        f"**5. Ключ к управлению** (как ставить задачи, мотивировать и давать обратную связь)"
    )

    raw_text = await _call_gemini(api_key, prompt)
    return _format_ai_html(raw_text) if raw_text else None
