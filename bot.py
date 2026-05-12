import asyncio
import json
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from config import BOT_TOKEN, LOGO_FILE_ID, SUPPORT_PHONE, SERVICE_NAME, ADMIN_IDS, TELEGRAM_CONTACT
from database import (init_db, add_order, get_order, accept_order,
                      set_driver_online, get_online_drivers, get_driver_current_order,
                      finish_order, cancel_order, get_client_last_orders,
                      save_driver, get_driver, is_driver_allowed,
                      add_allowed_driver, remove_allowed_driver, get_all_drivers,
                      get_allowed_drivers_list,
                      get_loyalty, increment_rides, use_discount,
                      save_referral, complete_referral)
from keyboards import *

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Глобальные состояния
user_state = {}               # клиентский заказ
driver_reg_state = {}         # регистрация водителя
pending_client_geo = {}       # ожидание гео от клиента
pending_driver_geo = {}       # ожидание гео от водителя
chat_sessions = {}            # user_id -> (target_id, role)

# ========== Общие команды ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref"):
        try:
            referrer_id = int(args[1][3:])
            referred_id = message.from_user.id
            if referrer_id != referred_id:
                save_referral(referrer_id, referred_id)
        except:
            pass

    text = (
        f"Добро пожаловать в <b>{SERVICE_NAME}</b> — ваш комфорт начинается здесь. ✨\n\n"
        f"Мы доставим вас в любую точку города быстро и безопасно.\n"
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

# ========== Админ-панель ==========
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("🔐 Админ-панель:", reply_markup=admin_menu())

@dp.message(F.text == "➕ Добавить водителя")
async def admin_add_driver_prompt(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    user_state[message.from_user.id] = {"step": "admin_enter_driver_id"}
    await message.answer("Введите Telegram ID водителя:")

@dp.message(lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_enter_driver_id")
async def admin_enter_driver_id(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        driver_id = int(message.text.strip())
    except:
        await message.answer("Некорректный ID. Отмена.")
        del user_state[message.from_user.id]
        return

    if is_driver_allowed(driver_id):
        await message.answer("Этот водитель уже добавлен.")
    else:
        add_allowed_driver(driver_id)
        await message.answer(f"✅ Водитель {driver_id} добавлен. Попросите его выполнить /driver и зарегистрироваться.")
    del user_state[message.from_user.id]

@dp.message(F.text == "➖ Удалить водителя")
async def admin_remove_driver_prompt(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    user_state[message.from_user.id] = {"step": "admin_remove_enter_id"}
    await message.answer("Введите Telegram ID водителя для удаления:")

@dp.message(lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_remove_enter_id")
async def admin_remove_enter_id(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        driver_id = int(message.text.strip())
    except:
        await message.answer("Некорректный ID. Отмена.")
        del user_state[message.from_user.id]
        return
    remove_allowed_driver(driver_id)
    await message.answer(f"✅ Водитель {driver_id} удалён из системы.")
    del user_state[message.from_user.id]

@dp.message(F.text == "📋 Список водителей")
async def admin_list_drivers(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    allowed_ids = get_allowed_drivers_list()
    if not allowed_ids:
        await message.answer("Нет добавленных водителей.")
        return
    text = "📋 <b>Водители:</b>\n\n"
    for d_id in allowed_ids:
        driver = get_driver(d_id)
        if driver:
            text += f"ID: {driver[0]}\nИмя: {driver[1] or '?'}\nТелефон: {driver[2] or '?'}\nАвто: {driver[3] or '?'} {driver[4] or '?'} ({driver[5] or '?'})\n\n"
        else:
            text += f"ID: {d_id} (не зарегистрирован)\n\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🔙 Выйти из админки")
async def admin_exit(message: types.Message):
    await message.answer("Вы вышли из админ-панели.", reply_markup=main_menu())

# ========== Кабинет водителя ==========
@dp.message(Command("driver"))
async def cmd_driver(message: types.Message):
    driver_id = message.from_user.id
    if not is_driver_allowed(driver_id):
        await message.answer("⛔ У вас нет доступа к функциям водителя.")
        return
    driver = get_driver(driver_id)
    if driver and driver[2] is not None:
        await message.answer("🚘 Добро пожаловать в кабинет водителя!", reply_markup=driver_main())
        return
    driver_reg_state[driver_id] = {"step": "ask_name"}
    await message.answer("👤 Введите ваше имя (как оно будет показано клиенту):")

@dp.message(lambda msg: msg.from_user.id in driver_reg_state)
async def driver_registration(message: types.Message):
    driver_id = message.from_user.id
    state = driver_reg_state[driver_id]
    if state["step"] == "ask_name":
        state["name"] = message.text.strip()
        state["step"] = "ask_phone"
        await message.answer("📞 Отправьте ваш номер телефона (кнопкой ниже или введите вручную в формате +79...)",
                             reply_markup=ReplyKeyboardMarkup(
                                 keyboard=[[KeyboardButton(text="📱 Поделиться номером", request_contact=True)]],
                                 resize_keyboard=True))
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
        save_driver(driver_id, name=state["name"], phone=state["phone"],
                    car_model=state["car_model"], car_color=state["car_color"],
                    car_plate=state["car_plate"])
        del driver_reg_state[driver_id]
        await message.answer("✅ Регистрация завершена! Теперь вы можете принимать заказы.", reply_markup=driver_main())

@dp.message(F.text == "🔛 Начать смену")
async def start_shift(message: types.Message):
    if not is_driver_allowed(message.from_user.id):
        return
    set_driver_online(message.from_user.id, True)
    await message.answer("✅ Вы на смене! Ожидайте заказы.", reply_markup=driver_main())

@dp.message(F.text == "🔚 Закончить смену")
async def end_shift(message: types.Message):
    if not is_driver_allowed(message.from_user.id):
        return
    set_driver_online(message.from_user.id, False)
    await message.answer("🛑 Смена завершена.", reply_markup=main_menu())

# ========== Клиентский заказ ==========
@dp.message(F.text == "🚖 Заказать такси")
async def start_order(message: types.Message):
    user_state[message.from_user.id] = {"step": "get_phone"}
    await message.answer(
        "Для оформления заказа, пожалуйста, подтвердите ваш номер телефона.",
        reply_markup=contact_request()
    )

@dp.message(F.text == "💬 Поддержка")
async def support(message: types.Message):
    await message.answer(f"📞 Свяжитесь с диспетчером: {SUPPORT_PHONE}\n💬 Или напишите в Telegram: {TELEGRAM_CONTACT}")

@dp.message(F.contact)
async def contact_received(message: types.Message):
    uid = message.from_user.id
    if uid not in user_state or user_state[uid].get("step") != "get_phone":
        return
    user_state[uid] = {"phone": message.contact.phone_number, "step": "from_address"}
    await message.answer("📍 <b>Откуда вас забрать?</b>\nМожете отправить геопозицию или написать адрес.",
                         parse_mode="HTML", reply_markup=from_location_method())

@dp.message(F.text == "✏️ Написать адрес вручную")
async def manual_from(message: types.Message):
    uid = message.from_user.id
    if uid not in user_state:
        return
    user_state[uid]["step"] = "waiting_from_text"
    await message.answer("Напишите адрес подачи:", reply_markup=back_only_keyboard())

@dp.message(lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "waiting_from_text")
async def get_from_text(message: types.Message):
    uid = message.from_user.id
    user_state[uid]["from_address"] = message.text
    user_state[uid]["from_lat"] = user_state[uid]["from_lon"] = None
    user_state[uid]["step"] = "to_address"
    await message.answer(f"Адрес подачи: «{message.text}»")
    await ask_destination(message)

@dp.message(F.location)
async def location_handler(message: types.Message):
    uid = message.from_user.id
    # пересылка гео
    if uid in pending_client_geo:
        driver_id = pending_client_geo.pop(uid)
        try:
            await message.copy_to(driver_id)
            await bot.send_message(driver_id, "📍 Клиент передал свою геопозицию.")
        except:
            await message.answer("❌ Не удалось отправить геопозицию водителю.")
        else:
            await message.answer("✅ Геопозиция отправлена водителю.", reply_markup=client_driver_found())
        return
    if uid in pending_driver_geo:
        client_id = pending_driver_geo.pop(uid)
        try:
            await message.copy_to(client_id)
            await bot.send_message(client_id, "📍 Водитель передаёт свою геопозицию.")
        except:
            await message.answer("❌ Не удалось отправить геопозицию клиенту.")
        else:
            await message.answer("✅ Геопозиция отправлена клиенту.", reply_markup=driver_order_actions(get_driver_current_order(uid)))
        return
    # адрес подачи
    if uid in user_state and user_state[uid].get("step") in ("from_address", "waiting_from_text"):
        lat, lon = message.location.latitude, message.location.longitude
        user_state[uid]["from_lat"], user_state[uid]["from_lon"] = lat, lon
        user_state[uid]["from_address"] = f"📍 точка на карте ({lat:.5f}, {lon:.5f})"
        user_state[uid]["step"] = "to_address"
        await message.answer("Геопозиция получена!")
        await ask_destination(message)

async def ask_destination(message: types.Message):
    await message.answer("🏁 <b>Куда едем?</b>", parse_mode="HTML", reply_markup=to_location_method())

@dp.message(lambda msg: msg.text and msg.text.startswith("🏷 "))
async def popular_place(message: types.Message):
    uid = message.from_user.id
    if uid not in user_state:
        return
    user_state[uid]["to_address"] = message.text[2:].strip()
    user_state[uid]["step"] = "confirm"
    await confirm_order_step(message)

@dp.message(F.text == "✏️ Другой адрес")
async def manual_to(message: types.Message):
    uid = message.from_user.id
    if uid not in user_state:
        return
    user_state[uid]["step"] = "waiting_to_text"
    await message.answer("Напишите адрес назначения:", reply_markup=back_only_keyboard())

@dp.message(lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "waiting_to_text")
async def get_to_text(message: types.Message):
    uid = message.from_user.id
    user_state[uid]["to_address"] = message.text
    user_state[uid]["step"] = "confirm"
    await confirm_order_step(message)

async def confirm_order_step(message: types.Message):
    uid = message.from_user.id
    state = user_state.get(uid)
    if not state:
        return
    loyalty = get_loyalty(uid)
    has_discounts = (loyalty and loyalty[1] > 0)
    state["discount_applied"] = has_discounts  # предварительно
    discount_text = "\n💰 Применена скидка 50%!" if has_discounts else ""
    summary = (
        f"📋 <b>Ваш заказ:</b>\n"
        f"📍 Откуда: {state['from_address']}\n"
        f"🏁 Куда: {state.get('to_address', 'не указан')}\n"
        f"📞 Телефон: {state.get('phone', 'не указан')}{discount_text}\n\n"
        f"Всё верно?"
    )
    await message.answer(summary, parse_mode="HTML", reply_markup=apply_discount_kb(has_discounts))

@dp.message(F.text == "✅ Подтвердить заказ (со скидкой 50%)")
async def confirm_discount(message: types.Message):
    uid = message.from_user.id
    if uid in user_state:
        user_state[uid]["discount_applied"] = True
    await confirm_order_client(message)

@dp.message(F.text == "✅ Подтвердить заказ (без скидки)")
async def confirm_no_discount(message: types.Message):
    uid = message.from_user.id
    if uid in user_state:
        user_state[uid]["discount_applied"] = False
    await confirm_order_client(message)

@dp.message(F.text == "✅ Подтвердить заказ")
async def confirm_order_client(message: types.Message):
    uid = message.from_user.id
    state = user_state.pop(uid, None)
    if not state:
        return
    order_id = add_order(uid, state["from_address"], state.get("from_lat"), state.get("from_lon"),
                         state.get("to_address"), state.get("phone"))
    # списываем скидку, если применена
    if state.get("discount_applied"):
        use_discount(uid)
    online = get_online_drivers()
    if not online:
        await message.answer("😔 Нет свободных водителей. Попробуйте позже или звоните диспетчеру.", reply_markup=main_menu())
        return
    discount_msg = "\n💰 Скидка 50% (лояльность)" if state.get("discount_applied") else ""
    for driver_id in online:
        try:
            driver_info_msg = (
                f"🔔 <b>Новый заказ!</b>\n"
                f"📍 Откуда: {state['from_address']}\n"
                f"🏁 Куда: {state.get('to_address')}\n"
                f"📞 Клиент: {state.get('phone')}{discount_msg}\n"
                f"ID заказа: {order_id}"
            )
            await bot.send_message(driver_id, driver_info_msg, parse_mode="HTML",
                                   reply_markup=driver_accept_order(order_id))
            if state.get("from_lat") is not None:
                await bot.send_location(driver_id, latitude=state["from_lat"], longitude=state["from_lon"])
        except Exception as e:
            logging.error(f"Failed to notify driver {driver_id}: {e}")
    await message.answer("⏳ Ищем автомобиль...", reply_markup=main_menu())

@dp.message(F.text == "❌ Отменить")
async def cancel_order_creation(message: types.Message):
    uid = message.from_user.id
    if uid in user_state:
        del user_state[uid]
    await message.answer("🚫 Заказ отменён.", reply_markup=main_menu())

@dp.message(F.text == "⬅ Назад")
async def go_back(message: types.Message):
    # упрощённая логика назад
    uid = message.from_user.id
    if uid in user_state:
        del user_state[uid]
    await message.answer("Возврат в главное меню.", reply_markup=main_menu())

# ========== Бонусы и рефералы ==========
@dp.message(F.text == "🎁 Мои бонусы")
async def show_bonuses(message: types.Message):
    uid = message.from_user.id
    loyalty = get_loyalty(uid)
    rides, discounts = loyalty if loyalty else (0, 0)
    ref_link = f"https://t.me/{(await bot.me()).username}?start=ref{uid}"
    text = (
        f"💳 <b>Ваши бонусы</b>\n"
        f"🚕 Поездок: {rides}/5\n"
        f"🎟 Доступно скидок 50%: {discounts}\n\n"
        f"Ваша реферальная ссылка:\n{ref_link}\n\n"
        f"Скидка действует только по городу."
    )
    await message.answer(text, parse_mode="HTML", reply_markup=bonus_menu())

@dp.message(F.text == "👥 Пригласить друга")
async def invite_friend(message: types.Message):
    uid = message.from_user.id
    ref_link = f"https://t.me/{(await bot.me()).username}?start=ref{uid}"
    await message.answer(
        f"👥 Пригласите друга по ссылке:\n{ref_link}\n\n"
        "Когда друг совершит первую поездку, вы получите скидку 50% на следующую.",
        reply_markup=bonus_menu()
    )

# ========== Чат с водителем ==========
@dp.message(F.text == "💬 Сообщение водителю")
async def client_open_chat(message: types.Message):
    uid = message.from_user.id
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute("SELECT id, driver_id FROM orders WHERE client_id=? AND status='accepted' ORDER BY id DESC LIMIT 1", (uid,))
    row = c.fetchone()
    conn.close()
    if not row:
        await message.answer("Нет активного заказа.")
        return
    _, driver_id = row
    chat_sessions[uid] = (driver_id, 'client')
    chat_sessions[driver_id] = (uid, 'driver')
    await message.answer("💬 Чат с водителем открыт. Отправьте сообщение, фото или голосовое. Для выхода нажмите «Завершить чат».",
                         reply_markup=client_chat_active())

@dp.message(F.text == "🔕 Завершить чат")
async def close_chat(message: types.Message):
    uid = message.from_user.id
    if uid in chat_sessions:
        target_id, _ = chat_sessions[uid]
        chat_sessions.pop(uid, None)
        chat_sessions.pop(target_id, None)
    await message.answer("Чат завершён.", reply_markup=client_driver_found())

@dp.message(lambda msg: msg.from_user.id in chat_sessions, content_types=types.ContentType.ANY)
async def relay_chat_message(message: types.Message):
    uid = message.from_user.id
    target_id, role = chat_sessions[uid]
    try:
        await message.copy_to(target_id)
    except:
        await message.answer("❌ Не удалось доставить сообщение.")

# --- Аналогично для водителя ---
@dp.callback_query(lambda c: c.data.startswith("chat_"))
async def driver_open_chat(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    order_id = int(callback.data.split("_")[1])
    order = get_order(order_id)
    if not order or order[3] != 'accepted':
        await callback.answer("Заказ не актуален.")
        return
    client_id = order[1]
    chat_sessions[driver_id] = (client_id, 'driver')
    chat_sessions[client_id] = (driver_id, 'client')
    await bot.send_message(driver_id, "💬 Чат с клиентом открыт. Отправьте сообщение. Для выхода нажмите «Завершить чат».",
                           reply_markup=driver_chat_active())
    await callback.answer()

@dp.message(F.text == "🔕 Завершить чат")  # для водителя
async def driver_close_chat(message: types.Message):
    await close_chat(message)
    await message.answer("Чат завершён.", reply_markup=driver_order_actions(get_driver_current_order(message.from_user.id)))

# ========== Остальные обработчики заказа (accept, decline, loc, arrived, finish) ==========
# (оставлены без изменений, но для finish добавим лояльность)

@dp.callback_query(lambda c: c.data.startswith("accept_"))
async def accept_order_handler(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    order_id = int(callback.data.split("_")[1])
    order = get_order(order_id)
    if not order or order[3] != 'searching':
        await callback.answer("Заказ уже не актуален.", show_alert=True)
        await callback.message.delete()
        return
    driver = get_driver(driver_id)
    if driver:
        driver_info = {
            "name": driver[1] or callback.from_user.full_name,
            "car": f"{driver[3] or '?'} {driver[4] or '?'}",
            "plate": driver[5] or "не указан",
            "phone": driver[2] or "не указан"
        }
    else:
        driver_info = {"name": callback.from_user.full_name, "car": "не указан", "plate": "не указан", "phone": "не указан"}
    accept_order(order_id, driver_id, json.dumps(driver_info))
    client_id = order[1]
    client_msg = (
        f"🚖 <b>Водитель найден!</b>\n"
        f"Имя: {driver_info['name']}\nАвто: {driver_info['car']}\nНомер: {driver_info['plate']}\n"
        f"Ожидаемое время подачи: ~5 минут."
    )
    try:
        await bot.send_message(client_id, client_msg, parse_mode="HTML", reply_markup=client_driver_found())
    except Exception as e:
        logging.error(f"Notify client {client_id}: {e}")
    await callback.message.edit_text(
        f"✅ Вы приняли заказ #{order_id}\n📍 {order[4]} → {order[7]}\n📞 Клиент: {order[8]}",
        reply_markup=driver_order_actions(order_id))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("decline_"))
async def decline_order_handler(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.answer("Вы отклонили заказ.")

@dp.callback_query(lambda c: c.data.startswith("req_loc_"))
async def request_client_location(callback: types.CallbackQuery):
    order = get_order(int(callback.data.split("_")[2]))
    if not order:
        return
    client_id = order[1]
    pending_client_geo[client_id] = callback.from_user.id
    await bot.send_message(client_id, "📍 Водитель запрашивает ваше местоположение. Отправьте геопозицию.", reply_markup=request_location_kb())
    await callback.answer("Запрос отправлен.")

@dp.callback_query(lambda c: c.data.startswith("send_loc_"))
async def send_geo_to_client(callback: types.CallbackQuery):
    order = get_order(int(callback.data.split("_")[2]))
    if not order:
        return
    client_id = order[1]
    pending_driver_geo[callback.from_user.id] = client_id
    await bot.send_message(callback.from_user.id, "🗺 Отправьте вашу геопозицию для клиента.", reply_markup=request_location_kb("📍 Моя геопозиция"))
    await callback.answer("Отправьте гео.")

@dp.callback_query(lambda c: c.data.startswith("arrived_"))
async def driver_arrived(callback: types.CallbackQuery):
    order = get_order(int(callback.data.split("_")[1]))
    if not order:
        return
    client_id = order[1]
    await bot.send_message(client_id, "🚕 <b>Водитель на месте!</b>", parse_mode="HTML", reply_markup=client_after_arrived())
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🛑 Завершить поездку", callback_data=f"finish_{order[0]}")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("finish_"))
async def driver_finish(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    order_id = int(callback.data.split("_")[1])
    order = get_order(order_id)
    if not order:
        await callback.answer("Заказ не найден.")
        return
    client_id = order[1]
    # --- Лояльность ---
    loyalty_row = get_loyalty(client_id)
    rides_before = loyalty_row[0] if loyalty_row else 0
    increment_rides(client_id)  # увеличит или сконвертирует в скидку
    if rides_before == 0:
        complete_referral(client_id)  # первая поездка -> награда пригласившему
    # ---
    finish_order(order_id)
    await bot.send_message(client_id, "🏁 <b>Поездка завершена.</b> Спасибо!", parse_mode="HTML", reply_markup=main_menu())
    await bot.send_message(client_id, "Оцените поездку:", reply_markup=rating_keyboard(order_id))
    await callback.message.edit_text("Поездка завершена. Ожидайте новый заказ.")
    await callback.answer()
    chat_sessions.pop(client_id, None)
    chat_sessions.pop(driver_id, None)

@dp.message(F.text.in_(["🏃 Уже иду", "⏳ Буду через 5 мин", "📍 Я на месте"]))
async def client_fast_reply(message: types.Message):
    uid = message.from_user.id
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute("SELECT id, driver_id FROM orders WHERE client_id=? AND status='accepted' ORDER BY id DESC LIMIT 1", (uid,))
    row = c.fetchone()
    conn.close()
    if not row:
        await message.answer("Нет активного заказа.")
        return
    order_id, driver_id = row
    try:
        await bot.send_message(driver_id, f"📩 Клиент: «{message.text}»")
        await message.answer("✅ Водитель получил сообщение.")
    except Exception as e:
        await message.answer("❌ Не удалось отправить сообщение водителю.")

@dp.callback_query(lambda c: c.data.startswith("rate_"))
async def rate_order(callback: types.CallbackQuery):
    _, order_id, stars = callback.data.split("_")
    order_id, stars = int(order_id), int(stars)
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute('UPDATE orders SET rating=? WHERE id=?', (stars, order_id))
    conn.commit()
    conn.close()
    await callback.message.edit_text(f"Спасибо! Оценка: {'⭐'*stars} ({stars})")
    await callback.answer()

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
        text += (f"🚕 {created_date}\n📍 {o[4]} → {o[7]}\nСтатус: {o[3]}{rating_str}\n\n")
    await message.answer(text, parse_mode="HTML")

# ========== Запуск ==========
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())