import os
import logging
import re
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, ConversationHandler
import sqlite3

# Настройка расширенного логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
(ADDING_CLIENT_NAME, ADDING_CLIENT_PHONE, 
 SELECTING_CLIENT_FOR_RECEIPT, UPLOADING_RECEIPT, ADDING_RECEIPT_AMOUNT, ADDING_DEBT_DAYS,
 SELECTING_CLIENT_FOR_VIEW,
 SELECTING_CLIENT_FOR_DELETE, SELECTING_RECEIPT_FOR_DELETE,
 SELECTING_CLIENT_FOR_PAYMENT, ADDING_PAYMENT_AMOUNT) = range(11)

def get_connection():
    """Создание подключения к базе данных."""
    try:
        return sqlite3.connect('debt_bot.db')
    except sqlite3.Error as e:
        logger.error(f"Ошибка подключения к базе данных: {e}")
        raise

def init_db():
    """Инициализация таблиц базы данных."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Таблица клиентов
        cur.execute('''CREATE TABLE IF NOT EXISTS clients
                   (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    phone TEXT NOT NULL)''')
        
        # Таблица чеков
        cur.execute('''CREATE TABLE IF NOT EXISTS receipts
                   (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER,
                    photo_id TEXT,
                    amount REAL,
                    debt_days INTEGER,
                    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (client_id) REFERENCES clients (id))''')
        
        # Таблица платежей
        cur.execute('''CREATE TABLE IF NOT EXISTS payments
                   (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER,
                    amount REAL,
                    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (client_id) REFERENCES clients (id))''')
        
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Ошибка инициализации базы данных: {e}")
        raise
    finally:
        if conn:
            cur.close()
            conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    logger.info(f"Пользователь {update.effective_user.id} запустил бота")
    
    keyboard = [
        [KeyboardButton("👤 Добавить клиента"), KeyboardButton("📄 Добавить чек")],
        [KeyboardButton("👁 Просмотр чеков"), KeyboardButton("⏰ Просроченные долги")],
        [KeyboardButton("🗑 Удаление чеков"), KeyboardButton("💰 Оплата долгов")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        'Выберите действие:',
        reply_markup=reply_markup
    )

async def add_client_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало добавления клиента"""
    logger.info(f"Пользователь {update.effective_user.id} начал добавление клиента")
    await update.message.reply_text("Введите имя клиента:")
    return ADDING_CLIENT_NAME

async def add_client_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка имени клиента"""
    name = update.message.text.strip()
    
    if not name or len(name) > 100:
        await update.message.reply_text("Пожалуйста, введите корректное имя (1-100 символов).")
        return ADDING_CLIENT_NAME
    
    context.user_data['client_name'] = name
    await update.message.reply_text("Введите номер телефона клиента:")
    return ADDING_CLIENT_PHONE

async def add_client_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка номера телефона и сохранение клиента"""
    phone = update.message.text.strip()
    name = context.user_data['client_name']
    
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Проверка существования клиента
        cur.execute("SELECT id FROM clients WHERE name = ? AND phone = ?", (name, phone))
        existing_client = cur.fetchone()
        
        if existing_client:
            await update.message.reply_text(f"Клиент {name} уже существует!")
            return ConversationHandler.END
        
        # Добавление нового клиента
        cur.execute("INSERT INTO clients (name, phone) VALUES (?, ?)", (name, phone))
        conn.commit()
        logger.info(f"Добавлен новый клиент: {name}, {phone}")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при добавлении клиента: {e}")
        await update.message.reply_text("Произошла ошибка при добавлении клиента.")
        return ConversationHandler.END
    finally:
        if conn:
            cur.close()
            conn.close()
    
    keyboard = [
        [KeyboardButton("👤 Добавить клиента"), KeyboardButton("📄 Добавить чек")],
        [KeyboardButton("👁 Просмотр чеков"), KeyboardButton("⏰ Просроченные долги")],
        [KeyboardButton("🗑 Удаление чеков"), KeyboardButton("💰 Оплата долгов")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        f"Клиент {name} успешно добавлен!",
        reply_markup=reply_markup
    )
    return ConversationHandler.END

async def add_receipt_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса добавления чека - выбор клиента"""
    logger.info(f"Пользователь {update.effective_user.id} начал добавление чека")
    
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM clients")
        clients = cur.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении списка клиентов: {e}")
        await update.message.reply_text("Не удалось получить список клиентов. Попробуйте позже.")
        return ConversationHandler.END
    finally:
        if conn:
            cur.close()
            conn.close()
    
    if not clients:
        await update.message.reply_text("Сначала добавьте клиента!")
        return ConversationHandler.END
    
    # Создаем клавиатуру с клиентами
    keyboard = []
    for client_id, client_name in clients:
        keyboard.append([InlineKeyboardButton(client_name, callback_data=f'client_{client_id}')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Выберите клиента для добавления чека:",
        reply_markup=reply_markup
    )
    return SELECTING_CLIENT_FOR_RECEIPT

async def select_client_for_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора клиента для чека"""
    query = update.callback_query
    await query.answer()
    
    try:
        client_id = int(query.data.split('_')[1])
        context.user_data['selected_client_id'] = client_id
        
        await query.edit_message_text("Теперь отправьте фото чека:")
        return UPLOADING_RECEIPT
    except Exception as e:
        logger.error(f"Ошибка при выборе клиента: {e}")
        await query.edit_message_text("Произошла ошибка. Попробуйте снова.")
        return ConversationHandler.END

async def handle_receipt_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фото чека"""
    try:
        # Получаем файл с наибольшим разрешением
        photo = update.message.photo[-1]
        context.user_data['receipt_photo_id'] = photo.file_id
        
        await update.message.reply_text("Введите сумму чека:")
        return ADDING_RECEIPT_AMOUNT
    except Exception as e:
        logger.error(f"Ошибка при обработке фото чека: {e}")
        await update.message.reply_text("Не удалось сохранить фото. Попробуйте снова.")
        return ConversationHandler.END

async def add_receipt_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка суммы чека"""
    try:
        amount = float(update.message.text.replace(',', '.'))
        
        if amount <= 0:
            await update.message.reply_text("Сумма должна быть положительной. Введите корректную сумму:")
            return ADDING_RECEIPT_AMOUNT
        
        context.user_data['receipt_amount'] = amount
        await update.message.reply_text("Введите количество дней для оплаты долга:")
        return ADDING_DEBT_DAYS
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректную сумму:")
        return ADDING_RECEIPT_AMOUNT

async def add_receipt_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение добавления чека"""
    conn = None
    try:
        days = int(update.message.text)
        
        if days <= 0:
            await update.message.reply_text("Количество дней должно быть положительным. Введите корректное число:")
            return ADDING_DEBT_DAYS
        
        # Получаем сохраненные данные
        client_id = context.user_data.get('selected_client_id')
        photo_id = context.user_data.get('receipt_photo_id')
        amount = context.user_data.get('receipt_amount')
        
        # Проверяем, что все данные есть
        if not all([client_id, photo_id, amount]):
            await update.message.reply_text("Произошла ошибка. Начните процесс добавления чека заново.")
            return ConversationHandler.END
        
        # Сохраняем чек в базу данных
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO receipts 
            (client_id, photo_id, amount, debt_days, date_added)
            VALUES (?, ?, ?, ?, ?)
        """, (client_id, photo_id, amount, days, datetime.now()))
        conn.commit()
        
        logger.info(f"Добавлен новый чек для клиента {client_id}")
        
        # Возвращаем главное меню
        keyboard = [
            [KeyboardButton("👤 Добавить клиента"), KeyboardButton("📄 Добавить чек")],
            [KeyboardButton("👁 Просмотр чеков"), KeyboardButton("⏰ Просроченные долги")],
            [KeyboardButton("🗑 Удаление чеков"), KeyboardButton("💰 Оплата долгов")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "Чек успешно добавлен!",
            reply_markup=reply_markup
        )
        
        return ConversationHandler.END
    
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректное количество дней:")
        return ADDING_DEBT_DAYS
    except sqlite3.Error as e:
        logger.error(f"Ошибка при сохранении чека: {e}")
        await update.message.reply_text("Не удалось сохранить чек. Попробуйте снова.")
        return ConversationHandler.END
    finally:
        if conn:
            conn.close()

async def view_receipts_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало просмотра чеков - выбор клиента"""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM clients")
        clients = cur.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении списка клиентов: {e}")
        await update.message.reply_text("Не удалось получить список клиентов. Попробуйте позже.")
        return ConversationHandler.END
    finally:
        if conn:
            cur.close()
            conn.close()
    
    if not clients:
        await update.message.reply_text("Нет добавленных клиентов!")
        return ConversationHandler.END
    
    # Создаем клавиатуру с клиентами
    keyboard = []
    for client_id, client_name in clients:
        keyboard.append([InlineKeyboardButton(client_name, callback_data=f'view_{client_id}')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Выберите клиента для просмотра чеков:",
        reply_markup=reply_markup
    )
    return SELECTING_CLIENT_FOR_VIEW

async def show_client_receipts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ чеков для выбранного клиента"""
    query = update.callback_query
    await query.answer()
    
    try:
        client_id = int(query.data.split('_')[1])
        
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT photo_id, amount, date_added, debt_days 
            FROM receipts 
            WHERE client_id = ? 
            ORDER BY date_added DESC
        """, (client_id,))
        receipts = cur.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении чеков: {e}")
        await query.edit_message_text("Не удалось получить чеки. Попробуйте позже.")
        return ConversationHandler.END
    finally:
        if conn:
            cur.close()
            conn.close()
    
    if not receipts:
        await query.edit_message_text("У этого клиента нет чеков.")
        return ConversationHandler.END
    
    # Отправляем каждый чек отдельным сообщением
    for photo_id, amount, date_added, debt_days in receipts:
        # Вычисляем дату погашения долга
        due_date = datetime.strptime(date_added, '%Y-%m-%d %H:%M:%S.%f') + timedelta(days=debt_days)
        
        caption = (f"Сумма: {amount} руб.\n"
                   f"Дата добавления: {date_added}\n"
                   f"Срок оплаты: {due_date}")
        
        try:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=photo_id,
                caption=caption
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке фото чека: {e}")
    
    # Возвращаем главное меню
    keyboard = [
        [KeyboardButton("👤 Добавить клиента"), KeyboardButton("📄 Добавить чек")],
        [KeyboardButton("👁 Просмотр чеков"), KeyboardButton("⏰ Просроченные долги")],
        [KeyboardButton("🗑 Удаление чеков"), KeyboardButton("💰 Оплата долгов")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Вернуться в главное меню:",
        reply_markup=reply_markup
    )
    
    return ConversationHandler.END

async def show_overdue_debts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ просроченных долгов"""
    logger.info(f"Пользователь {update.effective_user.id} запросил список просроченных долгов")
    
    current_time = datetime.now()
    
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                c.name, 
                r.amount, 
                r.date_added, 
                r.debt_days,
                COALESCE((
                    SELECT SUM(amount) 
                    FROM payments p 
                    WHERE p.client_id = r.client_id
                ), 0) as paid_amount
            FROM receipts r
            JOIN clients c ON r.client_id = c.id
            WHERE datetime(r.date_added, '+' || r.debt_days || ' days') < ?
        """, (current_time,))
        overdue = cur.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении просроченных долгов: {e}")
        await update.message.reply_text("Произошла ошибка при получении списка долгов.")
        return
    finally:
        if conn:
            cur.close()
            conn.close()
    
    keyboard = [
        [KeyboardButton("👤 Добавить клиента"), KeyboardButton("📄 Добавить чек")],
        [KeyboardButton("👁 Просмотр чеков"), KeyboardButton("⏰ Просроченные долги")],
        [KeyboardButton("🗑 Удаление чеков"), KeyboardButton("💰 Оплата долгов")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    if not overdue:
        await update.message.reply_text(
            "Нет просроченных долгов.",
            reply_markup=reply_markup
        )
        return
    
    message = "Просроченные долги:\n\n"
    for name, amount, date_added, days, paid_amount in overdue:
        if amount > paid_amount:
            remaining_debt = amount - paid_amount
            due_date = datetime.strptime(date_added, '%Y-%m-%d %H:%M:%S.%f') + timedelta(days=days)
            
            message += f"Клиент: {name}\n"
            message += f"Оставшийся долг: {remaining_debt} руб.\n"
            message += f"Дата чека: {date_added}\n"
            message += f"Срок оплаты: {due_date}\n\n"
    
    await update.message.reply_text(
        message,
        reply_markup=reply_markup
    )

async def delete_receipt_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса удаления чека - выбор клиента"""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM clients")
        clients = cur.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении списка клиентов: {e}")
        await update.message.reply_text("Не удалось получить список клиентов. Попробуйте позже.")
        return ConversationHandler.END
    finally:
        if conn:
            cur.close()
            conn.close()
    
    if not clients:
        await update.message.reply_text("Нет добавленных клиентов!")
        return ConversationHandler.END
    
    # Создаем клавиатуру с клиентами
    keyboard = []
    for client_id, client_name in clients:
        keyboard.append([InlineKeyboardButton(client_name, callback_data=f'del_client_{client_id}')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Выберите клиента для удаления чека:",
        reply_markup=reply_markup
    )
    return SELECTING_CLIENT_FOR_DELETE

async def show_receipts_for_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ чеков для удаления"""
    query = update.callback_query
    await query.answer()
    
    try:
        client_id = int(query.data.split('_')[2])
        context.user_data['selected_client_id'] = client_id
        
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, photo_id, amount, date_added 
            FROM receipts 
            WHERE client_id = ?
        """, (client_id,))
        receipts = cur.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении чеков для удаления: {e}")
        await query.edit_message_text("Не удалось получить чеки. Попробуйте позже.")
        return ConversationHandler.END
    finally:
        if conn:
            cur.close()
            conn.close()
    
    if not receipts:
        await query.edit_message_text("У этого клиента нет чеков.")
        return ConversationHandler.END
    
    # Отправляем каждый чек с кнопкой удаления
    for receipt_id, photo_id, amount, date_added in receipts:
        keyboard = [[InlineKeyboardButton(
            "Удалить этот чек", 
            callback_data=f'delete_receipt_{receipt_id}'
        )]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        caption = f"Сумма: {amount} руб.\nДата: {date_added}"
        
        try:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=photo_id,
                caption=caption,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке фото чека: {e}")
    
    return SELECTING_RECEIPT_FOR_DELETE

async def delete_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаление выбранного чека"""
    query = update.callback_query
    await query.answer()
    
    try:
        receipt_id = int(query.data.split('_')[2])
        
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM receipts WHERE id = ?", (receipt_id,))
        conn.commit()
        
        logger.info(f"Удален чек с ID: {receipt_id}")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при удалении чека: {e}")
        await query.edit_message_text("Не удалось удалить чек. Попробуйте позже.")
        return ConversationHandler.END
    finally:
        if conn:
            cur.close()
            conn.close()
    
    keyboard = [
        [KeyboardButton("👤 Добавить клиента"), KeyboardButton("📄 Добавить чек")],
        [KeyboardButton("👁 Просмотр чеков"), KeyboardButton("⏰ Просроченные долги")],
        [KeyboardButton("🗑 Удаление чеков"), KeyboardButton("💰 Оплата долгов")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await query.edit_message_text(
        "Чек успешно удален!",
        reply_markup=reply_markup
    )
    return ConversationHandler.END

async def pay_debt_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса оплаты долга"""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                c.id, 
                c.name, 
                TOTAL(r.amount) - COALESCE((
                    SELECT TOTAL(amount) 
                    FROM payments p 
                    WHERE p.client_id = c.id
                ), 0) as debt
            FROM clients c
            LEFT JOIN receipts r ON c.id = r.client_id
            GROUP BY c.id, c.name
            HAVING debt > 0
        """)
        clients = cur.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении списка должников: {e}")
        await update.message.reply_text("Не удалось получить список должников. Попробуйте позже.")
        return ConversationHandler.END
    finally:
        if conn:
            cur.close()
            conn.close()
    
    if not clients:
        await update.message.reply_text("Нет клиентов с долгами.")
        return ConversationHandler.END
    
    keyboard = []
    for client_id, name, debt in clients:
        keyboard.append([InlineKeyboardButton(
            f"{name} (Долг: {debt} руб.)", 
            callback_data=f'pay_{client_id}'
        )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Выберите клиента для оплаты долга:",
        reply_markup=reply_markup
    )
    return SELECTING_CLIENT_FOR_PAYMENT

async def add_payment_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор суммы платежа"""
    query = update.callback_query
    await query.answer()
    
    try:
        client_id = int(query.data.split('_')[1])
        context.user_data['selected_client_id'] = client_id
        
        await query.edit_message_text("Введите сумму оплаты:")
        return ADDING_PAYMENT_AMOUNT
    except Exception as e:
        logger.error(f"Ошибка при выборе клиента для оплаты: {e}")
        await query.edit_message_text("Произошла ошибка. Попробуйте снова.")
        return ConversationHandler.END

async def process_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка платежа"""
    try:
        amount = float(update.message.text.replace(',', '.'))
        client_id = context.user_data['selected_client_id']
        
        conn = get_connection()
        cur = conn.cursor()
        
        # Добавление платежа
        cur.execute("""
            INSERT INTO payments (client_id, amount, date)
            VALUES (?, ?, ?)
        """, (client_id, amount, datetime.now()))
        
        # Получение информации о клиенте и остатке долга
        cur.execute("""
            SELECT 
                c.name, 
                TOTAL(r.amount) - (COALESCE((
                    SELECT TOTAL(amount) 
                    FROM payments p 
                    WHERE p.client_id = c.id
                ), 0) + ?) as remaining_debt
            FROM clients c
            JOIN receipts r ON c.id = r.client_id
            WHERE c.id = ?
            GROUP BY c.name
        """, (amount, client_id))
        
        result = cur.fetchone()
        client_name, remaining_debt = result if result else (None, 0)
        
        conn.commit()
        
        logger.info(f"Добавлен платеж для клиента {client_id}: {amount} руб.")
        
        # Возвращаем главное меню
        keyboard = [
            [KeyboardButton("👤 Добавить клиента"), KeyboardButton("📄 Добавить чек")],
            [KeyboardButton("👁 Просмотр чеков"), KeyboardButton("⏰ Просроченные долги")],
            [KeyboardButton("🗑 Удаление чеков"), KeyboardButton("💰 Оплата долгов")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        message = f"Оплата в размере {amount} руб. добавлена для клиента {client_name}\n"
        if remaining_debt and remaining_debt > 0:
            message += f"Оставшийся долг: {remaining_debt} руб."
        else:
            message += "Долг полностью погашен!"
        
        await update.message.reply_text(
            message,
            reply_markup=reply_markup)
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректную сумму.")
        return ADDING_PAYMENT_AMOUNT
    except sqlite3.Error as e:
        logger.error(f"Ошибка при обработке платежа: {e}")
        await update.message.reply_text("Произошла ошибка при обработке платежа.")
        return ConversationHandler.END
    finally:
        if conn:
            cur.close()
            conn.close()
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена текущей операции"""
    logger.info(f"Пользователь {update.effective_user.id} отменил операцию")
    
    keyboard = [
        [KeyboardButton("👤 Добавить клиента"), KeyboardButton("📄 Добавить чек")],
        [KeyboardButton("👁 Просмотр чеков"), KeyboardButton("⏰ Просроченные долги")],
        [KeyboardButton("🗑 Удаление чеков"), KeyboardButton("💰 Оплата долгов")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        'Операция отменена.',
        reply_markup=reply_markup
    )
    return ConversationHandler.END

def main():
    """Основная функция запуска бота"""
    # Проверка токена бота
    token = os.environ.get('BOT_TOKEN')
    if not token:
        logger.error("Не указан токен Telegram Bot. Установите переменную окружения BOT_TOKEN.")
        return
    
    # Инициализация базы данных
    try:
        init_db()
    except Exception as db_error:
        logger.error(f"Ошибка инициализации базы данных: {db_error}")
        return
    
    # Создание приложения бота
    try:
        application = Application.builder().token(token).build()
        
        # Добавление обработчиков команд
        application.add_handler(CommandHandler('start', start))
        
        # Добавление клиента
        add_client_conv = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex('^👤 Добавить клиента$'), add_client_start)],
            states={
                ADDING_CLIENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_name)],
                ADDING_CLIENT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_phone)]
            },
            fallbacks=[CommandHandler('cancel', cancel)]
        )
        application.add_handler(add_client_conv)
        
        # Добавление чека
        add_receipt_conv = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex('^📄 Добавить чек$'), add_receipt_start)],
            states={
                SELECTING_CLIENT_FOR_RECEIPT: [
                    CallbackQueryHandler(select_client_for_receipt, pattern='^client_')
                ],
                UPLOADING_RECEIPT: [MessageHandler(filters.PHOTO, handle_receipt_photo)],
                ADDING_RECEIPT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_receipt_amount)],
                ADDING_DEBT_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_receipt_days)]
            },
            fallbacks=[CommandHandler('cancel', cancel)]
        )
        application.add_handler(add_receipt_conv)
        
        # Просмотр чеков
        view_receipts_conv = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex('^👁 Просмотр чеков$'), view_receipts_start)],
            states={
                SELECTING_CLIENT_FOR_VIEW: [CallbackQueryHandler(show_client_receipts, pattern='^view_')]
            },
            fallbacks=[CommandHandler('cancel', cancel)]
        )
        application.add_handler(view_receipts_conv)
        
        # Просроченные долги
        application.add_handler(MessageHandler(filters.Regex('^⏰ Просроченные долги$'), show_overdue_debts))
        
        # Удаление чека
        delete_receipt_conv = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex('^🗑 Удаление чеков$'), delete_receipt_start)],
            states={
                SELECTING_CLIENT_FOR_DELETE: [
                    CallbackQueryHandler(show_receipts_for_delete, pattern='^del_client_')
                ],
                SELECTING_RECEIPT_FOR_DELETE: [
                    CallbackQueryHandler(delete_receipt, pattern='^delete_receipt_')
                ]
            },
            fallbacks=[CommandHandler('cancel', cancel)]
        )
        application.add_handler(delete_receipt_conv)
        
        # Оплата долга
        pay_debt_conv = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex('^💰 Оплата долгов$'), pay_debt_start)],
            states={
                SELECTING_CLIENT_FOR_PAYMENT: [
                    CallbackQueryHandler(add_payment_amount, pattern='^pay_')
                ],
                ADDING_PAYMENT_AMOUNT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, process_payment)
                ]
            },
            fallbacks=[CommandHandler('cancel', cancel)]
        )
        application.add_handler(pay_debt_conv)
        
        # Запуск бота
        logger.info("Бот запускается...")
        application.run_polling(drop_pending_updates=True)
    
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")

if __name__ == '__main__':
    main()
