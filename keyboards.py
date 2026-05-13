from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from config import POPULAR_PLACES

def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚖 Заказать такси"), KeyboardButton(text="📋 Мои поездки")],
            [KeyboardButton(text="🎁 Мои бонусы")],
            [KeyboardButton(text="💬 Поддержка")],
        ],
        resize_keyboard=True
    )

def contact_request():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Поделиться номером телефона", request_contact=True)],
            [KeyboardButton(text="⬅ Назад")]
        ],
        resize_keyboard=True
    )

def from_location_method():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Отправить геопозицию", request_location=True)],
            [KeyboardButton(text="✏️ Написать адрес вручную")],
            [KeyboardButton(text="⬅ Назад")]
        ],
        resize_keyboard=True
    )

def to_location_method():
    buttons = []
    for label in POPULAR_PLACES:
        buttons.append([KeyboardButton(text=f"🏷 {label}")])
    buttons.append([KeyboardButton(text="✏️ Другой адрес")])
    buttons.append([KeyboardButton(text="⬅ Назад")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def confirm_order_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Подтвердить заказ")],
            [KeyboardButton(text="⬅ Изменить"), KeyboardButton(text="❌ Отменить")]
        ],
        resize_keyboard=True
    )

def apply_discount_kb(has_discounts):
    if has_discounts:
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Подтвердить заказ (со скидкой 50%)")],
                [KeyboardButton(text="✅ Подтвердить заказ (межгород, без скидки)")],
                [KeyboardButton(text="⬅ Изменить"), KeyboardButton(text="❌ Отменить")]
            ],
            resize_keyboard=True
        )
    return confirm_order_kb()

def client_driver_found():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📞 Контакты водителя")],
            [KeyboardButton(text="💬 Сообщение водителю")],
            [KeyboardButton(text="📡 Отправить геопозицию"), KeyboardButton(text="❌ Отменить поездку")],
        ],
        resize_keyboard=True
    )

def client_chat_active():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔕 Завершить чат")],
        ],
        resize_keyboard=True
    )

def client_after_arrived():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💬 Сообщение водителю")],
            [KeyboardButton(text="🏃 Уже иду"), KeyboardButton(text="⏳ Буду через 5 мин")],
            [KeyboardButton(text="📍 Я на месте")],
        ],
        resize_keyboard=True
    )

def rating_keyboard(order_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{i}⭐", callback_data=f"rate_{order_id}_{i}") for i in range(1, 6)]
        ]
    )

def request_location_kb(text="📍 Отправить геопозицию"):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=text, request_location=True)]],
        resize_keyboard=True
    )

def back_only_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅ Назад")]],
        resize_keyboard=True
    )

def bonus_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Пригласить друга")],
            [KeyboardButton(text="🔙 Назад")],
        ],
        resize_keyboard=True
    )

# --- Водитель ---
def driver_main():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔛 Начать смену")],
            [KeyboardButton(text="🔚 Закончить смену")],
        ],
        resize_keyboard=True
    )

def driver_accept_order(order_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚕 Принять заказ", callback_data=f"accept_{order_id}")],
            [InlineKeyboardButton(text="⛔ Отклонить", callback_data=f"decline_{order_id}")],
        ]
    )

def driver_order_actions(order_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Сообщение клиенту", callback_data=f"chat_{order_id}")],
            [InlineKeyboardButton(text="📍 Запросить гео клиента", callback_data=f"req_loc_{order_id}")],
            [InlineKeyboardButton(text="🗺 Отправить гео клиенту", callback_data=f"send_loc_{order_id}")],
            [InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel_by_driver_{order_id}")],
            [InlineKeyboardButton(text="👋 Я на месте", callback_data=f"arrived_{order_id}")],
            [InlineKeyboardButton(text="🛑 Завершить поездку", callback_data=f"finish_{order_id}")],
        ]
    )

def driver_chat_active():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔕 Завершить чат")]],
        resize_keyboard=True
    )

# --- Админка ---
def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить водителя")],
            [KeyboardButton(text="➖ Удалить водителя")],
            [KeyboardButton(text="📋 Список водителей")],
            [KeyboardButton(text="🔴 Закончить рабочий день"), KeyboardButton(text="🟢 Включить рабочий день")],
            [KeyboardButton(text="🔙 Выйти из админки")],
        ],
        resize_keyboard=True
    )

def confirm_cancel_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, отменить", callback_data=f"confirm_cancel_{order_id}")],
            [InlineKeyboardButton(text="❌ Нет", callback_data=f"decline_cancel_{order_id}")],
        ]
    )

def review_prompt_kb(order_id: int) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✍️ Оставить отзыв"), KeyboardButton(text="⏭ Пропустить")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def skip_review_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⏭ Пропустить")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def searching_driver_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отменить заказ")]],
        resize_keyboard=True
    )

def workday_closed_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📞 Позвонить диспетчеру")],
            [KeyboardButton(text="🔙 Вернуться в главное меню")],
        ],
        resize_keyboard=True
    )