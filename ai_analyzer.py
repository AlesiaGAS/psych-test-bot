import html
import json
import logging
import os
import re
import aiohttp

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS = [
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "google/gemma-4-26b-a4b-it:free",
    "openrouter/free",
]

GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
]

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS = [
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
]

TEST_NAMES_RU = {
    "MBTI": "MBTI (тип личности)",
    "DISC": "DISC (поведенческий профиль)",
    "LEADERSHIP": "Управленческий потенциал (SJT-кейсы)",
}

SYSTEM_PROMPT = (
    "Ты — сильный HR-бизнес-партнёр и практик управления с 15-летним опытом в реальном бизнесе. "
    "Пишешь отчёты для руководителя, которому нужно принять конкретное кадровое решение (брать/не брать, повышать/нет, как управлять).\n\n"
    "ПРАВИЛА СТИЛЯ И ГРАММАТИКИ:\n"
    "- Пиши безупречным, живым, точным русским языком, без канцелярита и воды.\n"
    "- СТРОГО следи за полом кандидата по его ФИО (например, Стрельцова — женский род, «она», «её», «Стрельцовой»; Иванов — мужской род). Никогда не коверкай фамилию и не путай род.\n"
    "- ЗАПРЕЩЕНО выдумывать имена коллег или несуществующие детали (никаких «согласовать с Александром»).\n"
    "- СТРОГО сверяй выводы с цифрами шкал: не путай высокие и низкие показатели (например, если D = 83%, это ВЫСОКИЙ D, а не низкий).\n"
    "- ЗАПРЕЩЕНЫ шаблонные советы вроде «пройти тренинг по эмоциональному интеллекту», «поработать с коучем», «внедрить Agile-спринты», «матрица RACI». "
    "Давай только конкретные управленческие действия: как именно ставить задачу, что контролировать, как давать обратную связь, какие ситуации станут триггером.\n\n"
    "ПРАВИЛА ФОРМАТИРОВАНИЯ (КРИТИЧНО ДЛЯ TELEGRAM):\n"
    "- НИКАКИХ таблиц (символ | вообще не используй).\n"
    "- НИКАКИХ HTML-тегов (никаких <br>, <b> и т.д.).\n"
    "- НИКАКИХ заголовков через # или ##.\n"
    "- Для заголовков разделов используй только **жирный текст** на отдельной строке.\n"
    "- Для списков используй только символ «• » в начале строки.\n"
    "- Разделяй блоки пустой строкой, чтобы текст легко читался с телефона."
)


def _format_ai_html(text: str) -> str:
    """Чистит мусор от LLM и безопасно конвертирует в Telegram HTML."""
    # Убираем блоки <think>...</think>, если модель рассуждений их вернула
    cleaned = re.sub(r"<think>.*?</think>", "", text.strip(), flags=re.DOTALL | re.IGNORECASE)
    # Убираем случайные <br> и <br/> до экранирования
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
    # Убираем разделители таблиц вида |---|---|
    cleaned = re.sub(r"^\s*\|?[-:\s|]+\|?\s*$", "", cleaned, flags=re.MULTILINE)
    # Убираем markdown-заголовки ### в начале строк
    cleaned = re.sub(r"^#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
    # Приводим маркеры списков (- или *) к аккуратному •
    cleaned = re.sub(r"^\s*[-*]\s+", "• ", cleaned, flags=re.MULTILINE)
    # Схлопываем лишние пустые строки (больше 2 подряд)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    safe = html.escape(cleaned.strip())
    # Конвертируем **жирный** в <b>жирный</b>
    safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)
    return safe


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


async def _call_openrouter(api_key: str, prompt: str) -> str | None:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Title": "HR Psych Test Bot",
    }
    timeout = aiohttp.ClientTimeout(total=45)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        for model in OPENROUTER_MODELS:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.4,
                "max_tokens": 2500,
            }
            try:
                logger.info("Отправляю запрос в OpenRouter (%s)...", model)
                async with session.post(OPENROUTER_URL, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data["choices"][0]["message"].get("content")
                        if content:
                            logger.info("OpenRouter (%s) успешно ответил.", model)
                            return content
                    err = await resp.text()
                    logger.error("OpenRouter %s error %s: %s", model, resp.status, err)
            except Exception as e:
                logger.error("Ошибка запроса к OpenRouter (%s): %s", model, e)

    return None


async def _call_gemini(api_key: str, prompt: str) -> str | None:
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 3000,
        },
    }
    timeout = aiohttp.ClientTimeout(total=25)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        for model in GEMINI_MODELS:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={api_key}"
            )
            try:
                logger.info("Отправляю резервный запрос в Gemini (%s)...", model)
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        logger.info("Gemini (%s) успешно ответил.", model)
                        return data["candidates"][0]["content"]["parts"][0]["text"]
                    err = await resp.text()
                    logger.error("Gemini %s error %s: %s", model, resp.status, err)
            except Exception as e:
                logger.error("Ошибка запроса к Gemini (%s): %s", model, e)

    return None


async def _call_groq(api_key: str, prompt: str) -> str | None:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        for model in GROQ_MODELS:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.4,
                "max_tokens": 2500,
            }
            try:
                logger.info("Отправляю резервный запрос в Groq (%s)...", model)
                async with session.post(GROQ_URL, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        logger.info("Groq (%s) успешно ответил.", model)
                        return data["choices"][0]["message"]["content"]
                    err = await resp.text()
                    logger.error("Groq %s error %s: %s", model, resp.status, err)
            except Exception as e:
                logger.error("Ошибка запроса к Groq (%s): %s", model, e)

    return None


async def _call_ai(gemini_api_key: str | None, prompt: str) -> str | None:
    """Порядок: OpenRouter (free) -> Gemini -> Groq."""
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if openrouter_key:
        text = await _call_openrouter(openrouter_key, prompt)
        if text:
            return text
    else:
        logger.warning("OPENROUTER_API_KEY не найден в переменных окружения Render!")

    if gemini_api_key:
        text = await _call_gemini(gemini_api_key, prompt)
        if text:
            return text

    groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_api_key:
        return await _call_groq(groq_api_key, prompt)

    return None


async def generate_mbti_ai_portrait(
    api_key: str | None,
    full_name: str,
    result: dict,
    questions: list[dict],
    answers: list[str],
) -> str | None:
    scales_str = ", ".join(
        f"{k}: {v['left']}={v['left_pct']}% / {v['right']}={v['right_pct']}%"
        for k, v in result["scales"].items()
    )
    answers_log = _build_mbti_answers_log(questions, answers)

    prompt = (
        f"Проанализируй результаты теста MBTI кандидата {full_name}.\n\n"
        f"Итоговый тип: {result['type']} ({result['profile']['title']})\n"
        f"Шкалы: {scales_str}\n\n"
        f"Все 70 ответов кандидата:\n{answers_log}\n\n"
        f"Напиши ёмкий разбор (1500–2200 символов) по структуре:\n"
        f"**1. Как мыслит и работает** (суть личности без общих штампов)\n"
        f"**2. Нюансы и противоречия в ответах** (пограничные шкалы, нетипичные выборы)\n"
        f"**3. Что реально мотивирует, а что демотивирует**\n"
        f"**4. Зоны риска** (где выгорит или создаст конфликт)\n"
        f"**5. Как руководителю с ним работать** (3–4 коротких конкретных правила через «• »)"
    )

    raw_text = await _call_ai(api_key, prompt)
    return _format_ai_html(raw_text) if raw_text else None


async def generate_disc_ai_portrait(
    api_key: str | None,
    full_name: str,
    result: dict,
    blocks: list[dict],
    answers: list[dict[str, str]],
) -> str | None:
    scales_str = ", ".join(
        f"{k}: {result['pct'][k]}% (Итог {result['net'][k]:+d}, Наиб +{result['most'][k]}, Наим -{result['least'][k]})"
        for k in ("D", "I", "S", "C")
    )
    answers_log = _build_disc_answers_log(blocks, answers)

    prompt = (
        f"Проанализируй результаты теста DISC кандидата {full_name}.\n\n"
        f"Итоговый профиль: {result['code']} ({result['profile']['title']})\n"
        f"Шкалы: {scales_str}\n\n"
        f"Все 24 блока ответов кандидата:\n{answers_log}\n\n"
        f"Напиши ёмкий разбор (1500–2200 символов) по структуре:\n"
        f"**1. Поведенческий стиль в работе и под давлением**\n"
        f"**2. Адаптивный vs естественный стиль** (что показывает разница между Наиб и Наим)\n"
        f"**3. Сильные стороны и главные драйверы**\n"
        f"**4. Слепые пятна и риски в команде**\n"
        f"**5. Как ставить задачи и контролировать** (3–4 конкретных правила через «• »)"
    )

    raw_text = await _call_ai(api_key, prompt)
    return _format_ai_html(raw_text) if raw_text else None


async def generate_leadership_ai_portrait(
    api_key: str | None,
    full_name: str,
    result: dict,
    questions: list[dict],
    answers: list[dict],
) -> str | None:
    scales_str = ", ".join(
        f"{s['name']}: {s['pct']}% ({s['level_label']})"
        for s in result["scales"].values()
    )
    answers_log = _build_leadership_answers_log(questions, answers)

    prompt = (
        f"Проанализируй ответы кандидата {full_name} в тесте управленческого потенциала (SJT).\n\n"
        f"Общий индекс: {result['overall_pct']}% ({result['overall_label']})\n"
        f"Шкалы: {scales_str}\n\n"
        f"Конкретные выборы в 24 кейсах:\n{answers_log}\n\n"
        f"Напиши честный, практичный разбор для руководителя (1600–2300 символов) по структуре:\n"
        f"**1. Вердикт по роли** (на какой уровень готов прямо сейчас: исполнитель / старший / тимлид / руководитель — и почему)\n"
        f"**2. Реальное поведение в хаосе и под критикой** (конкретные паттерны из выбранных кейсов)\n"
        f"**3. Скрытые управленческие риски** (перекосы между шкалами, где может «сломаться»)\n"
        f"**4. Что проверить и подтянуть в первые 3 месяца** (3–4 практических шага на рабочем месте через «• », без воды и без таблиц)"
    )

    raw_text = await _call_ai(api_key, prompt)
    return _format_ai_html(raw_text) if raw_text else None


async def generate_dossier_ai_summary(
    api_key: str | None,
    full_name: str,
    records: list[dict],
) -> str | None:
    if not records:
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
        point_2 = "**2. Что важно в цифрах** (разбор сильных перекосов и пограничных значений)"
    else:
        point_2 = "**2. Как тесты дополняют или противоречат друг другу**"

    missing_note = ""
    if missing_types:
        missing_note = (
            f"\n\nПримечание: кандидат пока НЕ проходил тесты: {', '.join(missing_types)}. "
            f"Опирайся только на имеющиеся данные, а в самом конце в 1–2 предложениях укажи, что именно помогут уточнить оставшиеся тесты."
        )

    prompt = (
        f"Перед тобой досье кандидата {full_name} (пройдено тестов: {len(records)} из 3):\n\n"
        f"{chr(10).join(summary_blocks)}"
        f"{missing_note}\n\n"
        f"Собери целостный, острый и полезный портрет для руководителя (1800–2500 символов) по структуре:\n"
        f"**1. Кто этот человек в работе** (главная суть без воды)\n"
        f"{point_2}\n"
        f"**3. Идеальная роль и задачи** (где даст максимум отдачи)\n"
        f"**4. Главные риски найма или повышения**\n"
        f"**5. Ключ к управлению** (3–4 конкретных правила: как ставить задачи, мотивировать и критиковать — списком через «• »)"
    )

    raw_text = await _call_ai(api_key, prompt)
    return _format_ai_html(raw_text) if raw_text else None
