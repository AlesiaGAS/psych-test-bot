import html
import logging
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ai_analyzer import (
    generate_disc_ai_portrait,
    generate_dossier_ai_summary,
    generate_leadership_ai_portrait,
    generate_mbti_ai_portrait,
)
from db import Database
from keyboards import (
    after_test_kb,
    cancel_only_kb,
    disc_block_kb,
    dossier_card_kb,
    dossier_list_kb,
    leadership_question_kb,
    main_menu_kb,
    mbti_question_kb,
)
from scoring import (
    DISC_DATA,
    LEADERSHIP_DATA,
    MBTI_DATA,
    calculate_disc,
    calculate_leadership,
    calculate_mbti,
    format_disc_admin_report,
    format_disc_user_result,
    format_leadership_admin_report,
    format_leadership_user_result,
    format_mbti_admin_report,
    format_mbti_user_result,
    render_progress_bar,
)
from states import TestFlow

logger = logging.getLogger(__name__)
router = Router()

WELCOME_TEXT = (
    "👋 <b>Добро пожаловать в бот психологического и управленческого тестирования!</b>\n\n"
    "Выберите тест:\n"
    "• <b>MBTI</b> — 70 вопросов, тип личности по 4 дихотомиям (E/I, S/N, T/F, J/P).\n"
    "• <b>DISC</b> — 24 блока, поведенческий профиль (D, I, S, C).\n"
    "• <b>Управленческий потенциал</b> — 24 рабочих кейса (лидерство, неопределённость, критика, амбиции)."
)


async def safe_edit_text(message: Message, text: str, reply_markup=None) -> None:
    try:
        await message.edit_text(text=text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


async def send_long_message(bot: Bot, chat_id: int, text: str) -> None:
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        try:
            await bot.send_message(chat_id=chat_id, text=chunk)
        except Exception as e:
            logger.error("Не удалось отправить сообщение в %s: %s", chat_id, e)


async def send_report_to_admins(bot: Bot, admin_ids: list[int], report_text: str) -> None:
    for admin_id in admin_ids:
        await send_long_message(bot, admin_id, report_text)


def build_mbti_question_text(q_index: int) -> str:
    questions = MBTI_DATA["questions"]
    total = len(questions)
    q = questions[q_index]
    bar = render_progress_bar(q_index + 1, total)

    opt_a = html.escape(q["options"][0]["text"])
    opt_b = html.escape(q["options"][1]["text"])

    return (
        f"🧠 <b>Тест MBTI</b> | Вопрос <b>{q_index + 1} из {total}</b>\n"
        f"<code>[{bar}]</code>\n\n"
        f"<b>{html.escape(q['text'])}</b>\n\n"
        f"<b>А.</b> {opt_a}\n"
        f"<b>Б.</b> {opt_b}"
    )


def build_disc_block_text(
    block_index: int,
    step: str,
    chosen_most_idx: int | None = None,
) -> str:
    blocks = DISC_DATA["blocks"]
    total = len(blocks)
    block = blocks[block_index]
    bar = render_progress_bar(block_index + 1, total)

    lines = []
    for idx, item in enumerate(block["options"]):
        text = html.escape(item["text"])
        if chosen_most_idx is not None and idx == chosen_most_idx:
            lines.append(f"<s>{idx + 1}. {text}</s> ✅ <i>(Наиболее подходит)</i>")
        else:
            lines.append(f"<b>{idx + 1}.</b> {text}")

    if step == "most":
        prompt = "➕ Выберите утверждение, которое <b>НАИБОЛЕЕ</b> вам подходит:"
    else:
        prompt = "➖ Теперь выберите утверждение, которое <b>НАИМЕНЕЕ</b> вам подходит:"

    return (
        f"📊 <b>Тест DISC</b> | Блок <b>{block_index + 1} из {total}</b>\n"
        f"<code>[{bar}]</code>\n\n"
        f"{chr(10).join(lines)}\n\n"
        f"{prompt}"
    )


def build_leadership_question_text(q_index: int) -> str:
    questions = LEADERSHIP_DATA["questions"]
    total = len(questions)
    q = questions[q_index]
    bar = render_progress_bar(q_index + 1, total)

    opt_lines = [
        f"<b>{idx + 1}.</b> {html.escape(opt['text'])}"
        for idx, opt in enumerate(q["options"])
    ]

    return (
        f"🚀 <b>Управленческий потенциал</b> | Кейс <b>{q_index + 1} из {total}</b>\n"
        f"<code>[{bar}]</code>\n\n"
        f"<b>{html.escape(q['text'])}</b>\n\n"
        f"{chr(10).join(opt_lines)}"
    )


def format_dossier_card(records: list[dict]) -> str:
    latest = max(records, key=lambda r: r["created_at"])
    full_name = html.escape(latest["full_name"])
    username = f"@{html.escape(latest['username'])}" if latest["username"] else "отсутствует"
    user_id = latest["user_id"]

    by_type = {r["test_type"]: r for r in records}
    sections = []

    if "MBTI" in by_type:
        r = by_type["MBTI"]
        dt = r["created_at"].strftime("%d.%m.%Y")
        scales = r["scales_json"]
        sc_str = " | ".join(
            f"{v['left']}{v['left_pct']}%/{v['right']}{v['right_pct']}%"
            for v in scales.values()
        )
        sections.append(f"🧠 <b>MBTI</b> ({dt}): <b>{html.escape(r['result_code'])}</b>\n   <i>{sc_str}</i>")
    else:
        sections.append("🧠 <b>MBTI:</b> не пройден")

    if "DISC" in by_type:
        r = by_type["DISC"]
        dt = r["created_at"].strftime("%d.%m.%Y")
        pct = r["scales_json"].get("pct", {})
        sc_str = " | ".join(f"{k}: {pct.get(k, 0)}%" for k in ("D", "I", "S", "C"))
        sections.append(f"📊 <b>DISC</b> ({dt}): <b>{html.escape(r['result_code'])}</b>\n   <i>{sc_str}</i>")
    else:
        sections.append("📊 <b>DISC:</b> не пройден")

    if "LEADERSHIP" in by_type:
        r = by_type["LEADERSHIP"]
        dt = r["created_at"].strftime("%d.%m.%Y")
        scales = r["scales_json"]
        sc_lines = [
            f"   • {html.escape(v['short'])}: <b>{v['pct']}%</b> ({v['level_label']})"
            for v in scales.values()
        ]
        sections.append(
            f"🚀 <b>Управленческий потенциал</b> ({dt}): <b>{html.escape(r['result_code'])}</b>\n"
            + "\n".join(sc_lines)
        )
    else:
        sections.append("🚀 <b>Управленческий потенциал:</b> не пройден")

    return (
        f"🗂 <b>ДОСЬЕ КАНДИДАТА</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Имя:</b> {full_name}\n"
        f"🔗 <b>Username:</b> {username}\n"
        f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        + "\n\n".join(sections)
    )


# =====================================================================
# СТАРТ, МЕНЮ И ОТМЕНА
# =====================================================================

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb())


@router.callback_query(F.data == "test:menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_edit_text(callback.message, WELCOME_TEXT, reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "test:cancel")
async def cb_cancel_test(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_edit_text(
        callback.message,
        "❌ Тестирование отменено.\n\n" + WELCOME_TEXT,
        reply_markup=main_menu_kb(),
    )
    await callback.answer("Тест отменён")


# =====================================================================
# АДМИН-ДОСЬЕ (/dossier)
# =====================================================================

@router.message(Command("dossier"))
async def cmd_dossier(
    message: Message,
    admin_ids: list[int],
    db: Database,
) -> None:
    if message.from_user.id not in admin_ids:
        return

    candidates = await db.get_all_candidates(limit=30)
    if not candidates:
        await message.answer("🗂 База досье пока пуста — никто ещё не завершил тестирование.")
        return

    await message.answer(
        "🗂 <b>Досье кандидатов</b> (последние 30):\n"
        "Выберите человека, чтобы посмотреть все его результаты:",
        reply_markup=dossier_list_kb(candidates),
    )


@router.callback_query(F.data == "dossier:list")
async def cb_dossier_list(
    callback: CallbackQuery,
    admin_ids: list[int],
    db: Database,
) -> None:
    if callback.from_user.id not in admin_ids:
        await callback.answer("Нет доступа", show_alert=True)
        return

    candidates = await db.get_all_candidates(limit=30)
    await safe_edit_text(
        callback.message,
        "🗂 <b>Досье кандидатов</b> (последние 30):\n"
        "Выберите человека, чтобы посмотреть все его результаты:",
        reply_markup=dossier_list_kb(candidates),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dossier:view:"))
async def cb_dossier_view(
    callback: CallbackQuery,
    admin_ids: list[int],
    db: Database,
) -> None:
    if callback.from_user.id not in admin_ids:
        await callback.answer("Нет доступа", show_alert=True)
        return

    target_user_id = int(callback.data.split(":")[2])
    records = await db.get_candidate_results(target_user_id)
    if not records:
        await callback.answer("Данные не найдены", show_alert=True)
        return

    await safe_edit_text(
        callback.message,
        format_dossier_card(records),
        reply_markup=dossier_card_kb(target_user_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dossier:ai:"))
async def cb_dossier_ai(
    callback: CallbackQuery,
    bot: Bot,
    admin_ids: list[int],
    db: Database,
    gemini_api_key: str | None,
) -> None:
    if callback.from_user.id not in admin_ids:
        await callback.answer("Нет доступа", show_alert=True)
        return

    if not gemini_api_key:
        await callback.answer("Не задан GEMINI_API_KEY в Render", show_alert=True)
        return

    target_user_id = int(callback.data.split(":")[2])
    records = await db.get_candidate_results(target_user_id)
    if not records:
        await callback.answer("Данные не найдены", show_alert=True)
        return

    await callback.answer("⏳ Собираю сводный ИИ-портрет...")
    full_name = records[0]["full_name"]

    ai_text = await generate_dossier_ai_summary(
        api_key=gemini_api_key,
        full_name=full_name,
        records=records,
    )
    if ai_text:
        header = (
            f"🤖 <b>СВОДНЫЙ ИИ-ПОРТРЕТ: {html.escape(full_name)}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        await send_long_message(bot, callback.from_user.id, header + ai_text)
    else:
        await bot.send_message(
            callback.from_user.id,
            "⚠️ Не удалось получить ответ от Gemini API. Попробуйте чуть позже.",
        )


# =====================================================================
# ВЫБОР ТЕСТА И ЗАПРОС ИМЕНИ
# =====================================================================

@router.callback_query(F.data.startswith("select_test:"))
async def cb_select_test(callback: CallbackQuery, state: FSMContext) -> None:
    test_type = callback.data.split(":")[1]
    names = {
        "mbti": "MBTI (70 вопросов)",
        "disc": "DISC (24 блока)",
        "leadership": "Управленческий потенциал (24 кейса)",
    }

    await state.clear()
    await state.set_state(TestFlow.waiting_for_name)
    await state.update_data(selected_test=test_type)

    await safe_edit_text(
        callback.message,
        f"Вы выбрали тест <b>{names[test_type]}</b>.\n\n"
        f"✍️ Пожалуйста, введите ваше <b>Имя</b> (или ФИО) ответным сообщением:",
        reply_markup=cancel_only_kb(),
    )
    await callback.answer()


@router.message(TestFlow.waiting_for_name)
async def process_user_name(message: Message, state: FSMContext) -> None:
    full_name = (message.text or "").strip()
    if len(full_name) < 2 or len(full_name) > 100:
        await message.answer(
            "Пожалуйста, введите корректное имя (от 2 до 100 символов).",
            reply_markup=cancel_only_kb(),
        )
        return

    data = await state.get_data()
    test_type = data["selected_test"]

    if test_type == "mbti":
        await state.set_state(TestFlow.in_mbti_test)
        await state.update_data(full_name=full_name, q_index=0, answers=[])
        q = MBTI_DATA["questions"][0]
        await message.answer(
            text=build_mbti_question_text(0),
            reply_markup=mbti_question_kb(0, q["options"]),
        )
    elif test_type == "disc":
        await state.set_state(TestFlow.in_disc_test)
        await state.update_data(
            full_name=full_name,
            block_index=0,
            disc_step="most",
            current_most_idx=None,
            answers=[],
        )
        await message.answer(
            text=build_disc_block_text(0, "most"),
            reply_markup=disc_block_kb(0, "most"),
        )
    else:
        await state.set_state(TestFlow.in_leadership_test)
        await state.update_data(full_name=full_name, q_index=0, answers=[])
        await message.answer(
            text=build_leadership_question_text(0),
            reply_markup=leadership_question_kb(0),
        )


# =====================================================================
# ПРОХОЖДЕНИЕ MBTI
# =====================================================================

@router.callback_query(TestFlow.in_mbti_test, F.data.startswith("mbti_ans:"))
async def cb_mbti_answer(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    admin_ids: list[int],
    db: Database,
    gemini_api_key: str | None,
) -> None:
    _, raw_q_idx, raw_opt_idx = callback.data.split(":")
    q_idx = int(raw_q_idx)
    opt_idx = int(raw_opt_idx)

    data = await state.get_data()
    current_idx = data["q_index"]

    if q_idx != current_idx:
        await callback.answer()
        return

    questions = MBTI_DATA["questions"]
    chosen_trait = questions[current_idx]["options"][opt_idx]["trait"]

    answers: list[str] = data["answers"]
    answers.append(chosen_trait)
    next_idx = current_idx + 1

    if next_idx < len(questions):
        await state.update_data(q_index=next_idx, answers=answers)
        next_q = questions[next_idx]
        await safe_edit_text(
            callback.message,
            build_mbti_question_text(next_idx),
            reply_markup=mbti_question_kb(next_idx, next_q["options"]),
        )
        await callback.answer()
    else:
        result = calculate_mbti(answers)
        await db.save_result(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            full_name=data["full_name"],
            test_type="MBTI",
            result_code=result["type"],
            scales_data=result["scales"],
        )

        user_text = format_mbti_user_result(result)
        await state.clear()
        await safe_edit_text(callback.message, user_text, reply_markup=after_test_kb())
        await callback.answer("Тест завершён!")

        admin_text = format_mbti_admin_report(
            full_name=data["full_name"],
            username=callback.from_user.username,
            user_id=callback.from_user.id,
            result=result,
        )
        await send_report_to_admins(bot, admin_ids, admin_text)

        ai_portrait = await generate_mbti_ai_portrait(
            api_key=gemini_api_key,
            full_name=data["full_name"],
            result=result,
            questions=questions,
            answers=answers,
        )
        if ai_portrait:
            ai_header = (
                f"🤖 <b>ИИ-ПОРТРЕТ (MBTI): {html.escape(data['full_name'])} "
                f"({result['type']})</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            )
            await send_report_to_admins(bot, admin_ids, ai_header + ai_portrait)


@router.callback_query(TestFlow.in_mbti_test, F.data == "test:back")
async def cb_mbti_back(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    current_idx = data["q_index"]
    answers: list[str] = data["answers"]

    if current_idx > 0:
        prev_idx = current_idx - 1
        if answers:
            answers.pop()
        await state.update_data(q_index=prev_idx, answers=answers)
        prev_q = MBTI_DATA["questions"][prev_idx]
        await safe_edit_text(
            callback.message,
            build_mbti_question_text(prev_idx),
            reply_markup=mbti_question_kb(prev_idx, prev_q["options"]),
        )
    await callback.answer()


# =====================================================================
# ПРОХОЖДЕНИЕ DISC
# =====================================================================

@router.callback_query(TestFlow.in_disc_test, F.data.startswith("disc_ans:"))
async def cb_disc_answer(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    admin_ids: list[int],
    db: Database,
    gemini_api_key: str | None,
) -> None:
    _, raw_block_idx, step, raw_opt_idx = callback.data.split(":")
    block_idx = int(raw_block_idx)
    opt_idx = int(raw_opt_idx)

    data = await state.get_data()
    current_block = data["block_index"]
    current_step = data["disc_step"]

    if block_idx != current_block or step != current_step:
        await callback.answer()
        return

    blocks = DISC_DATA["blocks"]

    if step == "most":
        await state.update_data(disc_step="least", current_most_idx=opt_idx)
        await safe_edit_text(
            callback.message,
            build_disc_block_text(current_block, "least", chosen_most_idx=opt_idx),
            reply_markup=disc_block_kb(current_block, "least", excluded_idx=opt_idx),
        )
        await callback.answer()
        return

    most_idx = data["current_most_idx"]
    most_trait = blocks[current_block]["options"][most_idx]["trait"]
    least_trait = blocks[current_block]["options"][opt_idx]["trait"]

    answers: list[dict[str, str]] = data["answers"]
    answers.append({"most": most_trait, "least": least_trait})
    next_block = current_block + 1

    if next_block < len(blocks):
        await state.update_data(
            block_index=next_block,
            disc_step="most",
            current_most_idx=None,
            answers=answers,
        )
        await safe_edit_text(
            callback.message,
            build_disc_block_text(next_block, "most"),
            reply_markup=disc_block_kb(next_block, "most"),
        )
        await callback.answer()
    else:
        result = calculate_disc(answers)
        await db.save_result(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            full_name=data["full_name"],
            test_type="DISC",
            result_code=result["code"],
            scales_data={
                "most": result["most"],
                "least": result["least"],
                "net": result["net"],
                "pct": result["pct"],
            },
        )

        user_text = format_disc_user_result(result)
        await state.clear()
        await safe_edit_text(callback.message, user_text, reply_markup=after_test_kb())
        await callback.answer("Тест завершён!")

        admin_text = format_disc_admin_report(
            full_name=data["full_name"],
            username=callback.from_user.username,
            user_id=callback.from_user.id,
            result=result,
        )
        await send_report_to_admins(bot, admin_ids, admin_text)

        ai_portrait = await generate_disc_ai_portrait(
            api_key=gemini_api_key,
            full_name=data["full_name"],
            result=result,
            blocks=blocks,
            answers=answers,
        )
        if ai_portrait:
            ai_header = (
                f"🤖 <b>ИИ-ПОРТРЕТ (DISC): {html.escape(data['full_name'])} "
                f"({result['code']})</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            )
            await send_report_to_admins(bot, admin_ids, ai_header + ai_portrait)


@router.callback_query(TestFlow.in_disc_test, F.data == "test:back")
async def cb_disc_back(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    current_block = data["block_index"]
    current_step = data["disc_step"]
    answers: list[dict[str, str]] = data["answers"]

    if current_step == "least":
        await state.update_data(disc_step="most", current_most_idx=None)
        await safe_edit_text(
            callback.message,
            build_disc_block_text(current_block, "most"),
            reply_markup=disc_block_kb(current_block, "most"),
        )
    elif current_block > 0:
        prev_block = current_block - 1
        if answers:
            answers.pop()
        await state.update_data(
            block_index=prev_block,
            disc_step="most",
            current_most_idx=None,
            answers=answers,
        )
        await safe_edit_text(
            callback.message,
            build_disc_block_text(prev_block, "most"),
            reply_markup=disc_block_kb(prev_block, "most"),
        )

    await callback.answer()


# =====================================================================
# ПРОХОЖДЕНИЕ LEADERSHIP (УПРАВЛЕНЧЕСКИЙ ПОТЕНЦИАЛ)
# =====================================================================

@router.callback_query(TestFlow.in_leadership_test, F.data.startswith("lead_ans:"))
async def cb_leadership_answer(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    admin_ids: list[int],
    db: Database,
    gemini_api_key: str | None,
) -> None:
    _, raw_q_idx, raw_opt_idx = callback.data.split(":")
    q_idx = int(raw_q_idx)
    opt_idx = int(raw_opt_idx)

    data = await state.get_data()
    current_idx = data["q_index"]

    if q_idx != current_idx:
        await callback.answer()
        return

    questions = LEADERSHIP_DATA["questions"]
    q = questions[current_idx]
    chosen_opt = q["options"][opt_idx]

    answers: list[dict] = data["answers"]
    answers.append({
        "scale": q["scale"],
        "score": chosen_opt["score"],
        "opt_idx": opt_idx,
    })
    next_idx = current_idx + 1

    if next_idx < len(questions):
        await state.update_data(q_index=next_idx, answers=answers)
        await safe_edit_text(
            callback.message,
            build_leadership_question_text(next_idx),
            reply_markup=leadership_question_kb(next_idx),
        )
        await callback.answer()
    else:
        result = calculate_leadership(answers)
        await db.save_result(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            full_name=data["full_name"],
            test_type="LEADERSHIP",
            result_code=result["code"],
            scales_data=result["scales"],
        )

        user_text = format_leadership_user_result(result)
        await state.clear()
        await safe_edit_text(callback.message, user_text, reply_markup=after_test_kb())
        await callback.answer("Тест завершён!")

        admin_text = format_leadership_admin_report(
            full_name=data["full_name"],
            username=callback.from_user.username,
            user_id=callback.from_user.id,
            result=result,
        )
        await send_report_to_admins(bot, admin_ids, admin_text)

        ai_portrait = await generate_leadership_ai_portrait(
            api_key=gemini_api_key,
            full_name=data["full_name"],
            result=result,
            questions=questions,
            answers=answers,
        )
        if ai_portrait:
            ai_header = (
                f"🤖 <b>ИИ-РАЗБОР (УПРАВЛЕНЧЕСКИЙ ПОТЕНЦИАЛ): "
                f"{html.escape(data['full_name'])}</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            )
            await send_report_to_admins(bot, admin_ids, ai_header + ai_portrait)


@router.callback_query(TestFlow.in_leadership_test, F.data == "test:back")
async def cb_leadership_back(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    current_idx = data["q_index"]
    answers: list[dict] = data["answers"]

    if current_idx > 0:
        prev_idx = current_idx - 1
        if answers:
            answers.pop()
        await state.update_data(q_index=prev_idx, answers=answers)
        await safe_edit_text(
            callback.message,
            build_leadership_question_text(prev_idx),
            reply_markup=leadership_question_kb(prev_idx),
        )
    await callback.answer()
