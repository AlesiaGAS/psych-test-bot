import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent / "data"


def load_json_data(filename: str) -> dict[str, Any]:
    path = DATA_DIR / filename
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


MBTI_DATA: dict[str, Any] = load_json_data("mbti_questions.json")
DISC_DATA: dict[str, Any] = load_json_data("disc_questions.json")


def render_progress_bar(current: int, total: int, length: int = 10) -> str:
    filled = round((current / total) * length)
    return "▓" * filled + "░" * (length - filled)


def calculate_mbti(answers: list[str]) -> dict[str, Any]:
    counts = {k: 0 for k in ("E", "I", "S", "N", "T", "F", "J", "P")}
    for trait in answers:
        if trait in counts:
            counts[trait] += 1

    dichotomies = [
        ("E", "I", "I"),
        ("S", "N", "N"),
        ("T", "F", "F"),
        ("J", "P", "P"),
    ]

    result_letters = []
    scales = {}

    for left, right, tie_winner in dichotomies:
        left_val = counts[left]
        right_val = counts[right]
        total = left_val + right_val or 1

        left_pct = round((left_val / total) * 100)
        right_pct = 100 - left_pct

        if left_val > right_val:
            winner = left
        elif right_val > left_val:
            winner = right
        else:
            winner = tie_winner

        result_letters.append(winner)
        scales[f"{left}/{right}"] = {
            "left": left,
            "right": right,
            "left_count": left_val,
            "right_count": right_val,
            "left_pct": left_pct,
            "right_pct": right_pct,
            "winner": winner,
        }

    mbti_type = "".join(result_letters)
    profile = MBTI_DATA["types"][mbti_type]

    return {
        "type": mbti_type,
        "scales": scales,
        "profile": profile,
    }


def format_mbti_user_result(result: dict[str, Any]) -> str:
    mbti_type = result["type"]
    profile = result["profile"]
    scales = result["scales"]

    scale_lines = [
        f"• <b>{data['left']}</b> {data['left_pct']}% — {data['right_pct']}% <b>{data['right']}</b>"
        for data in scales.values()
    ]

    return (
        f"✅ <b>Тест MBTI завершён!</b>\n\n"
        f"Ваш тип личности: <b>{mbti_type} — {html.escape(profile['title'])}</b>\n\n"
        f"<b>Распределение по шкалам:</b>\n"
        f"{chr(10).join(scale_lines)}\n\n"
        f"<b>Краткое описание:</b>\n"
        f"{html.escape(profile['short_desc'])}"
    )


def format_mbti_admin_report(
    full_name: str,
    username: str | None,
    user_id: int,
    result: dict[str, Any],
) -> str:
    mbti_type = result["type"]
    profile = result["profile"]
    scales = result["scales"]
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    user_tag = f"@{html.escape(username)}" if username else "отсутствует"

    scale_lines = [
        f"• <b>{data['left']}</b>: {data['left_count']} ({data['left_pct']}%) | "
        f"<b>{data['right']}</b>: {data['right_count']} ({data['right_pct']}%)"
        for data in scales.values()
    ]

    return (
        f"📋 <b>НОВЫЙ ОТЧЁТ: MBTI</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Кандидат / Пользователь:</b> {html.escape(full_name)}\n"
        f"🔗 <b>Username:</b> {user_tag}\n"
        f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
        f"📅 <b>Дата:</b> {now_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏆 <b>Итоговый тип:</b> <b>{mbti_type} — {html.escape(profile['title'])}</b>\n\n"
        f"📊 <b>Точная разбалловка:</b>\n"
        f"{chr(10).join(scale_lines)}\n\n"
        f"💪 <b>Сильные стороны:</b>\n{html.escape(profile['strengths'])}\n\n"
        f"⚠️ <b>Зоны риска:</b>\n{html.escape(profile['risks'])}\n\n"
        f"🗣 <b>Стиль коммуникации и управления:</b>\n{html.escape(profile['communication'])}"
    )


def calculate_disc(answers: list[dict[str, str]]) -> dict[str, Any]:
    total_blocks = len(DISC_DATA["blocks"])
    most = {k: 0 for k in ("D", "I", "S", "C")}
    least = {k: 0 for k in ("D", "I", "S", "C")}

    for item in answers:
        most[item["most"]] += 1
        least[item["least"]] += 1

    net = {k: most[k] - least[k] for k in ("D", "I", "S", "C")}
    pct = {
        k: round(((net[k] + total_blocks) / (2 * total_blocks)) * 100)
        for k in ("D", "I", "S", "C")
    }

    ranked = sorted(
        ("D", "I", "S", "C"),
        key=lambda k: (net[k], most[k]),
        reverse=True,
    )
    primary, secondary = ranked[0], ranked[1]

    if net[secondary] > 0 and (net[primary] - net[secondary]) <= 6:
        profile_code = f"{primary}/{secondary}"
    else:
        profile_code = primary

    profile = DISC_DATA["profiles"].get(profile_code) or DISC_DATA["profiles"][primary]

    return {
        "code": profile_code,
        "most": most,
        "least": least,
        "net": net,
        "pct": pct,
        "ranked": ranked,
        "profile": profile,
    }


def format_disc_user_result(result: dict[str, Any]) -> str:
    code = result["code"]
    profile = result["profile"]
    pct = result["pct"]

    labels = {
        "D": "D (Доминирование)",
        "I": "I (Влияние)",
        "S": "S (Стабильность)",
        "C": "C (Соответствие / Анализ)",
    }

    scale_lines = [
        f"• <b>{labels[k]}:</b> {pct[k]}%"
        for k in ("D", "I", "S", "C")
    ]

    return (
        f"✅ <b>Тест DISC завершён!</b>\n\n"
        f"Ваш профиль: <b>{code} — {html.escape(profile['title'])}</b>\n\n"
        f"<b>Выраженность факторов:</b>\n"
        f"{chr(10).join(scale_lines)}\n\n"
        f"<b>Краткое описание:</b>\n"
        f"{html.escape(profile['short_desc'])}"
    )


def format_disc_admin_report(
    full_name: str,
    username: str | None,
    user_id: int,
    result: dict[str, Any],
) -> str:
    code = result["code"]
    profile = result["profile"]
    most = result["most"]
    least = result["least"]
    net = result["net"]
    pct = result["pct"]
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    user_tag = f"@{html.escape(username)}" if username else "отсутствует"

    scale_lines = []
    for k in ("D", "I", "S", "C"):
        sign = "+" if net[k] > 0 else ""
        scale_lines.append(
            f"• <b>{k}</b>: {pct[k]}% (Итог: {sign}{net[k]} | Наиб: +{most[k]} / Наим: -{least[k]})"
        )

    return (
        f"📋 <b>НОВЫЙ ОТЧЁТ: DISC</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Кандидат / Пользователь:</b> {html.escape(full_name)}\n"
        f"🔗 <b>Username:</b> {user_tag}\n"
        f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
        f"📅 <b>Дата:</b> {now_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏆 <b>Итоговый профиль:</b> <b>{code} — {html.escape(profile['title'])}</b>\n\n"
        f"📊 <b>Разбалловка по шкалам:</b>\n"
        f"{chr(10).join(scale_lines)}\n\n"
        f"💪 <b>Сильные стороны:</b>\n{html.escape(profile['strengths'])}\n\n"
        f"⚠️ <b>Зоны риска:</b>\n{html.escape(profile['risks'])}\n\n"
        f"🗣 <b>Стиль коммуникации и мотивации:</b>\n{html.escape(profile['communication'])}"
    )
