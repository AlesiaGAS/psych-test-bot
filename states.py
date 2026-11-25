from aiogram.fsm.state import State, StatesGroup


class TestFlow(StatesGroup):
    waiting_for_name = State()
    in_mbti_test = State()
    in_disc_test = State()
    in_leadership_test = State()
