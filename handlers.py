import html
import logging
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from db import Database
from keyboards import (
    after_test_kb,
    cancel_only_kb,
    disc_block_kb,
    main_menu_kb,
    mbti_question_kb,
)
from scoring import (
    DISC_DATA,
    MBTI_DATA,
    calculate_disc,
    calculate_mbti,
    format_disc_admin_report,
    format_disc_user_result,
    format_mbti_admin_report,
    format_mbti_user_result,
    render_progress_bar,
)
from states import TestFlow

logger = logging.getLogger(__name__)
router = Router()

WELCOME_TEXT = (
    "👋 <b>Добро пожаловать в бот психологического тестирования!</b>\n\n"
    "Выберите тест, который хотите пройти:\n"
    "• <b>MBTI</b> — 70 вопросов, определяет ваш тип личности по 4 дихотомиям (E/I, S/N, T/F, J/P).\n"
    "• <b>DISC</b> — 24 блока по 4 утверждения, оценивает поведенческий профиль (D, I, S, C)."
)


async def safe_edit_text(message: Message, text: str, reply_markup=None) -> None:
    try:
        await message.edit_text(text=text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise


async def send_report_to_admins(bot: Bot, admin_ids: list[int], report_text: str) -> None:
    for admin_id in admin_ids:
        try:
            await bot.send_message(chat_id=admin_id, text=report_text)
        except Exception as e:
            logger.error("Не удалось отправить отчёт админу %s: %s", admin_id, e)


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


@router.callback_query(F.data.startswith("select_test:"))
async def cb_select_test(callback: CallbackQuery, state: FSMContext) -> None:
    test_type = callback.data.split(":")[1]
    test_name = "MBTI (70 вопросов)" if test_type == "mbti" else "DISC (24 блока)"

    await state.clear()
    await state.set_state(TestFlow.waiting_for_name)
    await state.update_data(selected_test=test_type)

    await safe_edit_text(
        callback.message,
        f"Вы выбрали тест <b>{test_name}</b>.\n\n"
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
        await state.update_data(
            full_name=full_name,
            q_index=0,
            answers=[],
        )
        q = MBTI_DATA["questions"][0]
        await message.answer(
            text=build_mbti_question_text(0),
            reply_markup=mbti_question_kb(0, q["options"]),
        )
    else:
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


@router.callback_query(TestFlow.in_mbti_test, F.data.startswith("mbti_ans:"))
async def cb_mbti_answer(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    admin_ids: list[int],
    db: Database,
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
        admin_text = format_mbti_admin_report(
            full_name=data["full_name"],
            username=callback.from_user.username,
            user_id=callback.from_user.id,
            result=result,
        )

        await state.clear()
        await safe_edit_text(callback.message, user_text, reply_markup=after_test_kb())
        await callback.answer("Тест завершён!")
        await send_report_to_admins(bot, admin_ids, admin_text)


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


@router.callback_query(TestFlow.in_disc_test, F.data.startswith("disc_ans:"))
async def cb_disc_answer(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    admin_ids: list[int],
    db: Database,
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
        admin_text = format_disc_admin_report(
            full_name=data["full_name"],
            username=callback.from_user.username,
            user_id=callback.from_user.id,
            result=result,
        )

        await state.clear()
        await safe_edit_text(callback.message, user_text, reply_markup=after_test_kb())
        await callback.answer("Тест завершён!")
        await send_report_to_admins(bot, admin_ids, admin_text)


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
