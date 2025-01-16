import os
import logging
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, ConversationHandler
import sqlite3

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# States
(ADDING_CLIENT_NAME, ADDING_CLIENT_PHONE, 
 SELECTING_CLIENT_FOR_RECEIPT, UPLOADING_RECEIPT, ADDING_RECEIPT_AMOUNT, ADDING_DEBT_DAYS,
 SELECTING_CLIENT_FOR_VIEW,
 SELECTING_CLIENT_FOR_DELETE, SELECTING_RECEIPT_FOR_DELETE,
 SELECTING_CLIENT_FOR_PAYMENT, ADDING_PAYMENT_AMOUNT) = range(11)

# Keyboard for main menu
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("👤 Добавить клиента"), KeyboardButton("📄 Добавить чек")],
        [KeyboardButton("👁 Просмотр чеков"), KeyboardButton("⏰ Просроченные долги")],
        [KeyboardButton("🗑 Удаление чеков"), KeyboardButton("💰 Оплата долгов")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Database connection
def get_connection():
    try:
        return sqlite3.connect('debt_bot.db')
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise

def init_db():
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Create clients table
        cur.execute('''CREATE TABLE IF NOT EXISTS clients
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     name TEXT NOT NULL,
                     phone TEXT NOT NULL)''')
        
        # Create receipts table
        cur.execute('''CREATE TABLE IF NOT EXISTS receipts
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     client_id INTEGER,
                     photo_id TEXT,
                     amount REAL,
                     debt_days INTEGER,
                     date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                     FOREIGN KEY (client_id) REFERENCES clients (id))''')
        
        # Create payments table
        cur.execute('''CREATE TABLE IF NOT EXISTS payments
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     client_id INTEGER,
                     amount REAL,
                     date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                     FOREIGN KEY (client_id) REFERENCES clients (id))''')
        
        conn.commit()
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise
    finally:
        cur.close()
        conn.close()

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    try:
        user_name = update.message.from_user.first_name
        welcome_message = (
            f"👋 Здравствуйте, {user_name}!\n\n"
            "Это бот для управления долгами клиентов.\n"
            "Выберите действие из меню ниже:"
        )
        await update.message.reply_text(
            welcome_message,
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("Произошла ошибка при запуске бота. Попробуйте позже.")
# Client management
async def add_client_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the process of adding a new client."""
    try:
        await update.message.reply_text(
            "Введите имя клиента:",
            reply_markup=ReplyKeyboardRemove()
        )
        return ADDING_CLIENT_NAME
    except Exception as e:
        logger.error(f"Error in add_client_start: {e}")
        await update.message.reply_text(
            "Произошла ошибка. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

async def add_client_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process client name and ask for phone number."""
    try:
        name = update.message.text
        if len(name.strip()) < 2:
            await update.message.reply_text(
                "Имя должно содержать минимум 2 символа. Попробуйте еще раз:"
            )
            return ADDING_CLIENT_NAME
            
        context.user_data['client_name'] = name
        await update.message.reply_text(
            "Введите номер телефона клиента:"
        )
        return ADDING_CLIENT_PHONE
    except Exception as e:
        logger.error(f"Error in add_client_name: {e}")
        await update.message.reply_text(
            "Произошла ошибка. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

async def add_client_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process client phone number and save client to database."""
    try:
        phone = update.message.text
        name = context.user_data['client_name']
        
        # Simple phone validation
        phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        if not phone.replace('+', '').isdigit():
            await update.message.reply_text(
                "Некорректный номер телефона. Попробуйте еще раз:"
            )
            return ADDING_CLIENT_PHONE
        
        conn = get_connection()
        cur = conn.cursor()
        
        # Check if phone already exists
        cur.execute("SELECT name FROM clients WHERE phone = ?", (phone,))
        existing_client = cur.fetchone()
        if existing_client:
            await update.message.reply_text(
                f"Этот номер телефона уже зарегистрирован на клиента {existing_client[0]}.",
                reply_markup=get_main_keyboard()
            )
            return ConversationHandler.END
        
        # Add new client
        cur.execute("INSERT INTO clients (name, phone) VALUES (?, ?)", (name, phone))
        conn.commit()
        cur.close()
        conn.close()
        
        await update.message.reply_text(
            f"✅ Клиент {name} успешно добавлен!",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in add_client_phone: {e}")
        await update.message.reply_text(
            "Произошла ошибка при добавлении клиента. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

# Receipt management
async def add_receipt_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the process of adding a new receipt."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name, phone FROM clients ORDER BY name")
        clients = cur.fetchall()
        cur.close()
        conn.close()
        
        if not clients:
            await update.message.reply_text(
                "❌ Сначала добавьте хотя бы одного клиента!",
                reply_markup=get_main_keyboard()
            )
            return ConversationHandler.END
        
        keyboard = [[InlineKeyboardButton(f"{name} ({phone})", callback_data=f'client_{id}')] 
                   for id, name, phone in clients]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Выберите клиента:",
            reply_markup=reply_markup
        )
        return SELECTING_CLIENT_FOR_RECEIPT
        
    except Exception as e:
        logger.error(f"Error in add_receipt_start: {e}")
        await update.message.reply_text(
            "Произошла ошибка. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
async def select_client_for_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client selection for receipt."""
    try:
        query = update.callback_query
        await query.answer()
        
        client_id = int(query.data.split('_')[1])
        context.user_data['selected_client_id'] = client_id
        
        await query.edit_message_text("📸 Отправьте фото чека:")
        return UPLOADING_RECEIPT
    except Exception as e:
        logger.error(f"Error in select_client_for_receipt: {e}")
        await query.edit_message_text(
            "Произошла ошибка. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

async def handle_receipt_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process receipt photo and ask for amount."""
    try:
        photo = update.message.photo[-1]
        context.user_data['receipt_photo_id'] = photo.file_id
        
        await update.message.reply_text(
            "💰 Введите сумму чека (например: 1000.50):"
        )
        return ADDING_RECEIPT_AMOUNT
    except Exception as e:
        logger.error(f"Error in handle_receipt_photo: {e}")
        await update.message.reply_text(
            "Произошла ошибка при обработке фото. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

async def add_receipt_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process receipt amount and ask for debt days."""
    try:
        text = update.message.text.replace(',', '.')
        amount = float(text)
        if amount <= 0:
            await update.message.reply_text(
                "❌ Сумма должна быть больше нуля. Попробуйте еще раз:"
            )
            return ADDING_RECEIPT_AMOUNT
            
        context.user_data['receipt_amount'] = amount
        await update.message.reply_text(
            "📅 Введите количество дней для оплаты долга:"
        )
        return ADDING_DEBT_DAYS
    except ValueError:
        await update.message.reply_text(
            "❌ Некорректная сумма. Введите число (например: 1000.50):"
        )
        return ADDING_RECEIPT_AMOUNT
    except Exception as e:
        logger.error(f"Error in add_receipt_amount: {e}")
        await update.message.reply_text(
            "Произошла ошибка. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

async def add_receipt_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process debt days and save receipt to database."""
    try:
        days = int(update.message.text)
        if days <= 0:
            await update.message.reply_text(
                "❌ Количество дней должно быть больше нуля. Попробуйте еще раз:"
            )
            return ADDING_DEBT_DAYS
            
        client_id = context.user_data['selected_client_id']
        photo_id = context.user_data['receipt_photo_id']
        amount = context.user_data['receipt_amount']
        
        conn = get_connection()
        cur = conn.cursor()
        
        # Add receipt
        cur.execute("""
            INSERT INTO receipts (client_id, photo_id, amount, debt_days, date_added)
            VALUES (?, ?, ?, ?, ?)
        """, (client_id, photo_id, amount, days, datetime.now()))
        
        # Get client name
        cur.execute("SELECT name FROM clients WHERE id = ?", (client_id,))
        client_name = cur.fetchone()[0]
        
        conn.commit()
        cur.close()
        conn.close()
        
        # Calculate due date
        due_date = datetime.now() + timedelta(days=days)
        
        success_message = (
            f"✅ Чек успешно добавлен!\n\n"
            f"👤 Клиент: {client_name}\n"
            f"💰 Сумма: {amount:.2f} руб.\n"
            f"📅 Срок оплаты: {due_date.strftime('%d.%m.%Y')}"
        )
        
        await update.message.reply_text(
            success_message,
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text(
            "❌ Некорректное количество дней. Введите целое число:"
        )
        return ADDING_DEBT_DAYS
    except Exception as e:
        logger.error(f"Error in add_receipt_days: {e}")
        await update.message.reply_text(
            "Произошла ошибка при сохранении чека. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
        # View receipts
async def view_receipts_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the process of viewing receipts."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Get clients with active receipts
        cur.execute("""
            SELECT DISTINCT c.id, c.name, c.phone,
                   COUNT(r.id) as receipt_count,
                   SUM(r.amount) - COALESCE((
                       SELECT SUM(amount) 
                       FROM payments p 
                       WHERE p.client_id = c.id
                   ), 0) as total_debt
            FROM clients c
            LEFT JOIN receipts r ON c.id = r.client_id
            GROUP BY c.id, c.name, c.phone
            HAVING receipt_count > 0
            ORDER BY c.name
        """)
        clients = cur.fetchall()
        cur.close()
        conn.close()
        
        if not clients:
            await update.message.reply_text(
                "📭 Нет чеков для просмотра.",
                reply_markup=get_main_keyboard()
            )
            return ConversationHandler.END
        
        keyboard = []
        for id, name, phone, receipt_count, total_debt in clients:
            text = f"{name} ({phone}) - {receipt_count} чеков"
            if total_debt > 0:
                text += f", долг: {total_debt:.2f} руб."
            keyboard.append([InlineKeyboardButton(text, callback_data=f'view_{id}')])
            
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "👁 Выберите клиента для просмотра чеков:",
            reply_markup=reply_markup
        )
        return SELECTING_CLIENT_FOR_VIEW
        
    except Exception as e:
        logger.error(f"Error in view_receipts_start: {e}")
        await update.message.reply_text(
            "Произошла ошибка. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

async def show_client_receipts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all receipts for selected client."""
    try:
        query = update.callback_query
        await query.answer()
        
        client_id = int(query.data.split('_')[1])
        
        conn = get_connection()
        cur = conn.cursor()
        
        # Get client info
        cur.execute("""
            SELECT c.name, c.phone,
                   SUM(r.amount) as total_amount,
                   COALESCE((
                       SELECT SUM(amount)
                       FROM payments p
                       WHERE p.client_id = c.id
                   ), 0) as total_paid
            FROM clients c
            LEFT JOIN receipts r ON c.id = r.client_id
            WHERE c.id = ?
            GROUP BY c.id, c.name, c.phone
        """, (client_id,))
        client_info = cur.fetchone()
        name, phone, total_amount, total_paid = client_info
        
        # Get receipts
        cur.execute("""
            SELECT photo_id, amount, date_added, debt_days
            FROM receipts 
            WHERE client_id = ?
            ORDER BY date_added DESC
        """, (client_id,))
        receipts = cur.fetchall()
        
        cur.close()
        conn.close()
        
        # Send client summary
        remaining_debt = total_amount - total_paid
        summary = (
            f"👤 Клиент: {name}\n"
            f"📱 Телефон: {phone}\n"
            f"💰 Общая сумма долга: {total_amount:.2f} руб.\n"
            f"💵 Оплачено: {total_paid:.2f} руб.\n"
            f"📊 Остаток: {remaining_debt:.2f} руб.\n\n"
            f"📄 Чеки клиента:"
        )
        await query.edit_message_text(summary)
        
        # Send receipts
        for photo_id, amount, date_added, debt_days in receipts:
            due_date = datetime.strptime(date_added, '%Y-%m-%d %H:%M:%S.%f') + timedelta(days=debt_days)
            is_overdue = datetime.now() > due_date
            
            caption = (
                f"💰 Сумма: {amount:.2f} руб.\n"
                f"📅 Дата добавления: {date_added.split('.')[0]}\n"
                f"⏳ Срок оплаты: {due_date.strftime('%d.%m.%Y')}\n"
                f"❗️ Статус: {'Просрочен' if is_overdue else 'Активен'}"
            )
            
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=photo_id,
                caption=caption
            )
        
        # Send final message with main menu
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Вернуться в главное меню:",
            reply_markup=get_main_keyboard()
        )
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in show_client_receipts: {e}")
        await query.edit_message_text(
            "Произошла ошибка при загрузке чеков. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
        # Overdue debts
async def show_overdue_debts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all overdue debts."""
    try:
        current_time = datetime.now()
        
        conn = get_connection()
        cur = conn.cursor()
        
        # Get overdue debts with detailed information
        cur.execute("""
            SELECT 
                c.name, c.phone,
                r.amount, r.date_added, r.debt_days,
                COALESCE((
                    SELECT SUM(amount) 
                    FROM payments p 
                    WHERE p.client_id = c.id
                ), 0) as paid_amount
            FROM receipts r
            JOIN clients c ON r.client_id = c.id
            WHERE datetime(r.date_added, '+' || r.debt_days || ' days') < ?
            ORDER BY c.name, r.date_added
        """, (current_time,))
        
        overdue = cur.fetchall()
        cur.close()
        conn.close()
        
        if not overdue:
            await update.message.reply_text(
                "✅ Нет просроченных долгов.",
                reply_markup=get_main_keyboard()
            )
            return
        
        # Group by client
        client_debts = {}
        for name, phone, amount, date_added, days, paid_amount in overdue:
            if name not in client_debts:
                client_debts[name] = {
                    'phone': phone,
                    'total_debt': 0,
                    'paid': paid_amount,
                    'debts': []
                }
            
            due_date = datetime.strptime(date_added, '%Y-%m-%d %H:%M:%S.%f') + timedelta(days=days)
            days_overdue = (current_time - due_date).days
            
            client_debts[name]['total_debt'] += amount
            client_debts[name]['debts'].append({
                'amount': amount,
                'due_date': due_date,
                'days_overdue': days_overdue
            })
        
        # Format message
        message = "⚠️ Просроченные долги:\n\n"
        for client_name, data in client_debts.items():
            remaining_debt = data['total_debt'] - data['paid']
            if remaining_debt <= 0:
                continue
                
            message += f"👤 Клиент: {client_name}\n"
            message += f"📱 Телефон: {data['phone']}\n"
            message += f"💰 Общий долг: {data['total_debt']:.2f} руб.\n"
            message += f"💵 Оплачено: {data['paid']:.2f} руб.\n"
            message += f"📊 Остаток: {remaining_debt:.2f} руб.\n\n"
            message += "Просроченные чеки:\n"
            
            for debt in data['debts']:
                message += (
                    f"- {debt['amount']:.2f} руб. "
                    f"(просрочка {debt['days_overdue']} дней)\n"
                )
            message += "\n"
        
        # Split message if it's too long
        if len(message) > 4096:
            for x in range(0, len(message), 4096):
                await update.message.reply_text(message[x:x+4096])
        else:
            await update.message.reply_text(message)
            
        await update.message.reply_text(
            "Вернуться в главное меню:",
            reply_markup=get_main_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error in show_overdue_debts: {e}")
        await update.message.reply_text(
            "Произошла ошибка при получении данных о долгах. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )

# Delete receipt
async def delete_receipt_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the process of deleting a receipt."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Get clients with receipts
        cur.execute("""
            SELECT DISTINCT c.id, c.name, c.phone,
                   COUNT(r.id) as receipt_count
            FROM clients c
            JOIN receipts r ON c.id = r.client_id
            GROUP BY c.id, c.name, c.phone
            HAVING receipt_count > 0
            ORDER BY c.name
        """)
        clients = cur.fetchall()
        cur.close()
        conn.close()
        
        if not clients:
            await update.message.reply_text(
                "📭 Нет чеков для удаления.",
                reply_markup=get_main_keyboard()
            )
            return ConversationHandler.END
        
        keyboard = []
        for id, name, phone, receipt_count in clients:
            text = f"{name} ({phone}) - {receipt_count} чеков"
            keyboard.append([InlineKeyboardButton(text, callback_data=f'del_client_{id}')])
            
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🗑 Выберите клиента для удаления чека:",
            reply_markup=reply_markup
        )
        return SELECTING_CLIENT_FOR_DELETE
        
    except Exception as e:
        logger.error(f"Error in delete_receipt_start: {e}")
        await update.message.reply_text(
            "Произошла ошибка. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
        async def show_receipts_for_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show receipts available for deletion."""
    try:
        query = update.callback_query
        await query.answer()
        
        client_id = int(query.data.split('_')[2])
        context.user_data['selected_client_id'] = client_id
        
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT r.id, r.photo_id, r.amount, r.date_added, c.name
            FROM receipts r
            JOIN clients c ON r.client_id = c.id
            WHERE r.client_id = ?
            ORDER BY r.date_added DESC
        """, (client_id,))
        receipts = cur.fetchall()
        cur.close()
        conn.close()
        
        await query.edit_message_text(f"Чеки клиента:")
        
        for receipt_id, photo_id, amount, date_added, client_name in receipts:
            keyboard = [[InlineKeyboardButton("❌ Удалить чек", 
                                          callback_data=f'delete_receipt_{receipt_id}')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            caption = (
                f"👤 Клиент: {client_name}\n"
                f"💰 Сумма: {amount:.2f} руб.\n"
                f"📅 Дата: {date_added}"
            )
            
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=photo_id,
                caption=caption,
                reply_markup=reply_markup
            )
        
        return SELECTING_RECEIPT_FOR_DELETE
        
    except Exception as e:
        logger.error(f"Error in show_receipts_for_delete: {e}")
        await query.edit_message_text(
            "Произошла ошибка. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

async def delete_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete selected receipt."""
    try:
        query = update.callback_query
        await query.answer()
        
        receipt_id = int(query.data.split('_')[2])
        
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM receipts WHERE id = ?", (receipt_id,))
        conn.commit()
        cur.close()
        conn.close()
        
        await query.edit_message_text(
            "✅ Чек успешно удален!",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in delete_receipt: {e}")
        await query.edit_message_text(
            "Произошла ошибка при удалении чека. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current operation."""
    await update.message.reply_text(
        'Операция отменена.',
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END

def main():
    """Start the bot."""
    try:
        # Initialize database
        init_db()
        
        # Get token
        token = os.getenv('BOT_TOKEN')
        if not token:
            raise ValueError("No token provided")
        
        # Initialize bot
        application = Application.builder().token(token).build()
        
        # Add conversation handlers
        add_client_conv = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex('^👤 Добавить клиента$'), add_client_start)],
            states={
                ADDING_CLIENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_name)],
                ADDING_CLIENT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_phone)]
            },
            fallbacks=[CommandHandler('cancel', cancel)]
        )
        
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
        
        view_receipts_conv = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex('^👁 Просмотр чеков$'), view_receipts_start)],
            states={
                SELECTING_CLIENT_FOR_VIEW: [CallbackQueryHandler(show_client_receipts, pattern='^view_')]
            },
            fallbacks=[CommandHandler('cancel', cancel)]
        )
        
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
        
        # Add handlers
        application.add_handler(CommandHandler('start', start))
        application.add_handler(add_client_conv)
        application.add_handler(add_receipt_conv)
        application.add_handler(view_receipts_conv)
        application.add_handler(MessageHandler(
            filters.Regex('^⏰ Просроченные долги$'), 
            show_overdue_debts
        ))
        application.add_handler(delete_receipt_conv)
        
        # Start polling
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise

if __name__ == '__main__':
    main()
