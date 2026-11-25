import html
import json
import logging
import re
import aiohttp

logger = logging.getLogger(__name__)

MODELS = [
    "gemini-3.0-flash",
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
]

TEST_NAMES_RU = {
    "MBTI": "MBTI (тип личности)",
    "DISC": "DISC (поведенческий профиль)",
    "LEADERSHIP": "Управленческий потенциал (SJT-кейсы)",
}


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
            "maxOutputTokens": 4096,
        },
    }
    timeout = aiohttp.ClientTimeout(total=60)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        for model in MODELS:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={api_key}"
            )
            try:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["candidates"][0]["content"]["parts"][0]["text"]
                    err = await resp.text()
                    logger.error("Gemini %s error %s: %s", model, resp.status, err)
            except Exception as e:
                logger.error("Ошибка запроса к Gemini (%s): %s", model, e)

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

    passed_types = [rec["test_type"] for rec in records]
    missing_types = [
        TEST_NAMES_RU[t] for t in ("MBTI", "DISC", "LEADERSHIP") if t not in passed_types
    ]

    summary_blocks = []
    for rec in records:
        name_ru = TEST_NAMES_RU.get(rec["test_type"], rec["test_type"])
        summary_blocks.append(
            f"Тест «{name_ru}»: итог {rec['result_code']}\n"
            f"Детали шкал: {json.dumps(rec['scales_json'], ensure_ascii=False)}"
        )

    if len(records) == 1:
        point_2 = "**2. Ключевые особенности шкал** (глубокий разбор цифр и пограничных значений)"
    else:
        point_2 = "**2. Синергия и противоречия между пройденными тестами**"

    missing_note = ""
    if missing_types:
        missing_note = (
            f"\n\nПримечание: кандидат пока НЕ проходил тесты: {', '.join(missing_types)}. "
            f"Строй анализ строго на имеющихся данных, ничего не додумывай за непройденные тесты, "
            f"а в конце добавь 1–2 предложения, что именно поможет уточнить прохождение оставшихся тестов."
        )

    prompt = (
        f"Ты — опытный HRD и организационный психолог. "
        f"Перед тобой досье кандидата {full_name} на основе имеющихся результатов "
        f"(пройдено тестов: {len(records)} из 3):\n\n"
        f"{chr(10).join(summary_blocks)}"
        f"{missing_note}\n\n"
        f"Сформируй целостный и практичный портрет кандидата на русском языке (до 2800 символов).\n"
        f"Структура (используй **жирный** для заголовков, без символов #):\n"
        f"**1. Итоговый профиль кандидата** (кто этот человек в работе)\n"
        f"{point_2}\n"
        f"**3. Идеальная роль и масштаб задач** (где даст максимум результата)\n"
        f"**4. Главные риски найма / повышения**\n"
        f"**5. Ключ к управлению** (как ставить задачи, мотивировать и давать обратную связь)"
    )

    raw_text = await _call_gemini(api_key, prompt)
    return _format_ai_html(raw_text) if raw_text else None
