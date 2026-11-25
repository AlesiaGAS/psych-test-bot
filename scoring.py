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
LEADERSHIP_DATA: dict[str, Any] = load_json_data("leadership_questions.json")


def render_progress_bar(current: int, total: int, length: int = 10) -> str:
    filled = round((current / total) * length)
    return "▓" * filled + "░" * (length - filled)


# =====================================================================
# MBTI
# =====================================================================

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
        f"👤 <b>Кандидат:</b> {html.escape(full_name)}\n"
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


# =====================================================================
# DISC
# =====================================================================

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
        f"👤 <b>Кандидат:</b> {html.escape(full_name)}\n"
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


# =====================================================================
# LEADERSHIP (УПРАВЛЕНЧЕСКИЙ ПОТЕНЦИАЛ, SJT)
# =====================================================================

def _get_level_key(pct: int) -> tuple[str, str]:
    if pct >= 80:
        return "expert", "Экспертный"
    if pct >= 60:
        return "high", "Высокий"
    if pct >= 35:
        return "medium", "Базовый"
    return "low", "Низкий"


def calculate_leadership(answers: list[dict[str, Any]]) -> dict[str, Any]:
    """
    answers: список словарей {'scale': 'L', 'score': 3, 'opt_idx': 1} длиной 24.
    """
    raw_scores = {k: 0 for k in ("L", "U", "C", "A")}
    max_per_scale = {k: 0 for k in ("L", "U", "C", "A")}

    for q in LEADERSHIP_DATA["questions"]:
        max_per_scale[q["scale"]] += 3

    for ans in answers:
        raw_scores[ans["scale"]] += ans["score"]

    scales = {}
    total_score = 0
    total_max = 0

    for key in ("L", "U", "C", "A"):
        score = raw_scores[key]
        max_s = max_per_scale[key] or 18
        pct = round((score / max_s) * 100)
        lvl_key, lvl_label = _get_level_key(pct)
        meta = LEADERSHIP_DATA["scales"][key]

        total_score += score
        total_max += max_s

        scales[key] = {
            "name": meta["name"],
            "short": meta["short"],
            "score": score,
            "max": max_s,
            "pct": pct,
            "level_key": lvl_key,
            "level_label": lvl_label,
            "desc": meta["levels"][lvl_key],
        }

    overall_pct = round((total_score / (total_max or 72)) * 100)
    _, overall_label = _get_level_key(overall_pct)

    return {
        "overall_pct": overall_pct,
        "overall_label": overall_label,
        "code": f"{overall_pct}% ({overall_label})",
        "scales": scales,
    }


def format_leadership_user_result(result: dict[str, Any]) -> str:
    """Краткий и позитивный результат для пользователя без зон риска."""
    scales = result["scales"]
    ranked = sorted(scales.values(), key=lambda x: x["pct"], reverse=True)
    top_1, top_2 = ranked[0], ranked[1]

    scale_lines = [
        f"• <b>{s['name']}:</b> {s['pct']}%"
        for s in scales.values()
    ]

    return (
        f"✅ <b>Тест «Управленческий потенциал» завершён!</b>\n\n"
        f"<b>Ваши ключевые сильные зоны:</b>\n"
        f"🌟 {html.escape(top_1['name'])} ({top_1['pct']}%)\n"
        f"🌟 {html.escape(top_2['name'])} ({top_2['pct']}%)\n\n"
        f"<b>Общий профиль компетенций:</b>\n"
        f"{chr(10).join(scale_lines)}\n\n"
        f"Спасибо за прохождение! Ваши результаты сохранены."
    )


def format_leadership_admin_report(
    full_name: str,
    username: str | None,
    user_id: int,
    result: dict[str, Any],
) -> str:
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    user_tag = f"@{html.escape(username)}" if username else "отсутствует"

    scale_blocks = []
    for s in result["scales"].values():
        scale_blocks.append(
            f"• <b>{html.escape(s['name'])}:</b> {s['pct']}% "
            f"({s['score']}/{s['max']} — <i>{s['level_label']}</i>)\n"
            f"  └ {html.escape(s['desc'])}"
        )

    return (
        f"📋 <b>НОВЫЙ ОТЧЁТ: УПРАВЛЕНЧЕСКИЙ ПОТЕНЦИАЛ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Кандидат:</b> {html.escape(full_name)}\n"
        f"🔗 <b>Username:</b> {user_tag}\n"
        f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
        f"📅 <b>Дата:</b> {now_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏆 <b>Общий индекс:</b> <b>{result['overall_pct']}% ({result['overall_label']})</b>\n\n"
        f"📊 <b>Разбалловка по компетенциям:</b>\n"
        f"{chr(10).join(scale_blocks)}"
    )
