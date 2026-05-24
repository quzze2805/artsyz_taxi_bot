from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from config import POPULAR_PLACES

def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚖 Замовити таксі"), KeyboardButton(text="📋 Мої поїздки")],
            [KeyboardButton(text="🕒 Запланувати поїздку (Тестування)")],
            [KeyboardButton(text="🎁 Мої бонуси")],
            [KeyboardButton(text="💬 Підтримка")],
        ],
        resize_keyboard=True
    )

def main_menu_driver():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚖 Замовити таксі"), KeyboardButton(text="📋 Мої поїздки")],
            [KeyboardButton(text="🕒 Запланувати поїздку (Тестування)")],
            [KeyboardButton(text="🎁 Мої бонуси")],
            [KeyboardButton(text="💬 Підтримка")],
            [KeyboardButton(text="🚘 Кабінет водія")],
        ],
        resize_keyboard=True
    )

def contact_request():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Поділитися номером телефону", request_contact=True)],
            [KeyboardButton(text="⬅ Назад")]
        ],
        resize_keyboard=True
    )

def from_location_method():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Надіслати геопозицію", request_location=True)],
            [KeyboardButton(text="✏️ Написати адресу вручну")],
            [KeyboardButton(text="⬅ Назад")]
        ],
        resize_keyboard=True
    )

def to_location_method():
    buttons = []
    for label in POPULAR_PLACES:
        buttons.append([KeyboardButton(text=f"🏷 {label}")])
    buttons.append([KeyboardButton(text="✏️ Інша адреса")])
    buttons.append([KeyboardButton(text="⬅ Назад")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def confirm_order_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Підтвердити замовлення")],
            [KeyboardButton(text="💬 Коментар до замовлення")],
            [KeyboardButton(text="⬅ Змінити"), KeyboardButton(text="❌ Скасувати")]
        ],
        resize_keyboard=True
    )

def apply_discount_kb(has_discounts):
    if has_discounts:
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Підтвердити замовлення (зі знижкою 50%)")],
                [KeyboardButton(text="✅ Підтвердити замовлення (міжмісто, без знижки)")],
                [KeyboardButton(text="💬 Коментар до замовлення")],
                [KeyboardButton(text="⬅ Змінити"), KeyboardButton(text="❌ Скасувати")]
            ],
            resize_keyboard=True
        )
    return confirm_order_kb()
    if has_discounts:
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Підтвердити замовлення (зі знижкою 50%)")],
                [KeyboardButton(text="✅ Підтвердити замовлення (міжмісто, без знижки)")],
                [KeyboardButton(text="⬅ Змінити"), KeyboardButton(text="❌ Скасувати")]
            ],
            resize_keyboard=True
        )
    return confirm_order_kb()

def client_driver_found():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📞 Контакти водія")],
            [KeyboardButton(text="💬 Повідомлення водію")],
            [KeyboardButton(text="📡 Надіслати геопозицію"), KeyboardButton(text="❌ Скасувати поїздку")],
        ],
        resize_keyboard=True
    )

def client_planned_order_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔙 В головне меню")],
            [KeyboardButton(text="❌ Скасувати поїздку")]
        ],
        resize_keyboard=True
    )

def client_chat_active():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔕 Завершити чат")],
        ],
        resize_keyboard=True
    )

def client_after_arrived():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💬 Повідомлення водію")],
            [KeyboardButton(text="🏃 Вже йду"), KeyboardButton(text="⏳ Буду через 5 хв")],
            [KeyboardButton(text="📍 Я на місці")],
        ],
        resize_keyboard=True
    )

def rating_keyboard(order_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{i}⭐", callback_data=f"rate_{order_id}_{i}") for i in range(1, 6)]
        ]
    )

def request_location_kb(text="📍 Надіслати геопозицію"):
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
            [KeyboardButton(text="👥 Запросити друга")],
            [KeyboardButton(text="🔙 Назад")],
        ],
        resize_keyboard=True
    )

def driver_main():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔛 Розпочати зміну")],
            [KeyboardButton(text="🔚 Завершити зміну")],
            [KeyboardButton(text="📋 Мої замовлення")],
            [KeyboardButton(text="🔙 В головне меню")],
        ],
        resize_keyboard=True
    )

def driver_accept_order(order_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚕 Прийняти замовлення", callback_data=f"accept_{order_id}")],
            [InlineKeyboardButton(text="⛔ Відхилити", callback_data=f"decline_{order_id}")],
        ]
    )

def driver_order_actions(order_id, has_queue=False):
    keyboard = [
        [InlineKeyboardButton(text="💬 Повідомлення клієнту", callback_data=f"chat_{order_id}")],
        [InlineKeyboardButton(text="📍 Запитати гео клієнта", callback_data=f"req_loc_{order_id}")],
    ]
    if has_queue:
        keyboard.append([InlineKeyboardButton(text="❌ Скасувати наступне замовлення", callback_data=f"cancel_queued_{order_id}")])
    keyboard.extend([
        [InlineKeyboardButton(text="👋 Я на місці", callback_data=f"arrived_{order_id}")],
        [InlineKeyboardButton(text="🛑 Завершити поїздку", callback_data=f"finish_{order_id}")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def driver_chat_active():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔕 Завершити чат")]],
        resize_keyboard=True
    )

def client_queued_kb(order_id: int) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏳ Чекаю")],
            [KeyboardButton(text="❌ Скасувати замовлення (черга)")],
        ],
        resize_keyboard=True
    )

def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Додати водія")],
            [KeyboardButton(text="➖ Видалити водія")],
            [KeyboardButton(text="📋 Список водіїв")],
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="📈 Статистика водіїв")],
            [KeyboardButton(text="⚡️ Промо-акція")],
            [KeyboardButton(text="🚫 Заблокувати клієнта"), KeyboardButton(text="✅ Розблокувати клієнта")],
            [KeyboardButton(text="🔴 Завершити робочий день"), KeyboardButton(text="🟢 Розпочати робочий день")],
            [KeyboardButton(text="📢 Розсилка"), KeyboardButton(text="🔙 Вийти з адмінки")],
        ],
        resize_keyboard=True
    )

def searching_driver_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Скасувати замовлення")]],
        resize_keyboard=True
    )

def confirm_cancel_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Так, скасувати", callback_data=f"confirm_cancel_{order_id}")],
            [InlineKeyboardButton(text="❌ Ні", callback_data=f"decline_cancel_{order_id}")],
        ]
    )

def workday_closed_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📞 Зателефонувати диспетчеру")],
            [KeyboardButton(text="🔙 Повернутися в головне меню")],
        ],
        resize_keyboard=True
    )

def review_prompt_kb(order_id: int) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✍️ Залишити відгук"), KeyboardButton(text="⏭ Пропустити")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def skip_review_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⏭ Пропустити")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def driver_wait_time_kb(order_id: int) -> InlineKeyboardMarkup:
    minutes = [5, 10, 15, 20, 25, 30, 40, 50, 60]
    buttons = []
    row = []
    for i, m in enumerate(minutes, 1):
        row.append(InlineKeyboardButton(text=f"{m} хв", callback_data=f"wait_{order_id}_{m}"))
        if i % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def planned_time_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅ Назад")]],
        resize_keyboard=True
    )

def driver_eta_kb(order_id: int) -> InlineKeyboardMarkup:
    minutes = [5, 10, 15, 20, 25, 30, 40, 50, 60]
    buttons = []
    row = []
    for i, m in enumerate(minutes, 1):
        row.append(InlineKeyboardButton(text=f"{m} хв", callback_data=f"eta_{order_id}_{m}"))
        if i % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def driver_price_kb(order_id: int) -> InlineKeyboardMarkup:
    prices = [100, 120, 130, 140, 150, 170, 190, 200, 250, 300, 350]
    buttons = []
    row = []
    for i, p in enumerate(prices, 1):
        row.append(InlineKeyboardButton(text=f"{p} грн", callback_data=f"price_{order_id}_{p}"))
        if i % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    # Кнопка "Своя цена"
    buttons.append([InlineKeyboardButton(text="💬 Вказати свою ціну", callback_data=f"custom_price_{order_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def client_confirm_price_kb(order_id: int) -> InlineKeyboardMarkup:
    """Инлайн-кнопки для подтверждения клиентом цены поездки"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Підтвердити поїздку", callback_data=f"client_confirm_{order_id}")],
            [InlineKeyboardButton(text="❌ Скасувати поїздку", callback_data=f"client_cancel_{order_id}")]
        ]
    )

def main_menu_admin(is_driver=False):
    keyboard = [
        [KeyboardButton(text="🚖 Замовити таксі"), KeyboardButton(text="📋 Мої поїздки")],
        [KeyboardButton(text="🕒 Запланувати поїздку (Тестування)")],
        [KeyboardButton(text="🎁 Мої бонуси")],
        [KeyboardButton(text="💬 Підтримка")],
    ]
    if is_driver:
        keyboard.append([KeyboardButton(text="🚘 Кабінет водія")])
    keyboard.append([KeyboardButton(text="🔐 Адмін-панель")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def promo_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Включити промо")],
            [KeyboardButton(text="➖ Виключити промо")],
            [KeyboardButton(text="🔙 Назад в адмінку")]
        ],
        resize_keyboard=True
    )