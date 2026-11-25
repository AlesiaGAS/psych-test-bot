from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🧠 Тест MBTI (70 вопросов)", callback_data="select_test:mbti")
    builder.button(text="📊 Тест DISC (24 блока)", callback_data="select_test:disc")
    builder.button(text="🚀 Управленческий потенциал (24 кейса)", callback_data="select_test:leadership")
    builder.adjust(1)
    return builder.as_markup()


def cancel_only_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="test:cancel")]
        ]
    )


def mbti_question_kb(q_index: int, options: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    labels = ["А", "Б"]
    for opt_idx, _ in enumerate(options):
        builder.button(
            text=f"Вариант {labels[opt_idx]}",
            callback_data=f"mbti_ans:{q_index}:{opt_idx}",
        )
    builder.adjust(2)

    nav_row = []
    if q_index > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="test:back"))
    nav_row.append(InlineKeyboardButton(text="❌ Отменить", callback_data="test:cancel"))
    builder.row(*nav_row)

    return builder.as_markup()


def disc_block_kb(
    block_index: int,
    step: str,
    excluded_idx: int | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for opt_idx in range(4):
        if excluded_idx is not None and opt_idx == excluded_idx:
            continue
        builder.button(
            text=f"{opt_idx + 1}",
            callback_data=f"disc_ans:{block_index}:{step}:{opt_idx}",
        )
    builder.adjust(4 if excluded_idx is None else 3)

    nav_row = []
    if block_index > 0 or step == "least":
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="test:back"))
    nav_row.append(InlineKeyboardButton(text="❌ Отменить", callback_data="test:cancel"))
    builder.row(*nav_row)

    return builder.as_markup()


def leadership_question_kb(q_index: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for opt_idx in range(4):
        builder.button(
            text=f"Вариант {opt_idx + 1}",
            callback_data=f"lead_ans:{q_index}:{opt_idx}",
        )
    builder.adjust(2)

    nav_row = []
    if q_index > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="test:back"))
    nav_row.append(InlineKeyboardButton(text="❌ Отменить", callback_data="test:cancel"))
    builder.row(*nav_row)

    return builder.as_markup()


def after_test_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Пройти другой тест", callback_data="test:menu")]
        ]
    )


def dossier_list_kb(candidates: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for c in candidates:
        name = c["full_name"][:28]
        count = c["tests_count"]
        builder.button(
            text=f"👤 {name} ({count}/3)",
            callback_data=f"dossier:view:{c['user_id']}",
        )
    builder.adjust(1)
    return builder.as_markup()


def dossier_card_kb(user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🤖 Сводный ИИ-портрет по всем тестам",
        callback_data=f"dossier:ai:{user_id}",
    )
    builder.button(
        text="⬅️ К списку кандидатов",
        callback_data="dossier:list",
    )
    builder.adjust(1)
    return builder.as_markup()
