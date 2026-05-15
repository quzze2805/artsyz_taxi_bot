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
                      get_driver_queued_order, cancel_order, cancel_queued_order,
                      queue_order, activate_queued_order,
                      get_client_last_orders,
                      save_driver, get_driver, is_driver_allowed,
                      add_allowed_driver, remove_allowed_driver, get_all_drivers,
                      get_allowed_drivers_list,
                      get_loyalty, use_discount,
                      save_referral,
                      process_finished_order, save_review,
                      is_workday_active, set_workday_active,
                      update_client, get_client_info,
                      block_client, unblock_client, is_blocked,
                      get_block_reason,
                      log_start, get_start_count, get_driver_stats, get_all_drivers_stats)   # ← добавьте эти две функции
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
pending_queue = {}            # driver_id -> (order_id, driver_info_json)
order_messages = {}           # order_id -> list of (chat_id, message_id)
driver_cancel_state = {}      # driver_id -> order_id (для причины отмены)
review_state = {}             # user_id -> order_id (ожидание отзыва)

def get_main_menu(user_id: int):
    if is_driver_allowed(user_id):
        return main_menu_driver()
    return main_menu()

@dp.message(F.text == "📈 Статистика водителей")
async def admin_drivers_stats(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    stats = get_all_drivers_stats()
    if not stats:
        await message.answer("Нет данных о водителях.")
        return
    text = "📈 <b>Статистика водителей</b>\n\n"
    for s in stats:
        text += f"👤 {s['name']} (ID: {s['driver_id']})\n🚕 Поездок: {s['total']} | ⭐ Рейтинг: {s['avg_rating']}\n\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("driverstat"))
async def cmd_driver_stat(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        driver_id = int(message.text.split()[1])
    except:
        await message.answer("Используйте: /driverstat <ID водителя>")
        return

    stats = get_driver_stats(driver_id)
    driver = get_driver(driver_id)
    name = driver[1] if driver else "Неизвестный"
    await message.answer(
        f"📊 <b>Статистика водителя {name} (ID: {driver_id})</b>\n\n"
        f"✅ Завершённых поездок: {stats['finished']}\n"
        f"⭐ Средний рейтинг: {stats['avg_rating']}\n"
        f"❌ Отмен: {stats['cancelled']}",
        parse_mode="HTML"
    )

# ========== Общие команды ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Логируем уникального пользователя
    log_start(message.from_user.id)

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
    await message.answer("Что хотите сделать?", reply_markup=get_main_menu(message.from_user.id))

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
        del user_state[message.from_user.id]
        return
    user_state[message.from_user.id]["new_driver_id"] = driver_id
    user_state[message.from_user.id]["step"] = "admin_enter_driver_name"
    await message.answer("👤 Введите имя водителя:")

@dp.message(lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_enter_driver_name")
async def admin_enter_driver_name(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    user_state[message.from_user.id]["new_driver_name"] = message.text.strip()
    user_state[message.from_user.id]["step"] = "admin_enter_driver_phone"
    await message.answer("📞 Введите номер телефона водителя (в формате +380XXXXXXXXX):")

@dp.message(lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_enter_driver_phone")
async def admin_enter_driver_phone(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    user_state[message.from_user.id]["new_driver_phone"] = message.text.strip()
    user_state[message.from_user.id]["step"] = "admin_enter_driver_car"
    await message.answer("🚗 Введите марку и модель авто (например: Toyota Camry):")

@dp.message(lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_enter_driver_car")
async def admin_enter_driver_car(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    user_state[message.from_user.id]["new_driver_car"] = message.text.strip()
    user_state[message.from_user.id]["step"] = "admin_enter_driver_color"
    await message.answer("🎨 Введите цвет авто:")

@dp.message(lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_enter_driver_color")
async def admin_enter_driver_color(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    user_state[message.from_user.id]["new_driver_color"] = message.text.strip()
    user_state[message.from_user.id]["step"] = "admin_enter_driver_plate"
    await message.answer("🔢 Введите госномер авто (например: A123BC):")

@dp.message(lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_enter_driver_plate")
async def admin_enter_driver_plate(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    admin_id = message.from_user.id
    driver_id = user_state[admin_id]["new_driver_id"]
    name = user_state[admin_id]["new_driver_name"]
    phone = user_state[admin_id]["new_driver_phone"]
    car_model = user_state[admin_id]["new_driver_car"]
    car_color = user_state[admin_id]["new_driver_color"]
    car_plate = message.text.strip()
    add_allowed_driver(driver_id)
    save_driver(driver_id, name=name, phone=phone, car_model=car_model, car_color=car_color, car_plate=car_plate)
    await message.answer(f"✅ Водитель {name} добавлен.", reply_markup=admin_menu())
    try:
        await bot.send_message(driver_id,
            "🎉 <b>Поздравляем!</b>\n\n"
            "Вы добавлены водителем в сервис <b>TaxiService</b>!\n\n"
            "Для начала работы:\n"
            "1️⃣ Откройте бота: @taxi_artsyz_bot\n"
            "2️⃣ Нажмите /driver\n"
            "3️⃣ Нажмите «🔛 Начать смену»\n\n"
            "Добро пожаловать в команду! 💪",
            parse_mode="HTML")
    except:
        pass
    del user_state[admin_id]

@dp.message(Command("driverstat"))
async def cmd_driver_stat(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        driver_id = int(message.text.split()[1])
    except:
        await message.answer("Используйте: /driverstat <ID водителя>")
        return

    stats = get_driver_stats(driver_id)
    driver = get_driver(driver_id)
    name = driver[1] if driver else "Неизвестный"
    await message.answer(
        f"📊 <b>Статистика водителя {name} (ID: {driver_id})</b>\n\n"
        f"✅ Завершённых поездок: {stats['finished']}\n"
        f"⭐ Средний рейтинг: {stats['avg_rating']}\n"
        f"❌ Отмен: {stats['cancelled']}",
        parse_mode="HTML"
    )

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
    await message.answer(f"✅ Водитель {driver_id} удалён.", reply_markup=admin_menu())
    try:
        await bot.send_message(driver_id,
            "🔔 <b>Уведомление</b>\n\n"
            "Вы были исключены из списка водителей. Для уточнения причин свяжитесь с диспетчером.",
            parse_mode="HTML")
    except:
        pass
    del user_state[message.from_user.id]

@dp.message(F.text == "📋 Список водителей")
async def admin_list_drivers(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    allowed = get_allowed_drivers_list()
    if not allowed:
        await message.answer("Нет водителей.")
        return
    text = "📋 <b>Водители:</b>\n\n"
    for d_id in allowed:
        d = get_driver(d_id)
        if d:
            text += f"ID: {d[0]} | {d[1]} | {d[2]} | {d[3]} {d[4]} ({d[5]})\n"
        else:
            text += f"ID: {d_id} (не зарегистрирован)\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🚫 Заблокировать клиента")
async def admin_block_prompt(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    user_state[message.from_user.id] = {"step": "admin_block_phone"}
    await message.answer("Введите номер телефона для блокировки (380XXXXXXXXX):")

@dp.message(F.text, lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_block_phone")
async def admin_block_phone(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    phone = message.text.strip().replace('+', '').replace('-', '').replace(' ', '')
    if not phone.startswith("380") or len(phone) != 12:
        await message.answer("Неверный формат. Попробуйте ещё раз:")
        return
    user_state[message.from_user.id]["block_phone"] = phone
    user_state[message.from_user.id]["step"] = "admin_block_reason"
    await message.answer("Укажите причину блокировки:")

@dp.message(F.text, lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_block_reason")
async def admin_block_reason(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    phone = user_state[message.from_user.id]["block_phone"]
    reason = message.text.strip()
    block_client(phone, reason)
    await message.answer(f"✅ Клиент {phone} заблокирован. Причина: {reason}", reply_markup=admin_menu())
    del user_state[message.from_user.id]

@dp.message(F.text == "✅ Разблокировать клиента")
async def admin_unblock_prompt(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    user_state[message.from_user.id] = {"step": "admin_unblock_phone"}
    await message.answer("Введите номер телефона для разблокировки:")

@dp.message(F.text, lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_unblock_phone")
async def admin_unblock_phone(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    phone = message.text.strip().replace('+', '').replace('-', '').replace(' ', '')
    if not phone.startswith("380") or len(phone) != 12:
        await message.answer("Неверный формат.")
        return
    unblock_client(phone)
    await message.answer(f"✅ Клиент {phone} разблокирован.", reply_markup=admin_menu())
    del user_state[message.from_user.id]

@dp.message(F.text == "📊 Статистика")
async def admin_stats(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    starts = get_start_count()
    await message.answer(
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Уникальных пользователей, нажавших /start: <b>{starts}</b>",
        parse_mode="HTML"
    )

@dp.message(F.text == "🔴 Закончить рабочий день")
async def admin_stop_workday(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    set_workday_active(False)
    await message.answer("🔴 Рабочий день завершён.")

@dp.message(F.text == "🟢 Включить рабочий день")
async def admin_start_workday(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    set_workday_active(True)
    await message.answer("🟢 Рабочий день включён.")

@dp.message(F.text == "🔙 Выйти из админки")
async def admin_exit(message: types.Message):
    await message.answer("Вы вышли из админ-панели.", reply_markup=get_main_menu(message.from_user.id))

# ========== Кабинет водителя ==========
@dp.message(Command("driver"))
async def cmd_driver(message: types.Message):
    driver_id = message.from_user.id
    if not is_driver_allowed(driver_id):
        await message.answer("⛔ У вас нет доступа.")
        return
    driver = get_driver(driver_id)
    if driver and driver[2] is not None:
        await message.answer("🚘 Добро пожаловать в кабинет водителя!", reply_markup=driver_main())
        return
    driver_reg_state[driver_id] = {"step": "ask_name"}
    await message.answer("👤 Введите ваше имя:")

@dp.message(F.text == "🚘 Кабинет водителя")
async def driver_cabinet_button(message: types.Message):
    await cmd_driver(message)

@dp.message(lambda msg: msg.from_user.id in driver_reg_state)
async def driver_registration(message: types.Message):
    driver_id = message.from_user.id
    state = driver_reg_state[driver_id]
    if state["step"] == "ask_name":
        state["name"] = message.text.strip()
        state["step"] = "ask_phone"
        await message.answer("📞 Отправьте номер телефона (кнопкой или вручную +380...)",
                             reply_markup=ReplyKeyboardMarkup(
                                 keyboard=[[KeyboardButton(text="📱 Поделиться номером", request_contact=True)]],
                                 resize_keyboard=True))
    elif state["step"] == "ask_phone":
        phone = None
        if message.contact:
            phone = message.contact.phone_number
        else:
            text = message.text.strip().replace('-', '').replace(' ', '')
            if text.startswith("+380") and len(text) == 13:
                phone = text
            else:
                await message.answer("⚠️ Неверный формат.")
                return
        state["phone"] = phone
        state["step"] = "ask_car"
        await message.answer("🚗 Марка и модель авто:", reply_markup=ReplyKeyboardRemove())
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
        save_driver(driver_id, name=state["name"], phone=state["phone"],
                    car_model=state["car_model"], car_color=state["car_color"],
                    car_plate=state["car_plate"])
        del driver_reg_state[driver_id]
        await message.answer("✅ Регистрация завершена!", reply_markup=driver_main())

@dp.message(F.text == "🔛 Начать смену")
async def start_shift(message: types.Message):
    if not is_driver_allowed(message.from_user.id):
        return
    set_driver_online(message.from_user.id, True)
    await message.answer("✅ Вы на смене!", reply_markup=driver_main())

@dp.message(F.text == "🔚 Закончить смену")
async def end_shift(message: types.Message):
    if not is_driver_allowed(message.from_user.id):
        return
    set_driver_online(message.from_user.id, False)
    await message.answer("🛑 Смена завершена.", reply_markup=get_main_menu(message.from_user.id))

@dp.message(F.text == "🔙 В главное меню")
async def driver_back_to_main(message: types.Message):
    await message.answer("Головне меню", reply_markup=get_main_menu(message.from_user.id))

@dp.message(F.text == "🔙 Вернуться в главное меню")
async def closed_back_to_main(message: types.Message):
    await message.answer("Повертаємось до головного меню.", reply_markup=get_main_menu(message.from_user.id))

@dp.message(F.text == "🔙 Вернуться в главное меню")
async def closed_back_to_main(message: types.Message):
    await message.answer("Повертаємось до головного меню.", reply_markup=get_main_menu(message.from_user.id))

# ========== Клиентский заказ ==========
@dp.message(F.text == "🚖 Заказать такси")
async def start_order(message: types.Message):
    if not is_workday_active():
        await message.answer(
            "🌙 Зараз неробочий час. Замовлення через бота тимчасово недоступні.\n"
            "Скористатися ботом можна з 10:00 до 23:30.\n\n"
            "Замовити за телефоном: +380754436757",
            reply_markup=workday_closed_kb()
        )
        return
    user_state[message.from_user.id] = {"step": "get_phone"}
    await message.answer("Для оформления заказа подтвердите номер телефона.",
                         reply_markup=contact_request())

@dp.message(F.text == "💬 Поддержка")
async def support(message: types.Message):
    await message.answer(f"📞 {SUPPORT_PHONE}\n💬 {TELEGRAM_CONTACT}")

@dp.message(F.contact)
async def contact_received(message: types.Message):
    uid = message.from_user.id
    if uid not in user_state or user_state[uid].get("step") != "get_phone":
        return
    phone = message.contact.phone_number.replace('+', '').replace('-', '').replace(' ', '')
    if is_blocked(phone):
        reason = get_block_reason(phone)
        reason_text = f"\n\n<i>Причина: {reason}</i>" if reason else ""
        await message.answer(
            f"⛔ <b>Доступ заблоковано</b>\n\n"
            f"Ви більше не можете користуватися сервісом через порушення правил.{reason_text}\n\n"
            f"Телефон для зв'язку: +38 075 443 67 57",
            parse_mode="HTML", reply_markup=get_main_menu(uid)
        )
        del user_state[uid]
        return
    user_state[uid] = {"phone": phone, "step": "from_address"}
    await message.answer("📍 <b>Откуда вас забрать?</b>", parse_mode="HTML", reply_markup=from_location_method())

@dp.message(F.text == "✏️ Написать адрес вручную")
async def manual_from(message: types.Message):
    uid = message.from_user.id
    if uid not in user_state:
        return
    user_state[uid]["step"] = "waiting_from_text"
    await message.answer("Напишите адрес подачи:", reply_markup=back_only_keyboard())

@dp.message(F.text, lambda msg: user_state.get(msg.from_user.id, {}).get("step") == "waiting_from_text")
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
    if uid in pending_client_geo:
        driver_id = pending_client_geo.pop(uid)
        try:
            await message.copy_to(driver_id)
            await bot.send_message(driver_id, "📍 Клиент передал геопозицию.")
        except:
            pass
        else:
            await message.answer("✅ Геопозиция отправлена водителю.", reply_markup=client_driver_found())
        return
    if uid in pending_driver_geo:
        client_id = pending_driver_geo.pop(uid)
        try:
            await message.copy_to(client_id)
            await bot.send_message(client_id, "📍 Водитель передаёт геопозицию.")
        except:
            pass
        else:
            await message.answer("✅ Геопозиция отправлена клиенту.",
                                 reply_markup=driver_order_actions(get_driver_current_order(uid)))
        return
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

@dp.message(F.text, lambda msg: user_state.get(msg.from_user.id, {}).get("step") == "waiting_to_text")
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
    state["discount_applied"] = has_discounts
    discount_text = "\n💰 Применена скидка 50%!" if has_discounts else ""
    phone = state.get("phone") or "не указан"
    from_addr = state.get("from_address") or "не указан"
    to_addr = state.get("to_address") or "не указан"
    summary = (
        f"📋 <b>Ваш заказ:</b>\n"
        f"📍 Откуда: {from_addr}\n"
        f"🏁 Куда: {to_addr}\n"
        f"📞 Телефон: {phone}{discount_text}\n\n"
        f"<i>⚠️ Будь ласка, підтверджуйте замовлення лише якщо ви дійсно плануєте поїздку.</i>\n"
        f"<i>Неправдиві виклики призводять до блокування акаунта.</i>\n\n"
        f"Всё верно?"
    )
    await message.answer(summary, parse_mode="HTML", reply_markup=apply_discount_kb(has_discounts))

@dp.message(F.text == "✅ Подтвердить заказ (со скидкой 50%)")
async def confirm_discount(message: types.Message):
    uid = message.from_user.id
    if uid in user_state:
        user_state[uid]["discount_applied"] = True
    await confirm_order_client(message)

@dp.message(F.text == "✅ Подтвердить заказ (межгород, без скидки)")
async def confirm_no_discount(message: types.Message):
    uid = message.from_user.id
    if uid in user_state:
        user_state[uid]["discount_applied"] = False
    await confirm_order_client(message)

@dp.message(F.text == "✅ Подтвердить заказ")
async def confirm_order_client(message: types.Message):
    uid = message.from_user.id
    state = user_state.get(uid)
    if not state:
        return
    order_id = add_order(uid, state["from_address"], state.get("from_lat"), state.get("from_lon"),
                     state.get("to_address"), state.get("phone"),
                     discount=1 if state.get("discount_applied") else 0)
    update_client(uid, state.get("phone"), message.from_user.full_name)
    online = get_online_drivers()
    if not online:
        await message.answer("😔 Нет свободных водителей.", reply_markup=get_main_menu(uid))
        return
    discount_msg = "\n💰 Скидка 50% (лояльность)" if state.get("discount_applied") else ""
    try:
        client_user = await bot.get_chat(uid)
        client_telegram = f"@{client_user.username}" if client_user.username else f"tg://user?id={uid}"
        client_name = client_user.full_name or "не указано"
    except:
        client_telegram = f"tg://user?id={uid}"
        client_name = "не указано"
    client_info = get_client_info(state.get("phone"))
    rides_info = ""
    if client_info:
        rides_info = f"🚕 Поїздок: {client_info[3]}"
        if client_info[3] == 0:
            rides_info += " (новий клієнт)"
    
    # Запоминаем сообщения, разосланные водителям
    order_messages[order_id] = []
    
    for driver_id in online:
        try:
            driver_info_msg = (
                f"🔔 <b>Новый заказ!</b>\n"
                f"📍 Откуда: {state['from_address']}\n"
                f"🏁 Куда: {state.get('to_address')}\n"
                f"📞 Телефон: {state.get('phone')}\n"
                f"👤 Клиент: {client_name}\n"
                f"💬 Telegram: {client_telegram}\n"
                f"{rides_info}\n"
                f"{discount_msg}"
                f"ID заказа: {order_id}"
            )
            msg = await bot.send_message(driver_id, driver_info_msg, parse_mode="HTML",
                                         reply_markup=driver_accept_order(order_id))
            order_messages[order_id].append((driver_id, msg.message_id))
            if state.get("from_lat") is not None:
                await bot.send_location(driver_id, latitude=state["from_lat"], longitude=state["from_lon"])
        except Exception as e:
            logging.error(f"Failed to notify driver {driver_id}: {e}")
    await message.answer("⏳ Ищем ближайший автомобиль...", reply_markup=searching_driver_kb())
    if uid in user_state:
        phone = user_state[uid].get("phone")
        user_state[uid] = {"phone": phone, "step": "from_address"}

@dp.message(F.text == "❌ Отменить заказ")
async def cancel_searching_order_prompt(message: types.Message):
    uid = message.from_user.id
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute("SELECT id FROM orders WHERE client_id=? AND status='searching' ORDER BY id DESC LIMIT 1", (uid,))
    row = c.fetchone()
    conn.close()
    if not row:
        await message.answer("Нет активного поиска.", reply_markup=get_main_menu(message.from_user.id))
        return
    await message.answer("Вы действительно хотите отменить поиск?", reply_markup=confirm_cancel_kb(row[0]))

@dp.message(F.text == "⬅ Изменить")
async def change_order(message: types.Message):
    uid = message.from_user.id
    if uid not in user_state:
        return
    user_state[uid]["step"] = "to_address"
    user_state[uid].pop("to_address", None)
    user_state[uid].pop("discount_applied", None)
    await message.answer("🏁 <b>Куда едем?</b>", parse_mode="HTML", reply_markup=to_location_method())

@dp.message(F.text == "⬅ Назад")
async def go_back(message: types.Message):
    uid = message.from_user.id
    if uid not in user_state:
        await message.answer("Главное меню.", reply_markup=get_main_menu(message.from_user.id))
        return
    step = user_state[uid].get("step")
    if step == "get_phone":
        del user_state[uid]
        await message.answer("Оформление заказа отменено.", reply_markup=get_main_menu(message.from_user.id))
    elif step in ("from_address", "waiting_from_text"):
        user_state[uid]["step"] = "get_phone"
        await message.answer("Вернёмся к номеру телефона.", reply_markup=contact_request())
    elif step in ("to_address", "waiting_to_text"):
        user_state[uid]["step"] = "from_address"
        await message.answer("📍 <b>Откуда вас забрать?</b>", parse_mode="HTML", reply_markup=from_location_method())
    elif step == "confirm":
        user_state[uid]["step"] = "to_address"
        await message.answer("🏁 <b>Куда едем?</b>", parse_mode="HTML", reply_markup=to_location_method())
    else:
        del user_state[uid]
        await message.answer("Главное меню.", reply_markup=get_main_menu(message.from_user.id))

@dp.message(F.text == "❌ Отменить заказ (очередь)")
async def client_cancel_queued_prompt(message: types.Message):
    client_id = message.from_user.id
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute("SELECT id, driver_id FROM orders WHERE client_id=? AND status='queued' ORDER BY id DESC LIMIT 1", (client_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        await message.answer("Нет заказа в очереди.")
        return
    order_id, driver_id = row
    await message.answer("Вы уверены, что хотите отменить заказ? Водитель уже знает о нём.",
                         reply_markup=confirm_cancel_kb(order_id))

@dp.message(F.text == "❌ Отменить")
async def cancel_order_creation(message: types.Message):
    uid = message.from_user.id
    if uid in user_state:
        del user_state[uid]
    await message.answer("🚫 Заказ отменён.", reply_markup=get_main_menu(message.from_user.id))

# ========== Бонусы ==========
@dp.message(F.text == "🎁 Мои бонусы")
async def show_bonuses(message: types.Message):
    uid = message.from_user.id
    loyalty = get_loyalty(uid)
    rides, discounts = loyalty if loyalty else (0, 0)
    ref_link = f"https://t.me/{(await bot.me()).username}?start=ref{uid}"
    await message.answer(
        f"💳 <b>Ваши бонусы</b>\n"
        f"🚕 Поездок: {rides}/5\n"
        f"🎟 Доступно скидок 50%: {discounts}\n\n"
        f"Реферальная ссылка:\n{ref_link}",
        parse_mode="HTML", reply_markup=bonus_menu()
    )

@dp.message(F.text == "👥 Пригласить друга")
async def invite_friend(message: types.Message):
    uid = message.from_user.id
    ref_link = f"https://t.me/{(await bot.me()).username}?start=ref{uid}"
    await message.answer(f"Пригласите друга:\n{ref_link}\nПосле его первой поездки вы получите скидку 50%.",
                         reply_markup=bonus_menu())

@dp.message(F.text == "🔙 Назад")
async def bonus_back(message: types.Message):
    await message.answer("Главное меню.", reply_markup=get_main_menu(message.from_user.id))

# ========== Чат ==========
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
    await message.answer("💬 Чат с водителем открыт. Для выхода нажмите «Завершить чат».",
                         reply_markup=client_chat_active())
    try:
        await bot.send_message(driver_id, "_Пассажир открыл чат._", parse_mode="Markdown")
    except:
        pass

@dp.message(F.text == "🔕 Завершить чат")
async def close_chat(message: types.Message):
    uid = message.from_user.id
    if uid in chat_sessions:
        target_id, role = chat_sessions[uid]
        chat_sessions.pop(uid, None)
        chat_sessions.pop(target_id, None)
        if role == 'client':
            try:
                order_id = get_driver_current_order(target_id)
                await bot.send_message(target_id, "_Пассажир завершил чат._", parse_mode="Markdown")
                await bot.send_message(target_id, "Чат закрыт.", reply_markup=driver_order_actions(order_id, bool(get_driver_queued_order(target_id))) if order_id else driver_main())
            except:
                pass
            await message.answer("Чат завершён.", reply_markup=client_driver_found())
        else:
            try:
                conn = sqlite3.connect("taxi.db")
                c = conn.cursor()
                c.execute("SELECT id FROM orders WHERE client_id=? AND status='accepted' ORDER BY id DESC LIMIT 1", (target_id,))
                row = c.fetchone()
                conn.close()
                if row:
                    await bot.send_message(target_id, "_Водитель завершил чат._", parse_mode="Markdown")
                    await bot.send_message(target_id, "Чат закрыт.", reply_markup=client_driver_found())
            except:
                pass
            order_id = get_driver_current_order(uid)
            await message.answer("Чат завершён.", reply_markup=driver_order_actions(order_id, bool(get_driver_queued_order(uid))) if order_id else driver_main())
    else:
        await message.answer("Чат не активен.")

@dp.message(lambda msg: msg.from_user.id in chat_sessions)
async def relay_chat_message(message: types.Message):
    uid = message.from_user.id
    target_id, role = chat_sessions[uid]
    prefix = "_Водитель:_ " if role == 'driver' else "_Пассажир:_ "
    try:
        if message.text:
            await bot.send_message(target_id, prefix + message.text, parse_mode="Markdown")
        elif message.caption:
            await message.copy_to(target_id, caption=prefix + message.caption)
        else:
            await bot.send_message(target_id, prefix, parse_mode="Markdown")
            await message.copy_to(target_id)
    except Exception as e:
        logging.error(f"Chat relay error: {e}")

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
    await bot.send_message(driver_id, "💬 Чат с клиентом открыт.", reply_markup=driver_chat_active())
    try:
        await bot.send_message(client_id, "_Водитель открыл чат._", parse_mode="Markdown")
    except:
        pass
    await callback.answer()

# ========== Обработка заказов водителем ==========
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
    driver_info_json = json.dumps(driver_info)

    # Проверяем, есть ли уже активный заказ
    current_order = get_driver_current_order(driver_id)
    if current_order:
        if get_driver_queued_order(driver_id):
            await callback.answer("У вас уже есть активный заказ и один в очереди. Завершите текущий, чтобы принять новый.", show_alert=True)
            return
        # Сохраняем данные во временное хранилище для последующего queue_order
        pending_queue[driver_id] = (order_id, driver_info_json)
        await callback.message.edit_text(
            "⏳ Через сколько минут вы планируете освободиться?",
            reply_markup=driver_wait_time_kb(order_id)
        )
        await callback.answer()
        return

    # Обычное принятие (водитель свободен)
    accept_order(order_id, driver_id, driver_info_json)
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
        reply_markup=driver_order_actions(order_id, bool(get_driver_queued_order(driver_id))))

    # Обновляем сообщения у других водителей
    if order_id in order_messages:
        for chat_id, msg_id in order_messages[order_id]:
            if chat_id == driver_id:
                continue
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=f"🔔 Заказ #{order_id} принят водителем {driver_info['name']} ({driver_info['car']}, {driver_info['plate']})",
                    reply_markup=None
                )
            except:
                pass
        del order_messages[order_id]

    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("decline_"))
async def decline_order_handler(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    order_id = int(callback.data.split("_")[1])
    order = get_order(order_id)
    if not order or order[3] != 'searching':
        await callback.answer("Заказ уже не актуален.", show_alert=True)
        await callback.message.delete()
        return
    driver_cancel_state[driver_id] = order_id
    await bot.send_message(driver_id, "📝 Укажите причину отказа от заказа:")
    await callback.answer()

@dp.message(lambda msg: msg.from_user.id in driver_cancel_state)
async def driver_cancel_reason(message: types.Message):
    driver_id = message.from_user.id
    order_id = driver_cancel_state.pop(driver_id)
    reason = message.text.strip()
    order = get_order(order_id)
    if not order or order[3] not in ('searching', 'queued'):
        await message.answer("Заказ уже не актуален.")
        return
    client_id = order[1]
    cancel_order(order_id) if order[3] == 'searching' else cancel_queued_order(order_id)
    try:
        await bot.send_message(client_id, f"❌ Водитель отменил заказ (№{order_id}).\nПричина: {reason}", reply_markup=get_main_menu(message.from_user.id))
    except:
        pass
    await message.answer("Заказ отменён.", reply_markup=driver_main())

@dp.callback_query(lambda c: c.data.startswith("wait_"))
async def driver_choose_wait_time(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    data = callback.data.split("_")
    if len(data) != 3:
        return
    order_id = int(data[1])
    minutes = int(data[2])

    # Проверяем, есть ли ожидающие данные
    if driver_id not in pending_queue or pending_queue[driver_id][0] != order_id:
        await callback.answer("Данные устарели. Попробуйте снова.", show_alert=True)
        return

    order = get_order(order_id)
    if not order or order[3] != 'searching':
        await callback.answer("Заказ уже не актуален.", show_alert=True)
        await callback.message.delete()
        if driver_id in pending_queue:
            del pending_queue[driver_id]
        return

    driver_info_json = pending_queue.pop(driver_id)[1]

    # Ставим в очередь
    queue_order(order_id, driver_id, driver_info_json)

    # Уведомление водителю
    await callback.message.edit_text(
        f"✅ Заказ #{order_id} поставлен в очередь.\n"
        f"Примерное время до освобождения: {minutes} мин.\n"
        f"Он начнётся после завершения текущей поездки."
    )

    # Уведомление клиенту (клиент Б)
    driver = get_driver(driver_id)
    driver_name = driver[1] if driver else callback.from_user.full_name
    car_info = f"{driver[3]} {driver[4]}" if driver else "не указано"
    plate = driver[5] if driver else "не указано"

    await bot.send_message(
        order[1],
        "🚖 <b>Ваш заказ принят!</b>\n"
        f"👤 Водитель: {driver_name} ({car_info}, {plate})\n\n"
        "⏳ Водитель сейчас завершает предыдущую поездку.\n"
        f"🕒 Ориентировочное время ожидания: до {minutes} минут.\n\n"
        "📍 Как только водитель освободится, он сразу направится к вам.",
        parse_mode="HTML",
        reply_markup=client_queued_kb(order_id)
    )
    await callback.answer()

# ========== Кнопки активного заказа (клиент) ==========
@dp.message(F.text == "📞 Контакты водителя")
async def show_driver_contacts(message: types.Message):
    await message.answer("📞 +38 075 443 67 57\n💬 @taxi_artsyz", reply_markup=client_driver_found())

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
    pending_client_geo[client_id] = row[1]
    await message.answer("📡 Отправьте ваше текущее местоположение.", reply_markup=request_location_kb())

@dp.message(F.text == "❌ Отменить поездку")
async def client_cancel_ride_prompt(message: types.Message):
    client_id = message.from_user.id
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute("SELECT id FROM orders WHERE client_id=? AND status='accepted' ORDER BY id DESC LIMIT 1", (client_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        await message.answer("Нет активного заказа.")
        return
    await message.answer("Вы действительно хотите отменить поездку?", reply_markup=confirm_cancel_kb(row[0]))

# ========== Ожидание в очереди (клиент Б) ==========
@dp.message(F.text == "⏳ Ожидаю")
async def client_continue_waiting(message: types.Message):
    await message.answer("Спасибо за ожидание! Водитель приедет сразу, как освободится. Мы сообщим, когда он будет в пути.",
                         reply_markup=client_queued_kb(0))  # order_id не важен для этой клавиатуры

# ========== Callback-обработчики ==========
@dp.callback_query(lambda c: c.data.startswith("confirm_cancel_"))
async def confirm_cancel_callback(callback: types.CallbackQuery):
    try:
        order_id = int(callback.data.split("_")[2])
    except:
        return
    order = get_order(order_id)
    if not order:
        await callback.answer("Заказ не найден.")
        return
    if order[3] == 'searching':
        cancel_order(order_id)
        phone = user_state.get(order[1], {}).get("phone")
        if phone:
            user_state[order[1]] = {"phone": phone, "step": "from_address"}
            await bot.send_message(order[1], "🚫 Поиск отменён. Укажите адрес подачи заново.", reply_markup=from_location_method())
        else:
            await bot.send_message(order[1], "🚫 Поиск отменён.", reply_markup=get_main_menu(message.from_user.id))
        await callback.message.edit_text("🚫 Поиск отменён.")
    elif order[3] == 'accepted':
        if order[2]:
            try:
                await bot.send_message(order[2], f"❌ Клиент отменил поездку (заказ #{order_id}).", reply_markup=driver_main())
            except:
                pass
        cancel_order(order_id)
        chat_sessions.pop(order[1], None)
        if order[2]:
            chat_sessions.pop(order[2], None)
        pending_client_geo.pop(order[1], None)
        if order[2]:
            pending_driver_geo.pop(order[2], None)
        await callback.message.edit_text("🚫 Поездка отменена.")
        await bot.send_message(order[1], "🚫 Поездка отменена.", reply_markup=get_main_menu(message.from_user.id))
    elif order[3] == 'queued':
        cancel_queued_order(order_id)
        if order[2]:
            try:
                await bot.send_message(order[2], f"❌ Клиент отменил заказ из очереди (заказ #{order_id}).", reply_markup=driver_main())
            except:
                pass
        await callback.message.edit_text("🚫 Заказ отменён.")
        await bot.send_message(order[1], "🚫 Заказ отменён.", reply_markup=get_main_menu(message.from_user.id))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("decline_cancel_"))
async def decline_cancel_callback(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[2])
    order = get_order(order_id)
    if not order:
        return
    if order[3] == 'searching':
        await callback.message.edit_text("⏳ Продолжаем поиск...")
        await bot.send_message(order[1], "⏳ Ищем ближайший автомобиль...", reply_markup=searching_driver_kb())
    elif order[3] == 'accepted':
        await callback.message.edit_text("Поездка продолжается.")
        await bot.send_message(order[1], "Поездка продолжается.", reply_markup=client_driver_found())
    elif order[3] == 'queued':
        await callback.message.edit_text("Ожидание продолжается.")
        await bot.send_message(order[1], "Ожидание продолжается.", reply_markup=client_queued_kb(order_id))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("req_loc_"))
async def request_client_location(callback: types.CallbackQuery):
    order = get_order(int(callback.data.split("_")[2]))
    if not order:
        return
    pending_client_geo[order[1]] = callback.from_user.id
    await bot.send_message(order[1], "📍 Водитель запрашивает ваше местоположение.", reply_markup=request_location_kb())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("send_loc_"))
async def send_geo_to_client(callback: types.CallbackQuery):
    order = get_order(int(callback.data.split("_")[2]))
    if not order:
        return
    pending_driver_geo[callback.from_user.id] = order[1]
    await bot.send_message(callback.from_user.id, "🗺 Отправьте вашу геопозицию для клиента.", reply_markup=request_location_kb("📍 Моя геопозиция"))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("cancel_queued_"))
async def cancel_queued_order_by_driver(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    order_id = int(callback.data.split("_")[2])
    order = get_order(order_id)
    if not order or order[3] != 'queued' or order[2] != driver_id:
        await callback.answer("Заказ не найден или не в очереди.")
        return
    cancel_queued_order(order_id)
    try:
        await bot.send_message(order[1], "❌ Водитель отменил ваш заказ из очереди. Приносим извинения.", reply_markup=get_main_menu(message.from_user.id))
    except:
        pass
    await bot.send_message(driver_id, "Заказ из очереди отменён.")
    # обновим клавиатуру текущего заказа (убираем кнопку отмены очереди)
    current_order_id = get_driver_current_order(driver_id)
    if current_order_id:
        await bot.send_message(driver_id, "Текущий заказ:", reply_markup=driver_order_actions(current_order_id, False))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("arrived_"))
async def driver_arrived(callback: types.CallbackQuery):
    order = get_order(int(callback.data.split("_")[1]))
    if not order:
        return
    client_id = order[1]
    await bot.send_message(client_id, "🚕 <b>Водитель на месте!</b>", parse_mode="HTML", reply_markup=client_after_arrived())
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛑 Завершить поездку", callback_data=f"finish_{order[0]}")]
        ]))
    await callback.answer("Клиент уведомлён.")

@dp.callback_query(lambda c: c.data.startswith("finish_"))
async def driver_finish(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    order_id = int(callback.data.split("_")[1])
    order = get_order(order_id)
    if not order:
        await callback.answer("Заказ не найден.")
        return
    client_id = order[1]
    process_finished_order(order_id)

    await bot.send_message(client_id, "🏁 <b>Поездка завершена.</b> Спасибо!", parse_mode="HTML", reply_markup=get_main_menu(client_id))
    await bot.send_message(client_id, "Оцените поездку:", reply_markup=rating_keyboard(order_id))

    # Активация очереди
    queued_id = activate_queued_order(driver_id)
    if queued_id:
        queued_order = get_order(queued_id)
        if queued_order:
            await bot.send_message(queued_order[1],
                "🚖 Водитель освободился и едет к вам! Ожидаемое время подачи: ~5 минут.",
                reply_markup=client_driver_found())
            await bot.send_message(driver_id,
                f"🔜 Следующий заказ #{queued_id} активирован.\n📍 {queued_order[4]} → {queued_order[7]}\n📞 Клиент: {queued_order[8]}",
                reply_markup=driver_order_actions(queued_id, False))
    else:
        await callback.message.edit_text("Поездка завершена. Ожидайте новый заказ.")
    await callback.answer()
    chat_sessions.pop(client_id, None)
    chat_sessions.pop(driver_id, None)

@dp.message(F.text.in_(["🏃 Уже иду", "⏳ Буду через 5 мин", "📍 Я на месте"]))
async def client_fast_reply(message: types.Message):
    client_id = message.from_user.id
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute("SELECT id, driver_id FROM orders WHERE client_id=? AND status='accepted' ORDER BY id DESC LIMIT 1", (client_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return
    order_id, driver_id = row
    try:
        await bot.send_message(driver_id, f"📩 Сообщение от клиента (заказ #{order_id}): «{message.text}»")
        await message.answer("✅ Водитель получил сообщение.")
    except:
        pass

@dp.callback_query(lambda c: c.data.startswith("rate_"))
async def rate_order(callback: types.CallbackQuery):
    try:
        _, order_id, stars = callback.data.split("_")
        order_id, stars = int(order_id), int(stars)
        conn = sqlite3.connect("taxi.db")
        c = conn.cursor()
        c.execute('UPDATE orders SET rating=? WHERE id=?', (stars, order_id))
        conn.commit()
        conn.close()
        order = get_order(order_id)
        if order and order[2]:
            await bot.send_message(order[2], f"📊 Оценка за заказ №{order_id}: {'⭐'*stars} ({stars}/5)")
        if stars <= 3:
            msg = "Спасибо за оценку. Нам жаль, что поездка не была идеальной. Напишите, что можно улучшить?"
        else:
            msg = "Спасибо за высокую оценку! Будем рады, если вы оставите отзыв."
        await callback.message.edit_text(f"Оценка: {stars}⭐")
        await bot.send_message(order[1], msg, reply_markup=review_prompt_kb(order_id))
    except:
        pass
    await callback.answer()

@dp.message(F.text == "✍️ Оставить отзыв")
async def review_write_prompt(message: types.Message):
    uid = message.from_user.id
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute("SELECT id FROM orders WHERE client_id=? AND status='finished' AND review IS NULL ORDER BY id DESC LIMIT 1", (uid,))
    row = c.fetchone()
    conn.close()
    if not row:
        await message.answer("Нет заказа для отзыва.", reply_markup=get_main_menu(message.from_user.id))
        return
    review_state[uid] = row[0]
    await message.answer("Напишите ваш отзыв. Для отмены нажмите «⏭ Пропустить».", reply_markup=skip_review_kb())

@dp.message(F.text == "⏭ Пропустить")
async def review_skip(message: types.Message):
    uid = message.from_user.id
    review_state.pop(uid, None)
    await message.answer("Спасибо за поездку!", reply_markup=get_main_menu(message.from_user.id))

@dp.message(F.text, lambda msg: msg.from_user.id in review_state)
async def review_receive_text(message: types.Message):
    uid = message.from_user.id
    order_id = review_state.pop(uid, None)
    if not order_id:
        return
    review_text = message.text.strip()
    if not review_text:
        await message.answer("Отзыв не может быть пустым.")
        review_state[uid] = order_id
        return
    save_review(order_id, review_text)
    await message.answer("Спасибо за ваш отзыв!", reply_markup=get_main_menu(message.from_user.id))

@dp.message(F.text == "📋 Мои поездки")
async def show_history(message: types.Message):
    orders = get_client_last_orders(message.from_user.id)
    if not orders:
        await message.answer("У вас ещё нет поездок.", reply_markup=get_main_menu(message.from_user.id))
        return
    text = "<b>Последние поездки:</b>\n\n"
    for o in orders:
        rating_value = o[13] if len(o) > 13 else None
        if rating_value is not None:
            rating_value = int(rating_value)
        rating_str = f" {'⭐'*rating_value}" if rating_value else ""
        created_date = o[11][:10] if o[11] else "?"
        text += (f"🚕 {created_date}\n📍 {o[4]} → {o[7]}\nСтатус: {o[3]}{rating_str}\n\n")
    await message.answer(text, parse_mode="HTML")

# ========== Запуск ==========
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())