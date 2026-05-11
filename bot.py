import asyncio
import json
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from config import BOT_TOKEN, LOGO_FILE_ID, SUPPORT_PHONE, SERVICE_NAME, ADMIN_IDS, TELEGRAM_CONTACT
from database import (init_db, add_order, get_order, accept_order,
                      set_driver_online, get_online_drivers,
                      get_driver_current_order, finish_order,
                      cancel_order, get_client_last_orders,
                      save_driver, get_driver, is_driver_allowed,
                      add_allowed_driver, remove_allowed_driver,
                      get_allowed_drivers_list, get_all_drivers)
from keyboards import *

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Словари состояний
user_state = {}              # клиентские шаги заказа
driver_reg_state = {}        # регистрация водителя
pending_client_geo = {}      # ожидание гео от клиента -> driver_id
pending_driver_geo = {}      # ожидание гео от водителя -> client_id
order_requests = {}          # {order_id: list of (chat_id, message_id)} для рассылки

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
async def return_to_main(message: types.Message):
    """Возвращает пользователя в главное меню (клиент)."""
    await message.answer("Вы в главном меню.", reply_markup=main_menu())

# ========== СТАРТ И ОБЩИЕ КОМАНДЫ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    text = (
        f"Добро пожаловать в <b>{SERVICE_NAME}</b> — ваш комфорт начинается здесь. ✨\n\n"
        f"Мы доставим вас в любую точку города быстро и безопасно. "
        f"Если удобнее сделать заказ голосом, звоните:\n📞 {SUPPORT_PHONE}\n"
        f"или через Telegram: {TELEGRAM_CONTACT}, отвечаем очень быстро."
    )
    if LOGO_FILE_ID and LOGO_FILE_ID != "СЮДА_FILE_ID_ЛОГОТИПА":
        await message.answer_photo(LOGO_FILE_ID, caption=text, parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")
    await message.answer("Что хотите сделать?", reply_markup=main_menu())

@dp.message(Command("id"))
async def cmd_id(message: types.Message):
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>", parse_mode="HTML")

# Временный хендлер для file_id (можно удалить)
@dp.message(F.photo)
async def get_photo_id(message: types.Message):
    file_id = message.photo[-1].file_id
    await message.reply(f"file_id вашей картинки:\n<code>{file_id}</code>", parse_mode="HTML")

# ========== АДМИН-ПАНЕЛЬ ==========
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return
    await message.answer("🔐 Админ-панель:", reply_markup=admin_menu())

# Обработчики админ-меню
@dp.message(F.text == "➕ Добавить водителя")
async def admin_add_driver_prompt(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    user_state[message.from_user.id] = {"step": "admin_enter_id"}
    await message.answer("Введите Telegram ID нового водителя (целое число):", reply_markup=ReplyKeyboardRemove())

@dp.message(lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_enter_id")
async def admin_enter_driver_id(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        driver_id = int(message.text.strip())
    except:
        await message.answer("Некорректный ID. Повторите ввод числом.")
        return
    if is_driver_allowed(driver_id):
        await message.answer("Этот водитель уже добавлен.", reply_markup=admin_menu())
        del user_state[message.from_user.id]
        return
    # Начинаем регистрацию данных водителя
    add_allowed_driver(driver_id)  # сразу добавляем в разрешённые
    driver_reg_state[driver_id] = {"step": "ask_name"}
    user_state[message.from_user.id] = {"step": "admin_await_driver_reg", "driver_id": driver_id}
    # Переключаемся на диалог с админом: говорим, что сейчас будем заполнять данные
    await message.answer(f"✅ Водитель {driver_id} добавлен в список. Теперь заполним его данные.\n"
                         f"Введите имя водителя (как оно будет показано клиентам):",
                         reply_markup=back_only_keyboard())

@dp.message(lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_await_driver_reg")
async def admin_driver_reg(message: types.Message):
    admin_id = message.from_user.id
    driver_id = user_state[admin_id]["driver_id"]
    if driver_id not in driver_reg_state:
        await message.answer("Ошибка состояния. Попробуйте заново.", reply_markup=admin_menu())
        del user_state[admin_id]
        return

    state = driver_reg_state[driver_id]
    if state["step"] == "ask_name":
        state["name"] = message.text.strip()
        state["step"] = "ask_phone"
        await message.answer("📞 Отправьте номер телефона водителя (вручную в формате +79...):")
    elif state["step"] == "ask_phone":
        state["phone"] = message.text.strip()
        state["step"] = "ask_car"
        await message.answer("🚗 Марка и модель авто:")
    elif state["step"] == "ask_car":
        state["car_model"] = message.text.strip()
        state["step"] = "ask_color"
        await message.answer("🎨 Цвет авто:")
    elif state["step"] == "ask_color":
        state["car_color"] = message.text.strip()
        state["step"] = "ask_plate"
        await message.answer("🔢 Госномер:")
    elif state["step"] == "ask_plate":
        state["car_plate"] = message.text.strip()
        save_driver(driver_id,
                    name=state["name"],
                    phone=state["phone"],
                    car_model=state["car_model"],
                    car_color=state["car_color"],
                    car_plate=state["car_plate"])
        del driver_reg_state[driver_id]
        del user_state[admin_id]
        await message.answer(f"✅ Профиль водителя {driver_id} сохранён.", reply_markup=admin_menu())

@dp.message(F.text == "➖ Удалить водителя")
async def admin_remove_driver_prompt(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    user_state[message.from_user.id] = {"step": "admin_delete_id"}
    await message.answer("Введите Telegram ID водителя для удаления:", reply_markup=ReplyKeyboardRemove())

@dp.message(lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_delete_id")
async def admin_delete_driver_id(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        driver_id = int(message.text.strip())
    except:
        await message.answer("Некорректный ID.")
        return
    if not is_driver_allowed(driver_id):
        await message.answer("Такого водителя нет в списке.", reply_markup=admin_menu())
    else:
        remove_allowed_driver(driver_id)
        await message.answer(f"Водитель {driver_id} удалён из разрешённых.", reply_markup=admin_menu())
    del user_state[message.from_user.id]

@dp.message(F.text == "📋 Список водителей")
async def admin_list_drivers(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    drivers = get_allowed_drivers_list()
    if not drivers:
        await message.answer("Нет ни одного водителя.")
        return
    text = "<b>Разрешённые водители:</b>\n\n"
    for d in drivers:
        text += f"ID: {d[0]}\nИмя: {d[1] or '?'}\nТелефон: {d[2] or '?'}\nАвто: {d[3] or '?'} {d[4] or '?'} ({d[5] or '?'})\n\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🔙 Выход")
async def exit_to_main(message: types.Message):
    if message.from_user.id in user_state:
        del user_state[message.from_user.id]
    await return_to_main(message)

# ========== ВОДИТЕЛЬСКИЙ КАБИНЕТ ==========
@dp.message(Command("driver"))
async def cmd_driver(message: types.Message):
    driver_id = message.from_user.id
    if not is_driver_allowed(driver_id):
        await message.answer("⛔ Вы не зарегистрированы как водитель.")
        return

    driver = get_driver(driver_id)
    if not driver or not driver[2]:  # нет телефона
        driver_reg_state[driver_id] = {"step": "ask_name"}
        await message.answer("👤 Введите ваше имя (как оно будет показано клиенту):")
        return

    await message.answer("🚘 Добро пожаловать в кабинет водителя!", reply_markup=driver_cabinet())

# Обработка регистрации водителя самим водителем (если нет профиля)
@dp.message(lambda msg: msg.from_user.id in driver_reg_state)
async def driver_self_registration(message: types.Message):
    driver_id = message.from_user.id
    state = driver_reg_state[driver_id]

    if state["step"] == "ask_name":
        state["name"] = message.text.strip()
        state["step"] = "ask_phone"
        await message.answer("📞 Отправьте ваш номер телефона (кнопкой ниже или введите вручную в формате +79...)",
                             reply_markup=ReplyKeyboardMarkup(
                                 keyboard=[[KeyboardButton(text="📱 Поделиться номером", request_contact=True)]],
                                 resize_keyboard=True
                             ))
    elif state["step"] == "ask_phone":
        phone = None
        if message.contact:
            phone = message.contact.phone_number
        else:
            text = message.text.strip()
            if text.startswith("+") and len(text) >= 10:
                phone = text
            else:
                await message.answer("⚠️ Пожалуйста, отправьте номер через кнопку или введите в формате +79XXXXXXXXX")
                return
        state["phone"] = phone
        state["step"] = "ask_car"
        await message.answer("🚗 Введите марку и модель автомобиля (например: Toyota Camry):", reply_markup=ReplyKeyboardRemove())
    elif state["step"] == "ask_car":
        state["car_model"] = message.text.strip()
        state["step"] = "ask_color"
        await message.answer("🎨 Введите цвет автомобиля:")
    elif state["step"] == "ask_color":
        state["car_color"] = message.text.strip()
        state["step"] = "ask_plate"
        await message.answer("🔢 Введите государственный номер автомобиля (например: A123BC):")
    elif state["step"] == "ask_plate":
        state["car_plate"] = message.text.strip()
        save_driver(driver_id,
                    name=state["name"],
                    phone=state["phone"],
                    car_model=state["car_model"],
                    car_color=state["car_color"],
                    car_plate=state["car_plate"])
        del driver_reg_state[driver_id]
        await message.answer("✅ Регистрация завершена! Теперь вы можете принимать заказы.", reply_markup=driver_cabinet())

# Водительские действия в кабинете
@dp.message(F.text == "🔛 Начать смену")
async def start_shift(message: types.Message):
    driver_id = message.from_user.id
    if not is_driver_allowed(driver_id):
        await message.answer("⛔ Вы не водитель.")
        return
    set_driver_online(driver_id, True)
    await message.answer("✅ Вы на смене! Ожидайте заказы.", reply_markup=driver_cabinet())

@dp.message(F.text == "🔚 Закончить смену")
async def end_shift(message: types.Message):
    driver_id = message.from_user.id
    if not is_driver_allowed(driver_id):
        return
    set_driver_online(driver_id, False)
    await message.answer("🛑 Смена завершена.", reply_markup=driver_cabinet())

@dp.message(F.text == "👤 Мой профиль")
async def driver_profile(message: types.Message):
    driver_id = message.from_user.id
    driver = get_driver(driver_id)
    if not driver:
        await message.answer("Профиль не найден.")
        return
    text = (
        f"👤 <b>Ваш профиль:</b>\n"
        f"Имя: {driver[1]}\n"
        f"Телефон: {driver[2]}\n"
        f"Авто: {driver[3]} {driver[4]}\n"
        f"Госномер: {driver[5]}"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "📋 Моя статистика")
async def driver_stats(message: types.Message):
    driver_id = message.from_user.id
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*), AVG(rating) FROM orders WHERE driver_id=? AND status='finished'", (driver_id,))
    row = c.fetchone()
    conn.close()
    total = row[0] if row[0] else 0
    avg = f"{row[1]:.1f}" if row[1] else "нет оценок"
    await message.answer(f"📊 Выполнено заказов: {total}\n⭐ Средний рейтинг: {avg}")

@dp.message(F.text == "🔙 Выход")
async def driver_exit(message: types.Message):
    await return_to_main(message)

# ========== КЛИЕНТСКАЯ ЛОГИКА ЗАКАЗА (без изменений, но с умной рассылкой) ==========
# ... далее код полностью повторяет предыдущую версию клиентской части, НО ...
# функция confirm_order_client будет изменена для сохранения order_requests и последующего редактирования сообщений.
# А accept_order_handler будет обновлён для обработки order_requests.

# Я скопирую все оставшиеся обработчики из последней рабочей версии, но с двумя изменениями в confirm_order_client и accept_order_handler.

# ====== КЛИЕНТ: ШАГИ ЗАКАЗА ======
@dp.message(F.text == "🚖 Заказать такси")
async def start_order(message: types.Message):
    user_id = message.from_user.id
    await message.answer(
        "Для оформления заказа, пожалуйста, подтвердите ваш номер телефона. "
        "Это нужно, чтобы водитель мог связаться с вами.",
        reply_markup=contact_request()
    )
    user_state[user_id] = {"step": "get_phone"}

@dp.message(F.text == "💬 Поддержка")
async def support(message: types.Message):
    await message.answer(f"📞 Свяжитесь с диспетчером: {SUPPORT_PHONE}\n💬 Или напишите в Telegram: {TELEGRAM_CONTACT}")

@dp.message(F.contact)
async def contact_received(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_state or user_state[user_id].get("step") != "get_phone":
        return
    phone = message.contact.phone_number
    user_state[user_id] = {"phone": phone, "step": "from_address"}
    await message.answer(
        "📍 <b>Откуда вас забрать?</b>\nМожете отправить геопозицию или написать адрес.",
        parse_mode="HTML",
        reply_markup=from_location_method()
    )

@dp.message(F.text == "✏️ Написать адрес вручную")
async def manual_from(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_state:
        return
    user_state[user_id]["step"] = "waiting_from_text"
    await message.answer("Напишите адрес подачи (например: ул. Центральная, 5 или «Магнит»).",
                         reply_markup=back_only_keyboard())

@dp.message(lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "waiting_from_text")
async def get_from_text(message: types.Message):
    user_id = message.from_user.id
    user_state[user_id]["from_address"] = message.text
    user_state[user_id]["from_lat"] = None
    user_state[user_id]["from_lon"] = None
    user_state[user_id]["step"] = "to_address"
    await message.answer(f"Адрес подачи сохранён: «{message.text}»")
    await ask_destination(message)

async def ask_destination(message: types.Message):
    await message.answer(
        "🏁 <b>Куда едем?</b>\nВыберите популярное место или укажите свой вариант.",
        parse_mode="HTML",
        reply_markup=to_location_method()
    )

@dp.message(lambda msg: msg.text and msg.text.startswith("🏷 "))
async def popular_place(message: types.Message):
    user_id = message.from_user.id
    place_name = message.text[2:].strip()
    if user_id not in user_state:
        return
    user_state[user_id]["to_address"] = place_name
    user_state[user_id]["step"] = "confirm"
    await message.answer(f"Выбрано: {place_name}")
    await confirm_order_step(message)

@dp.message(F.text == "✏️ Другой адрес")
async def manual_to(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_state:
        return
    user_state[user_id]["step"] = "waiting_to_text"
    await message.answer("Напишите адрес или ориентир назначения.",
                         reply_markup=back_only_keyboard())

@dp.message(lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "waiting_to_text")
async def get_to_text(message: types.Message):
    user_id = message.from_user.id
    user_state[user_id]["to_address"] = message.text
    user_state[user_id]["step"] = "confirm"
    await confirm_order_step(message)

async def confirm_order_step(message: types.Message):
    user_id = message.from_user.id
    state = user_state.get(user_id)
    if not state:
        return
    phone = state.get("phone", "не указан")
    from_addr = state.get("from_address", "неизвестно")
    to_addr = state.get("to_address", "не указан")
    summary = (
        f"📋 <b>Ваш заказ:</b>\n"
        f"📍 Откуда: {from_addr}\n"
        f"🏁 Куда: {to_addr}\n"
        f"📞 Телефон: {phone}\n\n"
        f"Всё верно?"
    )
    state["step"] = "confirm"
    await message.answer(summary, parse_mode="HTML", reply_markup=confirm_order_kb())

# НОВАЯ ВЕРСИЯ confirm_order_client
@dp.message(F.text == "✅ Подтвердить заказ")
async def confirm_order_client(message: types.Message):
    user_id = message.from_user.id
    state = user_state.pop(user_id, None)
    if not state:
        return
    order_id = add_order(
        client_id=user_id,
        from_address=state["from_address"],
        from_lat=state.get("from_lat"),
        from_lon=state.get("from_lon"),
        to_address=state.get("to_address"),
        phone=state.get("phone")
    )
    online = get_online_drivers()
    if not online:
        await message.answer("😔 К сожалению, сейчас нет свободных водителей. Попробуйте позже или позвоните диспетчеру.", reply_markup=main_menu())
        return

    # Работаем с базой
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    order = get_order(order_id)

    # Сохраняем список (chat_id, message_id) для последующего обновления
    msg_list = []
    for driver_id in online:
        try:
            driver_info_msg = (
                f"🔔 <b>Новый заказ!</b>\n"
                f"📍 Откуда: {state['from_address']}\n"
                f"🏁 Куда: {state.get('to_address')}\n"
                f"📞 Клиент: {state.get('phone')}\n"
                f"ID заказа: {order_id}"
            )
            sent_msg = await bot.send_message(driver_id, driver_info_msg, parse_mode="HTML",
                                              reply_markup=driver_accept_order(order_id))
            msg_list.append((driver_id, sent_msg.message_id))
            if state.get("from_lat") is not None and state.get("from_lon") is not None:
                await bot.send_location(driver_id,
                                        latitude=state["from_lat"],
                                        longitude=state["from_lon"])
        except Exception as e:
            logging.error(f"Failed to notify driver {driver_id}: {e}")
    order_requests[order_id] = msg_list
    conn.commit()
    conn.close()
    await message.answer("⏳ Ищем ближайший автомобиль...", reply_markup=main_menu())

# НОВЫЙ accept_order_handler
@dp.callback_query(lambda c: c.data.startswith("accept_"))
async def accept_order_handler(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    order_id = int(callback.data.split("_")[1])
    order = get_order(order_id)
    if not order or order[3] != 'searching':
        await callback.answer("Заказ уже не актуален.", show_alert=True)
        await callback.message.delete()
        return

    # Атомарно принимаем
    driver = get_driver(driver_id)
    if not driver:
        await callback.answer("Ваш профиль водителя не заполнен.", show_alert=True)
        return
    driver_info = {
        "name": driver[1] or callback.from_user.full_name,
        "car": f"{driver[3] or '?'} {driver[4] or '?'}",
        "plate": driver[5] or "не указан",
        "phone": driver[2] or "не указан"
    }
    driver_info_json = json.dumps(driver_info)
    accept_order(order_id, driver_id, driver_info_json)

    # Уведомляем клиента
    client_id = order[1]
    client_msg = (
        f"🚖 <b>Водитель найден!</b>\n"
        f"Имя: {driver_info['name']}\n"
        f"Авто: {driver_info['car']}\n"
        f"Номер: {driver_info['plate']}\n\n"
        f"Ожидаемое время подачи: ~5 минут."
    )
    try:
        await bot.send_message(client_id, client_msg, parse_mode="HTML", reply_markup=client_driver_found())
    except Exception as e:
        logging.error(f"Notify client {client_id}: {e}")

    # Обновляем сообщения всем водителям из рассылки
    msgs = order_requests.pop(order_id, [])
    for chat_id, msg_id in msgs:
        try:
            if chat_id == driver_id:
                # Принявший водитель
                new_text = (
                    f"✅ Вы приняли заказ #{order_id}\n"
                    f"📍 Адрес подачи: {order[4]}\n🏁 Куда: {order[7]}\n📞 Клиент: {order[8]}"
                )
                await bot.edit_message_text(
                    chat_id=chat_id, message_id=msg_id,
                    text=new_text,
                    reply_markup=driver_order_actions(order_id)
                )
            else:
                # Остальные
                await bot.edit_message_text(
                    chat_id=chat_id, message_id=msg_id,
                    text=f"🔔 Заказ #{order_id}\n📍 Откуда: {order[4]}\n🏁 Куда: {order[5]}\n"
                         f"✅ Принят водителем: {driver_info['name']} ({driver_info['car']}, {driver_info['plate']})",
                    reply_markup=None
                )
        except Exception as e:
            logging.warning(f"Не удалось обновить сообщение {msg_id} у {chat_id}: {e}")

    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("decline_"))
async def decline_order_handler(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    order_id = int(callback.data.split("_")[1])
    order = get_order(order_id)
    if not order or order[3] != 'searching':
        await callback.answer("Заказ уже не актуален.", show_alert=True)
    await callback.message.delete()
    await callback.answer("Вы отклонили заказ.")

# Остальные обработчики (гео, завершение, быстрые ответы, оценка, история) оставляем из предыдущей версии без изменений.
# Вставим их ниже.
# ... (скопировано из последнего рабочего bot.py)
# ========== ГЕОЛОКАЦИЯ ==========
@dp.message(F.location)
async def location_handler(message: types.Message):
    user_id = message.from_user.id

    if user_id in pending_client_geo:
        driver_id = pending_client_geo.pop(user_id)
        try:
            await message.copy_to(driver_id)
            await bot.send_message(driver_id, "📍 Клиент передал свою геопозицию выше.")
        except Exception as e:
            logging.error(f"Failed to copy location to driver {driver_id}: {e}")
            await message.answer("❌ Не удалось отправить геопозицию водителю.", reply_markup=client_driver_found())
            return
        await message.answer("✅ Геопозиция отправлена водителю.", reply_markup=client_driver_found())
        return

    if user_id in pending_driver_geo:
        client_id = pending_driver_geo.pop(user_id)
        try:
            await message.copy_to(client_id)
            await bot.send_message(client_id, "📍 Водитель передаёт свою геопозицию выше.")
        except Exception as e:
            logging.error(f"Failed to copy location to client {client_id}: {e}")
            await message.answer("❌ Не удалось отправить геопозицию клиенту.", reply_markup=driver_cabinet())
            return
        await message.answer("✅ Геопозиция отправлена клиенту.", reply_markup=driver_order_actions(get_driver_current_order(user_id)))
        return

    if user_id not in user_state or user_state[user_id].get("step") not in ("from_address", "waiting_from_text"):
        return
    lat = message.location.latitude
    lon = message.location.longitude
    user_state[user_id]["from_lat"] = lat
    user_state[user_id]["from_lon"] = lon
    user_state[user_id]["from_address"] = f"📍 точка на карте ({lat:.5f}, {lon:.5f})"
    user_state[user_id]["step"] = "to_address"
    await message.answer("Геопозиция получена!")
    await ask_destination(message)

# ====== КЛИЕНТ: АКТИВНЫЙ ЗАКАЗ ======
@dp.message(F.text == "📞 Контакты водителя")
async def show_driver_contacts(message: types.Message):
    await message.answer(
        "📞 Телефон: +380 75 443 67 57\n"
        "💬 Telegram: @taxi_artsyz",
        reply_markup=client_driver_found()
    )

@dp.message(F.text == "📡 Отправить геопозицию")
async def client_send_geo_prompt(message: types.Message):
    client_id = message.from_user.id
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute("SELECT id, driver_id FROM orders WHERE client_id=? AND status='accepted' ORDER BY id DESC LIMIT 1", (client_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        await message.answer("Нет активного заказа.")
        return
    order_id, driver_id = row
    pending_client_geo[client_id] = driver_id
    await message.answer(
        "📡 Отправьте ваше текущее местоположение (геопозицию), нажав на кнопку ниже.",
        reply_markup=request_location_kb()
    )

@dp.message(F.text == "❌ Отменить поездку")
async def client_cancel_ride(message: types.Message):
    client_id = message.from_user.id
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute("SELECT id, driver_id FROM orders WHERE client_id=? AND status='accepted' ORDER BY id DESC LIMIT 1", (client_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        await message.answer("Нет активного заказа для отмены.")
        return
    order_id, driver_id = row
    cancel_order(order_id)
    try:
        await bot.send_message(driver_id, f"❌ Клиент отменил поездку (заказ #{order_id}).")
    except:
        pass
    await message.answer("🚫 Поездка отменена.", reply_markup=main_menu())
    pending_client_geo.pop(client_id, None)
    pending_driver_geo.pop(driver_id, None)

# ====== ВОДИТЕЛЬ: ДЕЙСТВИЯ ПО ЗАКАЗУ ======
@dp.callback_query(lambda c: c.data.startswith("req_loc_"))
async def request_client_location(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    order_id = int(callback.data.split("_")[2])
    order = get_order(order_id)
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    client_id = order[1]
    pending_client_geo[client_id] = driver_id
    await bot.send_message(client_id,
        "📍 Водитель запрашивает ваше местоположение, чтобы быстро вас найти.\n"
        "Пожалуйста, отправьте геопозицию, нажав на кнопку ниже.",
        reply_markup=request_location_kb())
    await callback.answer("Клиенту отправлен запрос геолокации.")

@dp.callback_query(lambda c: c.data.startswith("send_loc_"))
async def send_geo_to_client(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    order_id = int(callback.data.split("_")[2])
    order = get_order(order_id)
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    client_id = order[1]
    pending_driver_geo[driver_id] = client_id
    await bot.send_message(driver_id,
        "🗺 Отправьте вашу геопозицию (или включите трансляцию), и она будет переслана клиенту.\n"
        "Нажмите кнопку ниже, чтобы отправить текущее местоположение.",
        reply_markup=request_location_kb("📍 Отправить мою геопозицию"))
    await callback.answer("Отправьте геопозицию, она будет передана клиенту.")

@dp.callback_query(lambda c: c.data.startswith("arrived_"))
async def driver_arrived(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    order_id = int(callback.data.split("_")[1])
    order = get_order(order_id)
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    client_id = order[1]
    await bot.send_message(client_id,
        "🚕 <b>Водитель на месте!</b>",
        parse_mode="HTML",
        reply_markup=client_after_arrived())
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛑 Завершить поездку", callback_data=f"finish_{order_id}")]
        ]
    ))
    await callback.answer("Клиент уведомлён.")

@dp.callback_query(lambda c: c.data.startswith("finish_"))
async def driver_finish(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    order_id = int(callback.data.split("_")[1])
    order = get_order(order_id)
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    finish_order(order_id)
    client_id = order[1]
    await bot.send_message(client_id,
        "🏁 <b>Поездка завершена.</b> Спасибо, что выбрали нас!",
        parse_mode="HTML",
        reply_markup=main_menu())
    await bot.send_message(client_id,
        "Оцените поездку:",
        reply_markup=rating_keyboard(order_id))
    await callback.message.edit_text("Поездка завершена. Ожидайте новый заказ.")
    await callback.answer()
    pending_client_geo.pop(client_id, None)
    pending_driver_geo.pop(driver_id, None)

# ========== БЫСТРЫЕ ОТВЕТЫ КЛИЕНТА ==========
@dp.message(F.text.in_(["🏃 Уже иду", "⏳ Буду через 5 мин", "📍 Я на месте"]))
async def client_fast_reply(message: types.Message):
    client_id = message.from_user.id
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute("SELECT id, driver_id FROM orders WHERE client_id=? AND status='accepted' ORDER BY id DESC LIMIT 1", (client_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        await message.answer("Нет активного заказа.")
        return
    order_id, driver_id = row
    try:
        await bot.send_message(driver_id, f"📩 Сообщение от клиента (заказ #{order_id}): «{message.text}»")
        await message.answer("✅ Водитель получил ваше сообщение.")
    except Exception as e:
        logging.error(f"Failed to forward fast reply to driver {driver_id}: {e}")
        await message.answer("❌ Не удалось отправить сообщение водителю.")

# ========== ОЦЕНКА ==========
@dp.callback_query(lambda c: c.data.startswith("rate_"))
async def rate_order(callback: types.CallbackQuery):
    _, order_id, stars = callback.data.split("_")
    order_id = int(order_id)
    stars = int(stars)
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute('UPDATE orders SET rating=? WHERE id=?', (stars, order_id))
    conn.commit()
    conn.close()
    await callback.message.edit_text(f"Спасибо! Вы поставили оценку {stars} {'⭐'*stars}")
    await callback.answer()

# ========== ИСТОРИЯ ==========
@dp.message(F.text == "📋 Мои поездки")
async def show_history(message: types.Message):
    orders = get_client_last_orders(message.from_user.id)
    if not orders:
        await message.answer("У вас ещё нет поездок.", reply_markup=main_menu())
        return
    text = "<b>Последние поездки:</b>\n\n"
    for o in orders:
        rating_value = o[12]
        if rating_value is not None:
            rating_value = int(rating_value)
        rating_str = f" {'⭐'*rating_value}" if rating_value else ""
        created_date = o[10][:10] if o[10] else "?"
        text += (f"🚕 {created_date}\n📍 {o[4]} → {o[7]}\n"
                 f"Статус: {o[3]}{rating_str}\n\n")
    await message.answer(text, parse_mode="HTML")

# ========== ОБРАБОТКА НАЗАД ==========
@dp.message(F.text == "⬅ Назад")
async def go_back(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_state:
        await message.answer("Вы не находитесь в процессе заказа.", reply_markup=main_menu())
        return
    step = user_state[user_id].get("step")

    if step in ("get_phone",):
        del user_state[user_id]
        await message.answer("Оформление заказа отменено.", reply_markup=main_menu())
    elif step in ("from_address", "waiting_from_text"):
        user_state[user_id]["step"] = "get_phone"
        await message.answer("Хорошо, давайте уточним ваш номер телефона.",
                             reply_markup=contact_request())
    elif step in ("to_address", "waiting_to_text"):
        user_state[user_id]["step"] = "from_address"
        user_state[user_id].pop("to_address", None)
        await message.answer("📍 <b>Откуда вас забрать?</b>\nМожете отправить геопозицию или написать адрес.",
                             parse_mode="HTML", reply_markup=from_location_method())
    elif step == "confirm":
        user_state[user_id]["step"] = "to_address"
        user_state[user_id].pop("to_address", None)
        await message.answer("🏁 <b>Куда едем?</b>\nВыберите популярное место или укажите свой вариант.",
                             parse_mode="HTML", reply_markup=to_location_method())
    else:
        await message.answer("Неизвестный этап. Возвращаемся в главное меню.", reply_markup=main_menu())
        if user_id in user_state:
            del user_state[user_id]

@dp.message(F.text == "⬅ Изменить")
async def change_order(message: types.Message):
    await go_back(message)

# ========== ЗАПУСК ==========
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())