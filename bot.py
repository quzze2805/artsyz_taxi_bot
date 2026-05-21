import asyncio
import json
import logging
import sqlite3
from datetime import datetime
from dateutil import parser
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
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
                      log_start, get_start_count,
                      get_all_drivers_stats, get_driver_stats,
                      add_planned_order, get_planned_order, get_client_planned_orders,
                      cancel_planned_order, get_due_reminders, set_planned_reminded,
                      activate_planned_order,
                      get_all_started_users,
                      get_planned_orders_to_remind, set_planned_reminded_order)
from keyboards import *

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Глобальні стани
user_state = {}
driver_reg_state = {}
pending_client_geo = {}
pending_driver_geo = {}
chat_sessions = {}
driver_cancel_state = {}
review_state = {}
order_messages = {}
pending_queue = {}
pending_eta = {}
pending_price = {}
pending_custom_price = {}

def get_main_menu(user_id: int):
    if user_id in ADMIN_IDS:
        # админ видит админ-кнопку; если ещё и водитель — кабинет водителя тоже будет
        return main_menu_admin(is_driver=is_driver_allowed(user_id))
    elif is_driver_allowed(user_id):
        return main_menu_driver()
    else:
        return main_menu()

# ========== Загальні команди ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
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
        f"Ласкаво просимо до <b>{SERVICE_NAME}</b> — ваш комфорт починається тут. ✨\n\n"
        f"Ми доставимо вас у будь-яку точку міста швидко та безпечно.\n"
        f"Якщо зручніше замовити голосом, телефонуйте:\n📞 {SUPPORT_PHONE}\n"
        f"або через Telegram: {TELEGRAM_CONTACT}, відповідаємо дуже швидко."
    )
    await message.answer(text, parse_mode="HTML")
    await message.answer("Що бажаєте зробити?", reply_markup=get_main_menu(message.from_user.id))

@dp.message(Command("id"))
async def cmd_id(message: types.Message):
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>", parse_mode="HTML")

# ========== Адмін-панель ==========
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("🔐 Адмін-панель:", reply_markup=admin_menu())

@dp.message(F.text == "➕ Додати водія")
async def admin_add_driver_prompt(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    user_state[message.from_user.id] = {"step": "admin_enter_driver_id"}
    await message.answer("Введіть Telegram ID водія:")

@dp.message(lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_enter_driver_id")
async def admin_enter_driver_id(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        driver_id = int(message.text.strip())
    except:
        await message.answer("Некоректний ID. Скасовано.")
        del user_state[message.from_user.id]
        return
    if is_driver_allowed(driver_id):
        await message.answer("Цей водій вже доданий.")
        del user_state[message.from_user.id]
        return
    user_state[message.from_user.id]["new_driver_id"] = driver_id
    user_state[message.from_user.id]["step"] = "admin_enter_driver_name"
    await message.answer("👤 Введіть ім'я водія:")

@dp.message(lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_enter_driver_name")
async def admin_enter_driver_name(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    user_state[message.from_user.id]["new_driver_name"] = message.text.strip()
    user_state[message.from_user.id]["step"] = "admin_enter_driver_phone"
    await message.answer("📞 Введіть номер телефону водія (у форматі +380XXXXXXXXX):")

@dp.message(lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_enter_driver_phone")
async def admin_enter_driver_phone(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    user_state[message.from_user.id]["new_driver_phone"] = message.text.strip()
    user_state[message.from_user.id]["step"] = "admin_enter_driver_car"
    await message.answer("🚗 Введіть марку та модель авто (наприклад: Toyota Camry):")

@dp.message(lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_enter_driver_car")
async def admin_enter_driver_car(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    user_state[message.from_user.id]["new_driver_car"] = message.text.strip()
    user_state[message.from_user.id]["step"] = "admin_enter_driver_color"
    await message.answer("🎨 Введіть колір авто:")

@dp.message(lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_enter_driver_color")
async def admin_enter_driver_color(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    user_state[message.from_user.id]["new_driver_color"] = message.text.strip()
    user_state[message.from_user.id]["step"] = "admin_enter_driver_plate"
    await message.answer("🔢 Введіть держномер авто (наприклад: A123BC):")

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
    await message.answer(f"✅ Водія {name} додано.", reply_markup=admin_menu())
    try:
        await bot.send_message(driver_id,
            "🎉 <b>Вітаємо!</b>\n\n"
            "Вас додано водієм до сервісу <b>TaxiService</b>!\n\n"
            "Для початку роботи:\n"
            "1️⃣ Відкрийте бота: @taxi_artsyz_bot\n"
            "2️⃣ Натисніть /driver\n"
            "3️⃣ Натисніть «🔛 Розпочати зміну»\n\n"
            "Ласкаво просимо до команди! 💪",
            parse_mode="HTML")
    except:
        pass
    del user_state[admin_id]

@dp.message(F.text == "➖ Видалити водія")
async def admin_remove_driver_prompt(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    user_state[message.from_user.id] = {"step": "admin_remove_enter_id"}
    await message.answer("Введіть Telegram ID водія для видалення:")

@dp.message(lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_remove_enter_id")
async def admin_remove_enter_id(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        driver_id = int(message.text.strip())
    except:
        await message.answer("Некоректний ID. Скасовано.")
        del user_state[message.from_user.id]
        return
    remove_allowed_driver(driver_id)
    await message.answer(f"✅ Водія {driver_id} видалено.", reply_markup=admin_menu())
    try:
        await bot.send_message(driver_id,
            "🔔 <b>Сповіщення</b>\n\n"
            "Вас виключено зі списку водіїв. Для уточнення причин зверніться до диспетчера.",
            parse_mode="HTML")
    except:
        pass
    del user_state[message.from_user.id]

@dp.message(F.text == "📋 Список водіїв")
async def admin_list_drivers(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    allowed = get_allowed_drivers_list()
    if not allowed:
        await message.answer("Немає водіїв.")
        return

    online_drivers = get_online_drivers()

    text = "📋 <b>Водії:</b>\n\n"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    for d_id in allowed:
        d = get_driver(d_id)
        status_icon = "🟢" if d_id in online_drivers else "🔴"
        if d:
            text += f"{status_icon} ID: {d[0]} | {d[1]} | {d[2]} | {d[3]} {d[4]} ({d[5]})\n"
        else:
            text += f"{status_icon} ID: {d_id} (не зареєстрований)\n"

        # Если водитель онлайн — показываем кнопку принудительного завершения смены
        if d_id in online_drivers:
            keyboard.inline_keyboard.append(
                [InlineKeyboardButton(text=f"🛑 Завершити зміну для {d[1] if d else d_id}",
                                      callback_data=f"admin_endshift_{d_id}")]
            )

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard if keyboard.inline_keyboard else None)

@dp.callback_query(lambda c: c.data.startswith("admin_endshift_"))
async def admin_force_end_shift(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return

    driver_id = int(callback.data.split("_")[2])

    # Снимаем водителя со смены
    set_driver_online(driver_id, False)

    # Уведомляем водителя
    try:
        await bot.send_message(driver_id, "🛑 Адміністратор примусово завершив вашу зміну.", reply_markup=driver_main())
    except:
        pass

    await callback.answer(f"✅ Зміну водія {driver_id} завершено.", show_alert=True)

    # Обновляем сообщение со списком (повторно вызываем ту же функцию, но для callback.message)
    # Просто заново выводим список
    await admin_list_drivers(callback.message)

@dp.message(F.text == "📊 Статистика")
async def admin_stats(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    starts = get_start_count()
    await message.answer(
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Унікальних користувачів, які натиснули /start: <b>{starts}</b>",
        parse_mode="HTML"
    )

@dp.message(F.text == "📈 Статистика водіїв")
async def admin_drivers_stats(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    stats = get_all_drivers_stats()
    if not stats:
        await message.answer("Немає даних про водіїв.")
        return
    text = "📈 <b>Статистика водіїв</b>\n\n"
    for s in stats:
        text += f"👤 {s['name']} (ID: {s['driver_id']})\n🚕 Поїздок: {s['total']} | ⭐ Рейтинг: {s['avg_rating']}\n\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("driverstat"))
async def cmd_driver_stat(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        driver_id = int(message.text.split()[1])
    except:
        await message.answer("Використовуйте: /driverstat <ID водія>")
        return
    stats = get_driver_stats(driver_id)
    driver = get_driver(driver_id)
    name = driver[1] if driver else "Невідомий"
    await message.answer(
        f"📊 <b>Статистика водія {name} (ID: {driver_id})</b>\n\n"
        f"✅ Завершених поїздок: {stats['finished']}\n"
        f"⭐ Середній рейтинг: {stats['avg_rating']}\n"
        f"❌ Скасувань: {stats['cancelled']}",
        parse_mode="HTML"
    )

@dp.message(Command("reviews"))
async def cmd_reviews(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute("SELECT id, client_id, rating, review, finished_at FROM orders WHERE review IS NOT NULL ORDER BY finished_at DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    if not rows:
        await message.answer("Відгуків поки що немає.")
        return
    text = "📝 <b>Останні відгуки:</b>\n\n"
    for r in rows:
        order_id, client_id, rating, review, finished = r
        date_str = finished[:10] if finished else "?"
        rating_str = f"{'⭐'*rating} ({rating}/5)" if rating else "без оцінки"
        text += f"🚕 Замовлення №{order_id} | {date_str}\n"
        text += f"👤 Клієнт: {client_id}\n"
        text += f"⭐ Оцінка: {rating_str}\n"
        text += f"💬 {review}\n\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🚫 Заблокувати клієнта")
async def admin_block_prompt(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    user_state[message.from_user.id] = {"step": "admin_block_phone"}
    await message.answer("Введіть номер телефону для блокування (380XXXXXXXXX):")

@dp.message(F.text, lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_block_phone")
async def admin_block_phone(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    phone = message.text.strip().replace('+', '').replace('-', '').replace(' ', '')
    if not phone.startswith("380") or len(phone) != 12:
        await message.answer("Невірний формат. Спробуйте ще раз:")
        return
    user_state[message.from_user.id]["block_phone"] = phone
    user_state[message.from_user.id]["step"] = "admin_block_reason"
    await message.answer("Вкажіть причину блокування:")

@dp.message(F.text, lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_block_reason")
async def admin_block_reason(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    phone = user_state[message.from_user.id]["block_phone"]
    reason = message.text.strip()
    block_client(phone, reason)
    await message.answer(f"✅ Клієнта {phone} заблоковано. Причина: {reason}", reply_markup=admin_menu())
    del user_state[message.from_user.id]

@dp.message(F.text == "✅ Розблокувати клієнта")
async def admin_unblock_prompt(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    user_state[message.from_user.id] = {"step": "admin_unblock_phone"}
    await message.answer("Введіть номер телефону для розблокування:")

@dp.message(F.text, lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_unblock_phone")
async def admin_unblock_phone(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    phone = message.text.strip().replace('+', '').replace('-', '').replace(' ', '')
    if not phone.startswith("380") or len(phone) != 12:
        await message.answer("Невірний формат.")
        return
    unblock_client(phone)
    await message.answer(f"✅ Клієнта {phone} розблоковано.", reply_markup=admin_menu())
    del user_state[message.from_user.id]

@dp.message(F.text == "🔴 Завершити робочий день")
async def admin_stop_workday(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    set_workday_active(False)
    await message.answer("🔴 Робочий день завершено.")

@dp.message(F.text == "🟢 Розпочати робочий день")
async def admin_start_workday(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    set_workday_active(True)
    await message.answer("🟢 Робочий день розпочато.")

@dp.message(F.text == "📢 Розсилка")
async def admin_broadcast_prompt(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    user_state[message.from_user.id] = {"step": "admin_broadcast"}
    await message.answer("Введіть повідомлення для розсилки всім користувачам, які запускали бота:")

@dp.message(F.text, lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_broadcast")
async def admin_broadcast_send(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    text = message.text.strip()
    users = get_all_started_users()
    success = 0
    for uid in users:
        try:
            await bot.send_message(uid, text)
            success += 1
        except:
            pass
    await message.answer(f"✅ Розсилка виконана. Отримали: {success}/{len(users)}", reply_markup=admin_menu())
    del user_state[message.from_user.id]

@dp.message(F.text, lambda msg: msg.from_user.id in user_state and user_state[msg.from_user.id].get("step") == "admin_broadcast")
async def admin_broadcast_send(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    text = message.text.strip()
    users = get_all_started_users()
    success = 0
    for uid in users:
        try:
            await bot.send_message(uid, text)
            success += 1
        except:
            pass
    await message.answer(f"✅ Розсилка виконана. Отримали: {success}/{len(users)}", reply_markup=admin_menu())
    del user_state[message.from_user.id]

@dp.message(F.text == "🔙 Вийти з адмінки")
async def admin_exit(message: types.Message):
    await message.answer("Ви вийшли з адмін-панелі.", reply_markup=get_main_menu(message.from_user.id))

@dp.message(F.text == "🚘 Кабінет водія")
async def driver_cabinet_button(message: types.Message):
    await cmd_driver(message)

# ========== Кабінет водія ==========
@dp.message(Command("driver"))
async def cmd_driver(message: types.Message):
    driver_id = message.from_user.id
    if not is_driver_allowed(driver_id):
        await message.answer("⛔ У вас немає доступу.")
        return
    driver = get_driver(driver_id)
    if driver and driver[2] is not None:
        await message.answer("🚘 Ласкаво просимо до кабінету водія!", reply_markup=driver_main())
        return
    driver_reg_state[driver_id] = {"step": "ask_name"}
    await message.answer("👤 Введіть ваше ім'я:")

@dp.message(lambda msg: msg.from_user.id in driver_reg_state)
async def driver_registration(message: types.Message):
    driver_id = message.from_user.id
    state = driver_reg_state[driver_id]
    if state["step"] == "ask_name":
        state["name"] = message.text.strip()
        state["step"] = "ask_phone"
        await message.answer("📞 Надішліть номер телефону (кнопкою або вручну +380...)",
                             reply_markup=ReplyKeyboardMarkup(
                                 keyboard=[[KeyboardButton(text="📱 Поділитися номером", request_contact=True)]],
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
                await message.answer("⚠️ Невірний формат.")
                return
        state["phone"] = phone
        state["step"] = "ask_car"
        await message.answer("🚗 Марка та модель авто:", reply_markup=ReplyKeyboardRemove())
    elif state["step"] == "ask_car":
        state["car_model"] = message.text.strip()
        state["step"] = "ask_color"
        await message.answer("🎨 Колір авто:")
    elif state["step"] == "ask_color":
        state["car_color"] = message.text.strip()
        state["step"] = "ask_plate"
        await message.answer("🔢 Держномер:")
    elif state["step"] == "ask_plate":
        state["car_plate"] = message.text.strip()
        save_driver(driver_id, name=state["name"], phone=state["phone"],
                    car_model=state["car_model"], car_color=state["car_color"],
                    car_plate=state["car_plate"])
        del driver_reg_state[driver_id]
        await message.answer("✅ Реєстрацію завершено!", reply_markup=driver_main())

@dp.message(F.text == "🔛 Розпочати зміну")
async def start_shift(message: types.Message):
    if not is_driver_allowed(message.from_user.id):
        return
    set_driver_online(message.from_user.id, True)
    await message.answer("✅ Ви на зміні!", reply_markup=driver_main())

    # Проверяем, есть ли плановые заказы в поиске, и показываем их водителю
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute("SELECT id FROM orders WHERE is_planned=1 AND status='searching'")
    planned_orders = c.fetchall()
    conn.close()
    for (order_id,) in planned_orders:
        await send_planned_order_to_driver(order_id, message.from_user.id)

@dp.message(F.text == "🔚 Завершити зміну")
async def end_shift(message: types.Message):
    if not is_driver_allowed(message.from_user.id):
        return
    set_driver_online(message.from_user.id, False)
    await message.answer("🛑 Зміну завершено.", reply_markup=get_main_menu(message.from_user.id))

@dp.message(F.text == "📋 Мої замовлення")
async def driver_my_orders(message: types.Message):
    driver_id = message.from_user.id
    if not is_driver_allowed(driver_id):
        return
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute("SELECT id, status, from_address, to_address, phone, created_at FROM orders WHERE driver_id=? AND status IN ('accepted','searching','queued') ORDER BY id DESC", (driver_id,))
    orders = c.fetchall()
    conn.close()
    if not orders:
        await message.answer("У вас немає активних замовлень.")
        return
    text = "📋 <b>Ваші замовлення:</b>\n\n"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    status_emoji = {"accepted": "🚕", "searching": "🔍", "queued": "⏳"}
    for o in orders:
        order_id, status, from_addr, to_addr, phone, created = o
        text += f"{status_emoji.get(status, '')} <b>№{order_id}</b> ({status})\n📍 {from_addr} → {to_addr}\n📞 {phone}\n\n"
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=f"🛑 Завершити №{order_id}", callback_data=f"force_finish_{order_id}"),
            InlineKeyboardButton(text=f"❌ Скасувати №{order_id}", callback_data=f"force_cancel_{order_id}")
        ])
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data.startswith("force_finish_"))
async def force_finish_order(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    order_id = int(callback.data.split("_")[2])
    order = get_order(order_id)
    if not order or order[2] != driver_id:
        await callback.answer("Замовлення не знайдено або не ваше.", show_alert=True)
        return
    process_finished_order(order_id)
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute("UPDATE driver_state SET current_order_id=NULL WHERE current_order_id=?", (order_id,))
    c.execute("UPDATE driver_state SET queued_order_id=NULL WHERE queued_order_id=?", (order_id,))
    conn.commit()
    conn.close()
    client_id = order[1]
    chat_sessions.pop(client_id, None)
    chat_sessions.pop(driver_id, None)
    pending_client_geo.pop(client_id, None)
    pending_driver_geo.pop(driver_id, None)
    await callback.message.edit_text(f"✅ Замовлення №{order_id} примусово завершено.")
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("force_cancel_"))
async def force_cancel_order(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    order_id = int(callback.data.split("_")[2])
    order = get_order(order_id)
    if not order or order[2] != driver_id:
        await callback.answer("Замовлення не знайдено або не ваше.", show_alert=True)
        return

    # Отменяем заказ в зависимости от статуса
    if order[3] == 'queued':
        cancel_queued_order(order_id)
    else:
        cancel_order(order_id)

    # Уведомляем клиента (если client_id известен)
    client_id = order[1]
    if client_id:
        try:
            await bot.send_message(client_id, f"❌ Водій скасував замовлення №{order_id}.", reply_markup=main_menu())
        except:
            pass

    # Очищаем связанные состояния
    chat_sessions.pop(client_id, None)
    chat_sessions.pop(driver_id, None)
    pending_client_geo.pop(client_id, None)
    pending_driver_geo.pop(driver_id, None)

    await callback.message.edit_text(f"❌ Замовлення №{order_id} скасовано.")
    await callback.answer()

@dp.message(F.text == "🔙 В головне меню")
async def driver_back_to_main(message: types.Message):
    await message.answer("Головне меню", reply_markup=get_main_menu(message.from_user.id))

# ========== Клієнтське замовлення ==========
@dp.message(F.text == "🚖 Замовити таксі")
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
    await message.answer(
        "📱 Для замовлення таксі потрібен ваш номер телефону.\n"
        "<i>Він використовується лише для зв'язку водія з вами. "
        "Номер не показується іншим клієнтам і не передається третім особам.</i>",
        parse_mode="HTML"
    )
    await message.answer("Будь ласка, натисніть кнопку нижче, щоб поділитися номером:",
                         reply_markup=contact_request())

@dp.message(F.text == "🕒 Запланувати поїздку (Тестування)")
async def planned_order_start(message: types.Message):
    if not is_workday_active():
        await message.answer(
            "🌙 Зараз неробочий час. Планування тимчасово недоступне.\n"
            "Скористайтеся пізніше або зателефонуйте: +380754436757",
            reply_markup=workday_closed_kb()
        )
        return
    user_state[message.from_user.id] = {"step": "planned_get_time"}
    await message.answer(
        "🕒 <b>Запланована поїздка</b>\n\n"
        "⚠️ <i>Ця функція працює в режимі тестування. Якщо виникнуть проблеми, телефонуйте: +380754436757</i>\n\n"
        "Будь ласка, вкажіть <b>дату та час</b> подачі автомобіля.\n\n"
        "📅 Наприклад: <i>25.12.2026 14:30</i> або <i>завтра 08:15</i>\n\n"
        "✍️ Напишіть дату та час одним повідомленням.",
        parse_mode="HTML",
        reply_markup=planned_time_kb()
    )

@dp.message(F.text, lambda msg: user_state.get(msg.from_user.id, {}).get("step") == "planned_get_time" and msg.text != "⬅ Назад")
async def planned_get_time(message: types.Message):
    uid = message.from_user.id
    text = message.text.strip()
    if not text:
        await message.answer("❌ Введіть дату та час.")
        return
    user_state[uid]["planned_time"] = text
    user_state[uid]["step"] = "get_phone"
    await message.answer(
        f"✅ <b>Час подачі:</b> <i>{text}</i>\n\n"
        "Тепер підтвердьте номер телефону.",
        parse_mode="HTML",
        reply_markup=contact_request()
    )

@dp.message(F.text == "💬 Підтримка")
async def support(message: types.Message):
    await message.answer(f"📞 {SUPPORT_PHONE}\n💬 {TELEGRAM_CONTACT}")

@dp.message(F.contact)
async def contact_received_universal(message: types.Message):
    uid = message.from_user.id
    if uid not in user_state:
        return

    step = user_state[uid].get("step")
    if step not in ("get_phone", "planned_get_phone", "planned_get_time"):
        return

    phone = message.contact.phone_number.replace('+', '').replace('-', '').replace(' ', '')
    if is_blocked(phone):
        reason = get_block_reason(phone)
        reason_text = f"\n\n<i>Причина: {reason}</i>" if reason else ""
        await message.answer(
            f"⛔ <b>Доступ заблоковано</b>\n\n"
            f"Ви більше не можете користуватися сервісом через порушення правил.{reason_text}",
            parse_mode="HTML", reply_markup=main_menu()
        )
        del user_state[uid]
        return

    user_state[uid]["phone"] = phone
    user_state[uid]["step"] = "from_address"
    await message.answer("📍 <b>Звідки вас забрати?</b>", parse_mode="HTML", reply_markup=from_location_method())

@dp.message(F.text == "✏️ Написати адресу вручну")
async def manual_from(message: types.Message):
    uid = message.from_user.id
    if uid not in user_state:
        return
    user_state[uid]["step"] = "waiting_from_text"
    await message.answer("Напишіть адресу подачі:", reply_markup=back_only_keyboard())

@dp.message(F.text == "❌ Скасувати")
async def cancel_order_creation(message: types.Message):
    uid = message.from_user.id
    if uid in user_state:
        del user_state[uid]
    await message.answer("🚫 Замовлення скасовано.", reply_markup=get_main_menu(uid))

@dp.message(F.text == "⬅ Змінити")
async def change_order(message: types.Message):
    uid = message.from_user.id
    if uid not in user_state:
        return
    user_state[uid]["step"] = "to_address"
    user_state[uid].pop("to_address", None)
    user_state[uid].pop("discount_applied", None)
    await message.answer("🏁 <b>Куди їдемо?</b>", parse_mode="HTML", reply_markup=to_location_method())

@dp.message(F.text == "⬅ Назад")
async def go_back(message: types.Message):
    uid = message.from_user.id
    if uid not in user_state:
        await message.answer("Головне меню.", reply_markup=get_main_menu(uid))
        return

    step = user_state[uid].get("step")

    if step == "planned_get_phone":
        del user_state[uid]
        await message.answer("Планування скасовано.", reply_markup=get_main_menu(uid))
    elif step == "planned_time":
        user_state[uid]["step"] = "planned_get_phone"
        await message.answer("Повертаємось до номера телефону.", reply_markup=contact_request())
    elif step in ("planned_from_address", "planned_waiting_from_text"):
        user_state[uid]["step"] = "planned_time"
        user_state[uid].pop("from_address", None)
        user_state[uid].pop("from_lat", None)
        user_state[uid].pop("from_lon", None)
        await message.answer("Введіть дату та час подачі ще раз.", reply_markup=planned_time_kb())
    elif step in ("planned_to_address", "planned_waiting_to_text"):
        user_state[uid]["step"] = "planned_from_address"
        user_state[uid].pop("to_address", None)
        await message.answer("📍 Звідки вас забрати?", reply_markup=from_location_method())
    elif step == "planned_confirm":
        user_state[uid]["step"] = "planned_to_address"
        user_state[uid].pop("to_address", None)
        await message.answer("🏁 Куди їдемо?", reply_markup=to_location_method())
    elif step == "get_phone":
        del user_state[uid]
        await message.answer("Оформлення замовлення скасовано.", reply_markup=get_main_menu(uid))
    elif step in ("from_address", "waiting_from_text"):
        user_state[uid]["step"] = "get_phone"
        await message.answer("Повертаємось до номера телефону.", reply_markup=contact_request())
    elif step in ("to_address", "waiting_to_text"):
        user_state[uid]["step"] = "from_address"
        user_state[uid].pop("to_address", None)
        user_state[uid].pop("from_lat", None)
        user_state[uid].pop("from_lon", None)
        await message.answer("📍 <b>Звідки вас забрати?</b>", parse_mode="HTML", reply_markup=from_location_method())
    elif step == "confirm":
        user_state[uid]["step"] = "to_address"
        user_state[uid].pop("to_address", None)
        user_state[uid].pop("discount_applied", None)
        await message.answer("🏁 <b>Куди їдемо?</b>", parse_mode="HTML", reply_markup=to_location_method())
    else:
        del user_state[uid]
        await message.answer("Головне меню.", reply_markup=get_main_menu(uid))

@dp.message(F.text, lambda msg: user_state.get(msg.from_user.id, {}).get("step") == "waiting_from_text" and msg.text != "⬅ Назад")
async def get_from_text(message: types.Message):
    uid = message.from_user.id
    user_state[uid]["from_address"] = message.text
    user_state[uid]["from_lat"] = user_state[uid]["from_lon"] = None
    user_state[uid]["step"] = "to_address"
    await message.answer(f"Адреса подачі: «{message.text}»")
    await ask_destination(message)

@dp.message(F.location)
async def location_handler(message: types.Message):
    uid = message.from_user.id
    if uid in pending_client_geo:
        driver_id = pending_client_geo.pop(uid)
        try:
            await message.copy_to(driver_id)
            await bot.send_message(driver_id, "📍 Клієнт передав геопозицію.")
        except:
            pass
        else:
            await message.answer("✅ Геопозицію надіслано водієві.", reply_markup=client_driver_found())
        return
    if uid in pending_driver_geo:
        client_id = pending_driver_geo.pop(uid)
        try:
            await message.copy_to(client_id)
            await bot.send_message(client_id, "📍 Водій передає геопозицію.")
        except:
            pass
        else:
            await message.answer("✅ Геопозицію надіслано клієнту.",
                                 reply_markup=driver_order_actions(get_driver_current_order(uid)))
        return
    if uid in user_state:
        step = user_state[uid].get("step")
        if step in ("from_address", "waiting_from_text", "planned_from_address", "planned_waiting_from_text"):
            lat, lon = message.location.latitude, message.location.longitude
            user_state[uid]["from_lat"], user_state[uid]["from_lon"] = lat, lon
            user_state[uid]["from_address"] = f"📍 точка на карті ({lat:.5f}, {lon:.5f})"
            if step.startswith("planned_"):
                user_state[uid]["step"] = "planned_to_address"
            else:
                user_state[uid]["step"] = "to_address"
            await message.answer("Геопозицію отримано!")
            await ask_destination(message)
            return

async def ask_destination(message: types.Message):
    await message.answer("🏁 <b>Куди їдемо?</b>", parse_mode="HTML", reply_markup=to_location_method())

@dp.message(lambda msg: msg.text and msg.text.startswith("🏷 "))
async def popular_place(message: types.Message):
    uid = message.from_user.id
    if uid not in user_state:
        return
    place_name = message.text[2:].strip()
    if user_state[uid].get("step") == "planned_to_address":
        user_state[uid]["to_address"] = place_name
        user_state[uid]["step"] = "planned_confirm"
        await planned_confirm_step(message)
        return
    user_state[uid]["to_address"] = place_name
    user_state[uid]["step"] = "confirm"
    await confirm_order_step(message)

@dp.message(F.text == "✏️ Інша адреса")
async def manual_to(message: types.Message):
    uid = message.from_user.id
    if uid not in user_state:
        return
    if user_state[uid].get("step") == "planned_to_address":
        user_state[uid]["step"] = "planned_waiting_to_text"
        await message.answer("Напишіть адресу призначення:", reply_markup=back_only_keyboard())
        return
    user_state[uid]["step"] = "waiting_to_text"
    await message.answer("Напишіть адресу призначення:", reply_markup=back_only_keyboard())

@dp.message(F.text, lambda msg: user_state.get(msg.from_user.id, {}).get("step") == "waiting_to_text" and msg.text != "⬅ Назад")
async def get_to_text(message: types.Message):
    uid = message.from_user.id
    user_state[uid]["to_address"] = message.text
    user_state[uid]["step"] = "confirm"
    await confirm_order_step(message)

@dp.message(F.text, lambda msg: user_state.get(msg.from_user.id, {}).get("step") == "planned_waiting_to_text" and msg.text != "⬅ Назад")
async def planned_get_to_text(message: types.Message):
    uid = message.from_user.id
    user_state[uid]["to_address"] = message.text
    user_state[uid]["step"] = "confirm"
    await confirm_order_step(message)

@dp.message(F.text, lambda msg: user_state.get(msg.from_user.id, {}).get("step") == "planned_waiting_from_text" and msg.text != "⬅ Назад")
async def planned_get_from_text(message: types.Message):
    uid = message.from_user.id
    user_state[uid]["from_address"] = message.text
    user_state[uid]["from_lat"] = user_state[uid]["from_lon"] = None
    user_state[uid]["step"] = "planned_to_address"
    await message.answer(f"Адреса подачі: «{message.text}»")
    await message.answer("🏁 Куди їдемо?", reply_markup=to_location_method())

async def confirm_order_step(message: types.Message):
    uid = message.from_user.id
    state = user_state.get(uid)
    if not state:
        return

    if 'planned_time' in state:
        from_addr = state.get("from_address") or "не вказано"
        to_addr = state.get("to_address") or "не вказано"
        phone = state.get("phone") or "не вказано"
        planned_time = state.get("planned_time")
        comment = state.get("comment", "")
        comment_text = f"\n💬 Коментар: {comment}" if comment else ""
        summary = (
            f"📋 <b>Запланована поїздка</b>\n\n"
            f"🕒 Час подачі: {planned_time}\n"
            f"📍 Звідки: {from_addr}\n"
            f"🏁 Куди: {to_addr}\n"
            f"📞 Телефон: {phone}"
            f"{comment_text}\n\n"
            f"Підтверджуєте?"
        )
        await message.answer(summary, parse_mode="HTML", reply_markup=confirm_order_kb())
        return

    loyalty = get_loyalty(uid)
    has_discounts = (loyalty and loyalty[1] > 0)
    state["discount_applied"] = has_discounts
    discount_text = "\n💰 Застосовано знижку 50%!" if has_discounts else ""
    phone = state.get("phone") or "не вказано"
    from_addr = state.get("from_address") or "не вказано"
    to_addr = state.get("to_address") or "не вказано"
    comment = state.get("comment", "")
    comment_text = f"\n💬 Коментар: {comment}" if comment else ""
    summary = (
        f"📋 <b>Ваше замовлення:</b>\n"
        f"📍 Звідки: {from_addr}\n"
        f"🏁 Куди: {to_addr}\n"
        f"📞 Телефон: {phone}"
        f"{comment_text}"
        f"{discount_text}\n\n"
        f"<i>⚠️ Будь ласка, підтверджуйте замовлення лише якщо ви дійсно плануєте поїздку.</i>\n"
        f"<i>Неправдиві виклики призводять до блокування акаунта.</i>\n\n"
        f"Все вірно?"
    )
    await message.answer(summary, parse_mode="HTML", reply_markup=apply_discount_kb(has_discounts))

@dp.message(F.text == "✅ Підтвердити замовлення (зі знижкою 50%)")
async def confirm_discount(message: types.Message):
    uid = message.from_user.id
    if uid in user_state:
        user_state[uid]["discount_applied"] = True
    await confirm_order_client(message)

@dp.message(F.text == "💬 Коментар до замовлення")
async def add_comment_prompt(message: types.Message):
    uid = message.from_user.id
    if uid not in user_state:
        return
    user_state[uid]["step"] = "writing_comment"
    await message.answer("✍️ Напишіть ваш коментар до замовлення:", reply_markup=back_only_keyboard())

@dp.message(F.text, lambda msg: user_state.get(msg.from_user.id, {}).get("step") == "writing_comment" and msg.text != "⬅ Назад")
async def receive_comment(message: types.Message):
    uid = message.from_user.id
    text = message.text.strip()
    if not text:
        await message.answer("❌ Коментар не може бути порожнім. Введіть текст або натисніть «⬅ Назад».")
        return
    user_state[uid]["comment"] = text
    user_state[uid]["step"] = "confirm"
    await message.answer(f"✅ Коментар додано: «{text}»")
    await confirm_order_step(message)   # возвращаем к подтверждению

@dp.message(F.text == "✅ Підтвердити замовлення (міжмісто, без знижки)")
async def confirm_no_discount(message: types.Message):
    uid = message.from_user.id
    if uid in user_state:
        user_state[uid]["discount_applied"] = False
    await confirm_order_client(message)

@dp.message(F.text == "✅ Підтвердити замовлення")
async def confirm_order_simple(message: types.Message):
    await confirm_order_client(message)

async def confirm_order_client(message: types.Message):
    uid = message.from_user.id
    state = user_state.get(uid)
    if not state:
        return

    is_planned = 1 if 'planned_time' in state else 0
    planned_time = state.get('planned_time')

    order_id = add_order(
        uid,
        state["from_address"],
        state.get("from_lat"),
        state.get("from_lon"),
        state.get("to_address"),
        state.get("phone"),
        discount=1 if state.get("discount_applied") else 0,
        is_planned=is_planned,
        planned_time=planned_time,
        comment=state.get("comment", "")
    )

    update_client(uid, state.get("phone"), message.from_user.full_name)

    if is_planned:
        # Проверяем, есть ли водители онлайн
        online_drivers = get_online_drivers()
        if online_drivers:
            await notify_drivers(order_id)
            await message.answer(
                "✅ <b>Замовлення створено!</b>\n"
                "🕒 Очікуйте, найближчий водій прийме ваше замовлення.\n"
                "Ви можете відстежувати статус або скасувати поїздку.",
                parse_mode="HTML",
                reply_markup=client_planned_order_kb()
            )
        else:
            await message.answer(
                "⚠️ <b>Наразі немає вільних водіїв.</b>\n\n"
                "Ваше замовлення збережено, але для уточнення часу подачі "
                "зателефонуйте диспетчеру:\n"
                "📞 +380754436757\n\n"
                "Якщо водій з'явиться, замовлення буде опрацьовано автоматично.",
                parse_mode="HTML",
                reply_markup=client_planned_order_kb()
            )
    else:
        # Обычный заказ
        online_drivers = get_online_drivers()
        if online_drivers:
            await notify_drivers(order_id)
            await message.answer("⏳ Шукаємо найближчий автомобіль...", reply_markup=searching_driver_kb())
        else:
            await message.answer(
                "⚠️ <b>Наразі немає вільних водіїв.</b>\n\n"
                "Усі водії зайняті або не на зміні.\n"
                "Будь ласка, зателефонуйте диспетчеру для оформлення замовлення:\n"
                "📞 +380754436757\n\n"
                "<i>Спробуйте пізніше або скористайтесь кнопкою «🕒 Запланувати поїздку».</i>",
                parse_mode="HTML",
                reply_markup=get_main_menu(uid)
            )

    if uid in user_state:
        phone = user_state[uid].get("phone")
        user_state[uid] = {"phone": phone, "step": "from_address"}

async def notify_drivers(order_id):
    order = get_order(order_id)
    if not order:
        return
    online = get_online_drivers()
    if not online:
        return
    try:
        client_user = await bot.get_chat(order[1])
        client_telegram = f"@{client_user.username}" if client_user.username else f"tg://user?id={order[1]}"
        client_name = client_user.full_name or "не вказано"
    except:
        client_telegram = f"tg://user?id={order[1]}"
        client_name = "не вказано"
    client_info = get_client_info(order[8])
    rides_info = ""
    if client_info:
        rides_info = f"🚕 Поїздок: {client_info[3]}"
        if client_info[3] == 0:
            rides_info += " (новий клієнт)"
    discount_msg = "\n💰 Знижка 50% (лояльність)" if order[10] else ""

    # Позначка для запланованої поїздки
    planned_mark = ""
    if len(order) > 15 and order[15] == 1:   # is_planned
        planned_time = order[16] if order[16] else "невідомо"
        planned_mark = f"❗️ <b>Запланована поїздка</b>\n🕒 Час подачі: {planned_time}\n"

    # Коментар до замовлення
    comment_text = ""
    if len(order) > 18 and order[18]:
        comment_text = f"💬 Коментар: {order[18]}\n"

    order_messages[order_id] = []
    for driver_id in online:
        try:
            driver_info_msg = (
                f"🔔 <b>Нове замовлення!</b>\n"
                f"{planned_mark}"
                f"📍 Звідки: {order[4]}\n"
                f"🏁 Куди: {order[7]}\n"
                f"📞 Телефон: {order[8]}\n"
                f"👤 Клієнт: {client_name}\n"
                f"💬 Telegram: {client_telegram}\n"
                f"{rides_info}\n"
                f"{comment_text}"
                f"{discount_msg}"
                f"ID замовлення: {order_id}"
            )
            msg = await bot.send_message(driver_id, driver_info_msg, parse_mode="HTML",
                                         reply_markup=driver_accept_order(order_id))
            order_messages[order_id].append((driver_id, msg.message_id))
            if order[5] is not None:
                await bot.send_location(driver_id, latitude=order[5], longitude=order[6])
        except Exception as e:
            logging.error(f"Failed to notify driver {driver_id}: {e}")

async def send_planned_order_to_driver(order_id, driver_id):
    """Отправляет водителю информацию о плановом заказе, который ещё не принят."""
    order = get_order(order_id)
    if not order or order[3] != 'searching':
        return
    try:
        client_user = await bot.get_chat(order[1])
        client_name = client_user.full_name or "не вказано"
    except:
        client_name = "не вказано"
    planned_time = order[16] if len(order) > 16 and order[16] else "невідомо"
    # Комментарий к заказу (индекс 17, если поле добавлено)
    comment_text = f"\n💬 Коментар: {order[17]}" if len(order) > 17 and order[17] else ""
    text = (
        f"🔔 <b>Активна запланована поїздка!</b>\n"
        f"❗️ <b>Запланована поїздка</b>\n"
        f"🕒 Час подачі: {planned_time}\n"
        f"📍 Звідки: {order[4]}\n"
        f"🏁 Куди: {order[7]}\n"
        f"📞 Телефон: {order[8]}\n"
        f"👤 Клієнт: {client_name}"
        f"{comment_text}\n"
        f"ID замовлення: {order_id}"
    )
    try:
        await bot.send_message(driver_id, text, parse_mode="HTML",
                               reply_markup=driver_accept_order(order_id))
        if order[5] is not None:
            await bot.send_location(driver_id, latitude=order[5], longitude=order[6])
    except Exception as e:
        logging.error(f"Failed to notify driver {driver_id} about planned order {order_id}: {e}")

@dp.message(F.text == "❌ Скасувати замовлення")
async def cancel_searching_order_prompt(message: types.Message):
    uid = message.from_user.id
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute("SELECT id FROM orders WHERE client_id=? AND status='searching' ORDER BY id DESC LIMIT 1", (uid,))
    row = c.fetchone()
    conn.close()
    if not row:
        await message.answer("Немає активного пошуку.", reply_markup=main_menu())
        return
    await message.answer("Ви дійсно бажаєте скасувати пошук?", reply_markup=confirm_cancel_kb(row[0]))

@dp.message(F.text == "✍️ Залишити відгук")
async def review_write_prompt(message: types.Message):
    uid = message.from_user.id
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute("SELECT id FROM orders WHERE client_id=? AND status='finished' AND review IS NULL ORDER BY id DESC LIMIT 1", (uid,))
    row = c.fetchone()
    conn.close()
    if not row:
        await message.answer("Немає замовлення для відгуку.", reply_markup=get_main_menu(message.from_user.id))
        return
    review_state[uid] = row[0]
    await message.answer("Напишіть ваш відгук. Для скасування натисніть «⏭ Пропустити».",
                         reply_markup=skip_review_kb())

@dp.message(F.text, lambda msg: msg.from_user.id in review_state and msg.text != "⏭ Пропустити")
async def review_receive_text(message: types.Message):
    uid = message.from_user.id
    order_id = review_state.pop(uid, None)
    if not order_id:
        return
    review_text = message.text.strip()
    if not review_text:
        await message.answer("Відгук не може бути порожнім.")
        review_state[uid] = order_id
        return
    save_review(order_id, review_text)
    await message.answer("Дякуємо за ваш відгук!", reply_markup=get_main_menu(uid))

# ========== Бонуси ==========
@dp.message(F.text == "🎁 Мої бонуси")
async def show_bonuses(message: types.Message):
    uid = message.from_user.id
    loyalty = get_loyalty(uid)
    rides, discounts = loyalty if loyalty else (0, 0)
    ref_link = f"https://t.me/{(await bot.me()).username}?start=ref{uid}"
    await message.answer(
        f"💳 <b>Ваші бонуси</b>\n"
        f"🚕 Поїздок: {rides}/5\n"
        f"🎟 Доступно знижок 50%: {discounts}\n\n"
        f"Реферальне посилання:\n{ref_link}",
        parse_mode="HTML", reply_markup=bonus_menu()
    )

@dp.message(F.text == "👥 Запросити друга")
async def invite_friend(message: types.Message):
    uid = message.from_user.id
    ref_link = f"https://t.me/{(await bot.me()).username}?start=ref{uid}"
    await message.answer(f"Запросіть друга:\n{ref_link}\nПісля його першої поїздки ви отримаєте знижку 50%.",
                         reply_markup=bonus_menu())

@dp.message(F.text == "🔙 Назад")
async def bonus_back(message: types.Message):
    await message.answer("Головне меню.", reply_markup=get_main_menu(message.from_user.id))

# ========== Чат ==========
@dp.message(F.text == "💬 Повідомлення водію")
async def client_open_chat(message: types.Message):
    uid = message.from_user.id
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute("SELECT id, driver_id FROM orders WHERE client_id=? AND status='accepted' ORDER BY id DESC LIMIT 1", (uid,))
    row = c.fetchone()
    conn.close()
    if not row:
        await message.answer("Немає активного замовлення.")
        return
    _, driver_id = row
    chat_sessions[uid] = (driver_id, 'client')
    chat_sessions[driver_id] = (uid, 'driver')
    # Клиенту показываем клавиатуру чата
    await message.answer("💬 Чат з водієм відкрито. Для виходу натисніть «Завершити чат».",
                         reply_markup=client_chat_active())
    # Водителю тоже отправляем клавиатуру чата и уведомление
    try:
        await bot.send_message(driver_id, "_Пасажир відкрив чат._", parse_mode="Markdown",
                               reply_markup=driver_chat_active())
    except:
        pass

@dp.message(F.text == "🔕 Завершити чат")
async def close_chat(message: types.Message):
    uid = message.from_user.id
    if uid not in chat_sessions:
        await message.answer("Чат не активний.")
        return

    target_id, role = chat_sessions.pop(uid)
    chat_sessions.pop(target_id, None)

    # Уведомляем другого участника, если возможно
    try:
        await bot.send_message(target_id, "🔕 Чат завершено.", reply_markup=get_main_menu(target_id))
    except:
        pass

    # Возвращаем инициатору его меню
    await message.answer("🔕 Чат завершено.", reply_markup=get_main_menu(uid))

@dp.message(lambda msg: msg.from_user.id in chat_sessions)
async def relay_chat_message(message: types.Message):
    uid = message.from_user.id
    target_id, role = chat_sessions[uid]
    prefix = "_Водій:_ " if role == 'driver' else "_Пасажир:_ "
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
        await callback.answer("Замовлення не актуальне.")
        return
    client_id = order[1]
    chat_sessions[driver_id] = (client_id, 'driver')
    chat_sessions[client_id] = (driver_id, 'client')
    # Водитель получает клавиатуру чата
    await bot.send_message(driver_id, "💬 Чат з клієнтом відкрито.", reply_markup=driver_chat_active())
    # Клиенту также отправляем клавиатуру чата и уведомление
    try:
        await bot.send_message(client_id, "_Водій відкрив чат._", parse_mode="Markdown",
                               reply_markup=client_chat_active())
    except:
        pass
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("accept_"))
async def accept_order_handler(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    order_id = int(callback.data.split("_")[1])
    order = get_order(order_id)

    if not order or order[3] != 'searching':
        await callback.answer("Замовлення вже не актуальне.", show_alert=True)
        await callback.message.delete()
        return

    driver = get_driver(driver_id)
    if driver:
        driver_info = {
            "name": driver[1] or callback.from_user.full_name,
            "car": f"{driver[3] or '?'} {driver[4] or '?'}",
            "plate": driver[5] or "не вказано",
            "phone": driver[2] or "не вказано"
        }
    else:
        driver_info = {"name": callback.from_user.full_name, "car": "не вказано", "plate": "не вказано", "phone": "не вказано"}
    driver_info_json = json.dumps(driver_info)

    # --- Плановая поездка ---
    if order[15] == 1:
        accept_order(order_id, driver_id, driver_info_json)
        client_id = order[1]
        client_msg = (
            f"🚖 <b>Водій прийняв замовлення</b>\n"
            f"Ім'я: {driver_info['name']}\nАвто: {driver_info['car']}\nНомер: {driver_info['plate']}\n"
            f"Очікуйте за вказаним часом.\n\n"
            f"⏰ <b>За годину до подачі</b> ми надішлемо вам запит на підтвердження.\n"
            f"Якщо не підтвердите – поїздку буде скасовано."
        )
        try:
            await bot.send_message(client_id, client_msg, parse_mode="HTML", reply_markup=client_driver_found())
        except Exception as e:
            logging.error(f"Notify client {client_id} failed: {e}")
        await callback.message.edit_text(
            f"✅ Ви прийняли замовлення #{order_id} (заплановане)\n📍 {order[4]} → {order[7]}\n📞 Клієнт: {order[8]}",
            reply_markup=driver_order_actions(order_id, False))
        if order_id in order_messages:
            for chat_id, msg_id in order_messages[order_id]:
                if chat_id == driver_id:
                    continue
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=msg_id,
                        text=f"🔔 Замовлення #{order_id} прийнято водієм {driver_info['name']} ({driver_info['car']}, {driver_info['plate']})",
                        reply_markup=None
                    )
                except:
                    pass
            del order_messages[order_id]
        await callback.answer()
        return

    # --- Обычный заказ ---
    current_order = get_driver_current_order(driver_id)
    if current_order:
        if get_driver_queued_order(driver_id):
            await callback.answer("У вас вже є активне замовлення та одне в черзі. Завершіть поточне, щоб прийняти нове.", show_alert=True)
            return
        pending_queue[driver_id] = (order_id, driver_info_json)
        await callback.message.edit_text(
            "⏳ Через скільки хвилин ви плануєте звільнитися?",
            reply_markup=driver_wait_time_kb(order_id)
        )
        await callback.answer()
        return

    # Принимаем заказ сразу (нет активных)
    accept_order(order_id, driver_id, driver_info_json)

    # Запрашиваем время прибытия и сохраняем message_id
    msg = await bot.send_message(
        driver_id,
        f"🚕 Ви прийняли замовлення #{order_id}.\n"
        f"Будь ласка, вкажіть орієнтовний час прибуття до клієнта:",
        reply_markup=driver_eta_kb(order_id)
    )
    pending_eta[driver_id] = (order_id, order[1], driver_info, msg.message_id)

    # Редактируем исходное сообщение с кнопками «Прийняти/Відхилити»
    await callback.message.edit_text(
        f"✅ Ви прийняли замовлення #{order_id}\n📍 {order[4]} → {order[7]}\n📞 Клієнт: {order[8]}",
        reply_markup=None
    )

    # Убираем заказ из рассылки другим водителям
    if order_id in order_messages:
        for chat_id, msg_id in order_messages[order_id]:
            if chat_id == driver_id:
                continue
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=f"🔔 Замовлення #{order_id} прийнято водієм {driver_info['name']} ({driver_info['car']}, {driver_info['plate']})",
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
        await callback.answer("Замовлення вже не актуальне.", show_alert=True)
        await callback.message.edit_text("⛔ Замовлення скасовано.")
        return

    await callback.message.edit_text("⛔ Ви відхилили замовлення.")
    driver_cancel_state[driver_id] = order_id
    await bot.send_message(driver_id, "📝 Вкажіть причину відмови від замовлення:")
    await callback.answer()

@dp.message(lambda msg: msg.from_user.id in driver_cancel_state)
async def driver_cancel_reason(message: types.Message):
    driver_id = message.from_user.id
    data = driver_cancel_state.pop(driver_id)

    # Распаковываем данные (может быть просто order_id, или кортеж)
    if isinstance(data, tuple) and len(data) == 3:
        order_id, orig_msg_id, cause_msg_id = data
    else:
        order_id = data
        orig_msg_id = cause_msg_id = None

    reason = message.text.strip()
    order = get_order(order_id)
    if not order or order[3] not in ('searching', 'queued', 'accepted'):
        await message.answer("Замовлення вже не актуальне.")
        return

    client_id = order[1]

    if order[3] == 'searching':
        cancel_order(order_id)
    elif order[3] == 'queued':
        cancel_queued_order(order_id)
    elif order[3] == 'accepted':
        cancel_order(order_id)

    try:
        await bot.send_message(client_id, f"❌ Водій скасував замовлення (№{order_id}).\nПричина: {reason}", reply_markup=main_menu())
    except:
        pass

    # Редактируем исходное сообщение с кнопками (если есть)
    if orig_msg_id:
        try:
            await bot.edit_message_text("❌ Замовлення скасовано.", chat_id=driver_id, message_id=orig_msg_id)
        except:
            pass

    # Редактируем сообщение с просьбой ввести причину
    if cause_msg_id:
        try:
            await bot.edit_message_text("🚫 Замовлення скасовано.", chat_id=driver_id, message_id=cause_msg_id)
        except:
            pass

    await message.answer("Замовлення скасовано.", reply_markup=driver_main())
    chat_sessions.pop(client_id, None)
    chat_sessions.pop(driver_id, None)
    pending_client_geo.pop(client_id, None)
    pending_driver_geo.pop(driver_id, None)

@dp.callback_query(lambda c: c.data.startswith("eta_"))
async def driver_eta_callback(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    if driver_id not in pending_eta:
        await callback.answer("Дані застаріли або час вже вказано.", show_alert=True)
        return

    data = callback.data.split("_")
    if len(data) != 3:
        return
    order_id = int(data[1])
    minutes = int(data[2])

    saved_order_id, client_id, driver_info, eta_msg_id = pending_eta.pop(driver_id)
    if saved_order_id != order_id:
        await callback.answer("Невірний заказ.", show_alert=True)
        return

    order = get_order(order_id)
    if not order or order[3] != 'accepted':
        await callback.answer("Замовлення вже не актуальне.", show_alert=True)
        return

    # Сохраняем для следующего шага (выбор цены)
    pending_price[driver_id] = (order_id, client_id, driver_info, minutes)

    # Редактируем то же сообщение, в котором были кнопки времени
    await callback.message.edit_text(
        f"🚕 Ви прийняли замовлення #{order_id}.\n"
        f"Орієнтовний час прибуття: <b>{minutes} хв</b>.\n"
        f"Будь ласка, вкажіть орієнтовну вартість поїздки:",
        parse_mode="HTML",
        reply_markup=driver_price_kb(order_id)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("price_"))
async def driver_price_callback(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    if driver_id not in pending_price:
        await callback.answer("Дані застаріли або вартість вже вказано.", show_alert=True)
        return

    data = callback.data.split("_")
    if len(data) != 3:
        return
    order_id = int(data[1])
    price = int(data[2])

    saved_order_id, client_id, driver_info, minutes = pending_price.pop(driver_id)
    if saved_order_id != order_id:
        await callback.answer("Невірний заказ.", show_alert=True)
        return

    order = get_order(order_id)
    if not order or order[3] != 'accepted':
        await callback.answer("Замовлення вже не актуальне.", show_alert=True)
        return

    # Проверяем скидку
    discount = order[10] if len(order) > 10 else 0
    price_text = ""
    if discount == 1:
        final_price = max(0, price // 2)
        price_text = f"💰 <s>{price} грн</s> ➔ <b>{final_price} грн</b> (знижка 50%)"
    else:
        price_text = f"💰 Орієнтовна вартість: <b>{price} грн</b>"

    client_msg = (
        f"🚖 <b>Водія знайдено!</b>\n"
        f"Ім'я: {driver_info['name']}\n"
        f"Авто: {driver_info['car']}\n"
        f"Номер: {driver_info['plate']}\n"
        f"Очікуваний час подачі: ~{minutes} хвилин.\n"
        f"{price_text}"
    )
    try:
        await bot.send_message(client_id, client_msg, parse_mode="HTML", reply_markup=client_confirm_price_kb(order_id))
    except Exception as e:
        logging.error(f"Notify client {client_id} failed: {e}")

    await callback.message.edit_text(
        f"✅ Ви прийняли замовлення #{order_id}.\n"
        f"Орієнтовний час прибуття: <b>{minutes} хв</b>.\n"
        f"Орієнтовна вартість: <b>{price} грн</b>.",
        parse_mode="HTML",
        reply_markup=driver_order_actions(order_id, bool(get_driver_queued_order(driver_id)))
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("wait_"))
async def driver_choose_wait_time(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    data = callback.data.split("_")
    if len(data) != 3:
        return
    order_id = int(data[1])
    minutes = int(data[2])

    if driver_id not in pending_queue or pending_queue[driver_id][0] != order_id:
        await callback.answer("Дані застаріли. Спробуйте знову.", show_alert=True)
        return

    order = get_order(order_id)
    if not order or order[3] != 'searching':
        await callback.answer("Замовлення вже не актуальне.", show_alert=True)
        await callback.message.delete()
        if driver_id in pending_queue:
            del pending_queue[driver_id]
        return

    driver_info_json = pending_queue.pop(driver_id)[1]
    queue_order(order_id, driver_id, driver_info_json)

    await callback.message.edit_text(
        f"✅ Замовлення #{order_id} поставлено в чергу.\n"
        f"Орієнтовний час до звільнення: {minutes} хв.\n"
        f"Воно розпочнеться після завершення поточної поїздки."
    )

    driver = get_driver(driver_id)
    driver_name = driver[1] if driver else callback.from_user.full_name
    car_info = f"{driver[3]} {driver[4]}" if driver else "не вказано"
    plate = driver[5] if driver else "не вказано"

    await bot.send_message(
        order[1],
        "🚖 <b>Ваше замовлення прийнято!</b>\n"
        f"👤 Водій: {driver_name} ({car_info}, {plate})\n\n"
        "⏳ Водій зараз завершує попередню поїздку.\n"
        f"🕒 Орієнтовний час очікування: до {minutes} хвилин.\n\n"
        "📍 Як тільки водій звільниться, він одразу попрямує до вас.",
        parse_mode="HTML",
        reply_markup=client_queued_kb(order_id)
    )

    if order_id in order_messages:
        for chat_id, msg_id in order_messages[order_id]:
            if chat_id == driver_id:
                continue
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=f"🔔 Замовлення #{order_id} прийнято водієм {driver_name} ({car_info}, {plate}) та поставлено в чергу",
                    reply_markup=None
                )
            except:
                pass
        del order_messages[order_id]

    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("custom_price_"))
async def driver_custom_price_prompt(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    if driver_id not in pending_price:
        await callback.answer("Дані застаріли.", show_alert=True)
        return

    data = callback.data.split("_")
    if len(data) < 3:
        return
    order_id = int(data[2])

    saved_order_id, client_id, driver_info, minutes = pending_price.get(driver_id, (None, None, None, None))
    if saved_order_id != order_id:
        await callback.answer("Невірний заказ.", show_alert=True)
        return

    # Редактируем текущее сообщение (с кнопками цены) на приглашение ввести сумму
    await callback.message.edit_text("💬 Введіть суму в гривнях (тільки число):")
    # Сохраняем message_id, чтобы потом заменить это сообщение финальным
    pending_custom_price[driver_id] = (order_id, client_id, driver_info, minutes, callback.message.message_id)
    await callback.answer()

@dp.message(lambda msg: msg.from_user.id in pending_custom_price)
async def custom_price_input(message: types.Message):
    driver_id = message.from_user.id
    if driver_id not in pending_custom_price:
        return

    data = pending_custom_price.pop(driver_id)
    order_id, client_id, driver_info, minutes, msg_id = data

    order = get_order(order_id)
    if not order or order[3] != 'accepted':
        await message.answer("Замовлення вже не актуальне.")
        return

    try:
        price = int(message.text.strip())
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Будь ласка, введіть ціле додатне число (наприклад, 150).")
        pending_custom_price[driver_id] = data
        return

    pending_price.pop(driver_id, None)

    discount = order[10] if len(order) > 10 else 0
    price_text = ""
    if discount == 1:
        final_price = max(0, price // 2)
        price_text = f"💰 <s>{price} грн</s> ➔ <b>{final_price} грн</b> (знижка 50%)"
    else:
        price_text = f"💰 Орієнтовна вартість: <b>{price} грн</b>"

    client_msg = (
        f"🚖 <b>Водія знайдено!</b>\n"
        f"Ім'я: {driver_info['name']}\n"
        f"Авто: {driver_info['car']}\n"
        f"Номер: {driver_info['plate']}\n"
        f"Очікуваний час подачі: ~{minutes} хвилин.\n"
        f"{price_text}"
    )
    try:
        await bot.send_message(client_id, client_msg, parse_mode="HTML", reply_markup=client_confirm_price_kb(order_id))
    except Exception as e:
        logging.error(f"Notify client {client_id} failed: {e}")

    # Редактируем то сообщение, где просили ввести сумму
    try:
        await bot.edit_message_text(
            chat_id=driver_id,
            message_id=msg_id,
            text=f"✅ Ви прийняли замовлення #{order_id}.\n"
                 f"Орієнтовний час прибуття: <b>{minutes} хв</b>.\n"
                 f"Орієнтовна вартість: <b>{price} грн</b>.",
            parse_mode="HTML",
            reply_markup=driver_order_actions(order_id, bool(get_driver_queued_order(driver_id)))
        )
    except Exception as e:
        logging.error(f"Failed to edit custom price message: {e}")
        await message.answer(
            f"✅ Ви прийняли замовлення #{order_id}.\n"
            f"Орієнтовний час прибуття: <b>{minutes} хв</b>.\n"
            f"Орієнтовна вартість: <b>{price} грн</b>.",
            parse_mode="HTML",
            reply_markup=driver_order_actions(order_id, bool(get_driver_queued_order(driver_id)))
        )

@dp.callback_query(lambda c: c.data.startswith("cancel_order_"))
async def driver_cancel_order_prompt(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    order_id = int(callback.data.split("_")[2])
    order = get_order(order_id)
    if not order or order[2] != driver_id or order[3] != 'accepted':
        await callback.answer("Замовлення не знайдено або не є активним.", show_alert=True)
        return

    orig_msg_id = callback.message.message_id
    await callback.message.edit_reply_markup(reply_markup=None)
    msg = await bot.send_message(driver_id, "📝 Вкажіть причину скасування замовлення:")
    driver_cancel_state[driver_id] = (order_id, orig_msg_id, msg.message_id)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("client_confirm_"))
async def client_confirm_price(callback: types.CallbackQuery):
    client_id = callback.from_user.id
    order_id = int(callback.data.split("_")[2])
    order = get_order(order_id)
    if not order or order[1] != client_id or order[3] != 'accepted':
        await callback.answer("Замовлення не знайдено або не активне.", show_alert=True)
        return

    # Убираем кнопки подтверждения
    await callback.message.edit_reply_markup(reply_markup=None)

    # Показываем клиенту обычные кнопки управления поездкой
    await bot.send_message(
        client_id,
        "✅ <b>Поїздку підтверджено!</b>\n"
        "Тепер ви можете зв'язатися з водієм або скасувати поїздку.",
        parse_mode="HTML",
        reply_markup=client_driver_found()
    )

    # Уведомляем водителя, что клиент подтвердил
    driver_id = order[2]
    if driver_id:
        try:
            await bot.send_message(driver_id, "✅ Клієнт підтвердив поїздку.")
        except:
            pass
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("client_cancel_"))
async def client_cancel_price(callback: types.CallbackQuery):
    client_id = callback.from_user.id
    order_id = int(callback.data.split("_")[2])
    order = get_order(order_id)
    if not order or order[1] != client_id or order[3] != 'accepted':
        await callback.answer("Замовлення не знайдено або не активне.", show_alert=True)
        return

    # Отменяем заказ
    cancel_order(order_id)

    # Уведомляем водителя
    driver_id = order[2]
    if driver_id:
        try:
            await bot.send_message(driver_id, f"❌ Клієнт скасував поїздку №{order_id} після отримання ціни.", reply_markup=driver_main())
        except:
            pass

    # Меняем сообщение клиента
    await callback.message.edit_text("❌ Поїздку скасовано.")
    await bot.send_message(client_id, "Ви скасували поїздку та повертаєтесь до головного меню.", reply_markup=get_main_menu(client_id))
    await callback.answer()

# ========== Кнопки активного замовлення (клієнт) ==========
@dp.message(F.text == "📞 Контакти водія")
async def show_driver_contacts(message: types.Message):
    await message.answer("📞 +38 075 443 67 57\n💬 @taxi_artsyz", reply_markup=client_driver_found())

@dp.message(F.text == "📡 Надіслати геопозицію")
async def client_send_geo_prompt(message: types.Message):
    client_id = message.from_user.id
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute("SELECT id, driver_id FROM orders WHERE client_id=? AND status='accepted' ORDER BY id DESC LIMIT 1", (client_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        await message.answer("Немає активного замовлення.")
        return
    pending_client_geo[client_id] = row[1]
    await message.answer("📡 Надішліть ваше поточне місцезнаходження.", reply_markup=request_location_kb())

@dp.message(F.text == "❌ Скасувати поїздку")
async def client_cancel_ride_prompt(message: types.Message):
    client_id = message.from_user.id
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute("SELECT id FROM orders WHERE client_id=? AND status IN ('accepted', 'searching') ORDER BY id DESC LIMIT 1", (client_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        await message.answer("Немає активного замовлення.")
        return
    await message.answer("Ви дійсно бажаєте скасувати поїздку?", reply_markup=confirm_cancel_kb(row[0]))

@dp.message(F.text == "⏳ Чекаю")
async def client_continue_waiting(message: types.Message):
    await message.answer("Дякуємо за очікування! Водій приїде одразу, як звільниться. Ми повідомимо, коли він буде в дорозі.",
                         reply_markup=get_main_menu(message.from_user.id))

@dp.message(F.text == "❌ Скасувати замовлення (черга)")
async def client_cancel_queued_prompt(message: types.Message):
    client_id = message.from_user.id
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute("SELECT id, driver_id FROM orders WHERE client_id=? AND status='queued' ORDER BY id DESC LIMIT 1", (client_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        await message.answer("Немає замовлення в черзі.", reply_markup=get_main_menu(client_id))
        return
    order_id, driver_id = row
    await message.answer("Ви впевнені, що бажаєте скасувати замовлення? Водій вже знає про нього.",
                         reply_markup=confirm_cancel_kb(order_id))

# ========== Callback-обробники ==========
@dp.callback_query(lambda c: c.data.startswith("confirm_cancel_"))
async def confirm_cancel_callback(callback: types.CallbackQuery):
    try:
        order_id = int(callback.data.split("_")[2])
    except:
        return
    order = get_order(order_id)
    if not order:
        return
    if order[3] == 'searching':
        cancel_order(order_id)
        phone = user_state.get(order[1], {}).get("phone")
        if phone:
            user_state[order[1]] = {"phone": phone, "step": "from_address"}
            await bot.send_message(order[1], "🚫 Пошук скасовано. Вкажіть адресу подачі заново.", reply_markup=from_location_method())
        else:
            await bot.send_message(order[1], "🚫 Пошук скасовано.", reply_markup=get_main_menu(order[1]))
        await callback.message.edit_text("🚫 Пошук скасовано.")
    elif order[3] == 'accepted':
        if order[2]:
            try:
                await bot.send_message(order[2], f"❌ Клієнт скасував поїздку (замовлення #{order_id}).", reply_markup=driver_main())
            except:
                pass
        cancel_order(order_id)
        chat_sessions.pop(order[1], None)
        if order[2]:
            chat_sessions.pop(order[2], None)
        pending_client_geo.pop(order[1], None)
        if order[2]:
            pending_driver_geo.pop(order[2], None)
        await callback.message.edit_text("🚫 Поїздку скасовано.")
        await bot.send_message(order[1], "🚫 Поїздку скасовано.", reply_markup=get_main_menu(order[1]))
    elif order[3] == 'queued':
        cancel_queued_order(order_id)
        if order[2]:
            try:
                await bot.send_message(order[2], f"❌ Клієнт скасував замовлення з черги (замовлення #{order_id}).", reply_markup=driver_main())
            except:
                pass
        await callback.message.edit_text("🚫 Замовлення скасовано.")
        await bot.send_message(order[1], "🚫 Замовлення скасовано.", reply_markup=get_main_menu(order[1]))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("decline_cancel_"))
async def decline_cancel_callback(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[2])
    order = get_order(order_id)
    if not order:
        return
    if order[3] == 'searching':
        await callback.message.edit_text("⏳ Продовжуємо пошук...")
        await bot.send_message(order[1], "⏳ Шукаємо найближчий автомобіль...", reply_markup=searching_driver_kb())
    elif order[3] == 'accepted':
        await callback.message.edit_text("Поїздка продовжується.")
        await bot.send_message(order[1], "Поїздка продовжується.", reply_markup=client_driver_found())
    elif order[3] == 'queued':
        await callback.message.edit_text("Очікування продовжується.")
        await bot.send_message(order[1], "Очікування продовжується.", reply_markup=client_queued_kb(order_id))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("req_loc_"))
async def request_client_location(callback: types.CallbackQuery):
    order = get_order(int(callback.data.split("_")[2]))
    if not order:
        return
    pending_client_geo[order[1]] = callback.from_user.id
    await bot.send_message(order[1], "📍 Водій запитує ваше місцезнаходження.", reply_markup=request_location_kb())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("cancel_queued_"))
async def cancel_queued_order_by_driver(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    order_id = int(callback.data.split("_")[2])
    order = get_order(order_id)
    if not order or order[3] != 'queued' or order[2] != driver_id:
        await callback.answer("Замовлення не знайдено або не в черзі.")
        return
    cancel_queued_order(order_id)
    try:
        await bot.send_message(order[1], "❌ Водій скасував ваше замовлення з черги. Приносимо вибачення.", reply_markup=main_menu())
    except:
        pass
    await bot.send_message(driver_id, "Замовлення з черги скасовано.")
    current_order_id = get_driver_current_order(driver_id)
    if current_order_id:
        await bot.send_message(driver_id, "Поточне замовлення:", reply_markup=driver_order_actions(current_order_id, False))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("arrived_"))
async def driver_arrived(callback: types.CallbackQuery):
    order = get_order(int(callback.data.split("_")[1]))
    if not order:
        return
    client_id = order[1]
    await bot.send_message(client_id, "🚕 <b>Водій на місці!</b>", parse_mode="HTML", reply_markup=client_after_arrived())
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛑 Завершити поїздку", callback_data=f"finish_{order[0]}")]
        ]))
    await callback.answer("Клієнта повідомлено.")

@dp.callback_query(lambda c: c.data.startswith("finish_"))
async def driver_finish(callback: types.CallbackQuery):
    driver_id = callback.from_user.id
    order_id = int(callback.data.split("_")[1])
    order = get_order(order_id)
    if not order:
        await callback.answer("Замовлення не знайдено.")
        return
    client_id = order[1]
    process_finished_order(order_id)

    await bot.send_message(client_id, "🏁 <b>Поїздку завершено.</b> Дякуємо!", parse_mode="HTML", reply_markup=get_main_menu(client_id))
    await bot.send_message(client_id, "Оцініть поїздку:", reply_markup=rating_keyboard(order_id))

    queued_id = activate_queued_order(driver_id)
    if queued_id:
        queued_order = get_order(queued_id)
        if queued_order:
            await bot.send_message(queued_order[1],
                "🚖 Водій звільнився та їде до вас! Очікуваний час подачі: ~5 хвилин.",
                reply_markup=client_driver_found())
            await bot.send_message(driver_id,
                f"🔜 Наступне замовлення #{queued_id} активовано.\n📍 {queued_order[4]} → {queued_order[7]}\n📞 Клієнт: {queued_order[8]}",
                reply_markup=driver_order_actions(queued_id, False))
    else:
        await callback.message.edit_text("Поїздку завершено. Очікуйте нове замовлення.")
    await callback.answer()
    chat_sessions.pop(client_id, None)
    chat_sessions.pop(driver_id, None)

@dp.message(F.text.in_(["🏃 Вже йду", "⏳ Буду через 5 хв", "📍 Я на місці"]))
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
        await bot.send_message(driver_id, f"📩 Повідомлення від клієнта (замовлення #{order_id}): «{message.text}»")
        await message.answer("✅ Водій отримав повідомлення.")
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
            await bot.send_message(order[2], f"📊 Оцінка за замовлення №{order_id}: {'⭐'*stars} ({stars}/5)")
        if stars <= 3:
            msg = "Дякуємо за оцінку. Нам шкода, що поїздка не була ідеальною. Напишіть, що можна покращити?"
        else:
            msg = "Дякуємо за високу оцінку! Будемо раді, якщо ви залишите відгук."
        await callback.message.edit_text(f"Оцінка: {stars}⭐")
        await bot.send_message(order[1], msg, reply_markup=review_prompt_kb(order_id))
    except:
        pass
    await callback.answer()

@dp.message(F.text == "✍️ Залишити відгук")
async def review_write_prompt(message: types.Message):
    uid = message.from_user.id
    conn = sqlite3.connect("taxi.db")
    c = conn.cursor()
    c.execute("SELECT id FROM orders WHERE client_id=? AND status='finished' AND review IS NULL ORDER BY id DESC LIMIT 1", (uid,))
    row = c.fetchone()
    conn.close()
    if not row:
        await message.answer("Немає замовлення для відгуку.", reply_markup=main_menu())
        return
    review_state[uid] = row[0]
    await message.answer("Напишіть ваш відгук. Для скасування натисніть «⏭ Пропустити».", reply_markup=skip_review_kb())

@dp.message(F.text == "⏭ Пропустити")
async def review_skip(message: types.Message):
    uid = message.from_user.id
    review_state.pop(uid, None)
    await message.answer("Дякуємо за поїздку!", reply_markup=get_main_menu(message.from_user.id))

@dp.message(F.text, lambda msg: msg.from_user.id in review_state)
async def review_receive_text(message: types.Message):
    uid = message.from_user.id
    order_id = review_state.pop(uid, None)
    if not order_id:
        return
    review_text = message.text.strip()
    if not review_text:
        await message.answer("Відгук не може бути порожнім.")
        review_state[uid] = order_id
        return
    save_review(order_id, review_text)
    await message.answer("Дякуємо за ваш відгук!", reply_markup=get_main_menu(uid))

@dp.message(F.text == "📋 Мої поїздки")
async def show_history(message: types.Message):
    orders = get_client_last_orders(message.from_user.id)
    if not orders:
        await message.answer("У вас ще немає поїздок.", reply_markup=get_main_menu(message.from_user.id))
        return
    text = "<b>Останні поїздки:</b>\n\n"
    for o in orders:
        rating_value = o[13] if len(o) > 13 else None
        if rating_value is not None:
            rating_value = int(rating_value)
        rating_str = f" {'⭐'*rating_value}" if rating_value else ""
        created_date = o[11][:10] if o[11] else "?"
        text += (f"🚕 {created_date}\n📍 {o[4]} → {o[7]}\nСтатус: {o[3]}{rating_str}\n\n")
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🔙 Повернутися в головне меню")
async def closed_back_to_main(message: types.Message):
    await message.answer("Повертаємось до головного меню.", reply_markup=get_main_menu(message.from_user.id))

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("🔐 Адмін-панель:", reply_markup=admin_menu())

@dp.message(F.text == "🔐 Адмін-панель")
async def admin_panel_button(message: types.Message):
    await cmd_admin(message)

@dp.message(F.text == "🚘 Кабінет водія")
async def driver_cabinet_button(message: types.Message):
    await cmd_driver(message)

# ========== Нагадування за годину (фонова задача) ==========
async def check_planned_reminders():
    while True:
        try:
            orders = get_planned_orders_to_remind()
            for order in orders:
                order_id, client_id, driver_id, planned_time = order
                await bot.send_message(
                    client_id,
                    f"⏰ <b>Нагадування!</b>\n"
                    f"Ваша запланована поїздка за годину.\n"
                    f"🕒 Час подачі: {planned_time if planned_time else 'невідомо'}\n\n"
                    f"Будь ласка, підтвердіть актуальність замовлення.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="✅ Підтвердити", callback_data=f"confirm_planned_{order_id}")],
                            [InlineKeyboardButton(text="❌ Скасувати", callback_data=f"cancel_planned_{order_id}")]
                        ]
                    )
                )
                set_planned_reminded_order(order_id)
        except Exception as e:
            logging.error(f"Planned reminders error: {e}")
        await asyncio.sleep(60)

@dp.callback_query(lambda c: c.data.startswith("confirm_planned_"))
async def confirm_planned(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[2])
    order = get_order(order_id)
    if not order:
        await callback.answer("Замовлення не знайдено.")
        return
    driver_id = order[2]
    if driver_id:
        try:
            await bot.send_message(driver_id, f"✅ Клієнт підтвердив заплановану поїздку №{order_id}. Час подачі: {order[16]}")
        except:
            pass
    await callback.message.edit_text("✅ Ви підтвердили поїздку. Водій чекатиме вас у зазначений час.")
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("cancel_planned_"))
async def cancel_planned(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[2])
    order = get_order(order_id)
    if not order:
        await callback.answer("Замовлення не знайдено.")
        return
    cancel_order(order_id)
    driver_id = order[2]
    if driver_id:
        try:
            await bot.send_message(driver_id, f"❌ Клієнт скасував заплановану поїздку №{order_id}. Замовлення відмінено.")
        except:
            pass
    await callback.message.edit_text("❌ Замовлення скасовано.")
    await callback.answer()

# ========== Запуск ==========
async def main():
    init_db()
    asyncio.create_task(check_planned_reminders())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
