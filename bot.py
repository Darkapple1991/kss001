import telebot
from telebot import types
from datetime import datetime, timedelta

# Создаем экземпляр бота
bot = telebot.TeleBot('7908445338:AAGaQ64s-eEE12VmVDHC3xyYQRwYmUG6K10')

# Словарь для хранения информации о клиентах и их чеках
clients = {}

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def start_message(message):
    # Создаем инлайн-клавиатуру с кнопками
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    add_client_button = types.InlineKeyboardButton('Добавить клиента', callback_data='add_client')
    add_check_button = types.InlineKeyboardButton('Добавить чек', callback_data='add_check')
    view_checks_button = types.InlineKeyboardButton('Просмотр чеков', callback_data='view_checks')
    overdue_debts_button = types.InlineKeyboardButton('Просроченные долги', callback_data='overdue_debts')
    delete_checks_button = types.InlineKeyboardButton('Удаление чеков', callback_data='delete_checks')
    pay_debts_button = types.InlineKeyboardButton('Оплата долгов', callback_data='pay_debts')
    keyboard.add(add_client_button, add_check_button, view_checks_button,
                 overdue_debts_button, delete_checks_button, pay_debts_button)

    bot.send_message(message.chat.id, 'Выберите действие:', reply_markup=keyboard)

# Обработчик кнопки "Добавить клиента"
@bot.callback_query_handler(func=lambda call: call.data == 'add_client')
def add_client(call):
    msg = bot.send_message(call.message.chat.id, 'Введите имя клиента:')
    bot.register_next_step_handler(msg, process_client_name)

def process_client_name(message):
    name = message.text
    msg = bot.send_message(message.chat.id, 'Введите номер телефона клиента:')
    bot.register_next_step_handler(msg, process_client_phone, name)

def process_client_phone(message, name):
    phone = message.text
    client_id = len(clients) + 1
    clients[client_id] = {'name': name, 'phone': phone, 'checks': []}
    bot.send_message(message.chat.id, f'Клиент "{name}" добавлен с номером телефона {phone}')

# Обработчик кнопки "Добавить чек"
@bot.callback_query_handler(func=lambda call: call.data == 'add_check')
def add_check(call):
    if not clients:
        bot.send_message(call.message.chat.id, 'Сначала добавьте клиента')
        return

    keyboard = types.InlineKeyboardMarkup()
    for client_id, client in clients.items():
        button = types.InlineKeyboardButton(client['name'], callback_data=f'add_check_{client_id}')
        keyboard.add(button)

    bot.send_message(call.message.chat.id, 'Выберите клиента:', reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith('add_check_'))
def process_check(call):
    client_id = int(call.data.split('_')[2])
    msg = bot.send_message(call.message.chat.id, 'Загрузите фото чека:')
    bot.register_next_step_handler(msg, process_check_photo, client_id)

def process_check_photo(message, client_id):
    if message.content_type == 'photo':
        photo_id = message.photo[-1].file_id
        msg = bot.send_message(message.chat.id, 'Введите сумму чека:')
        bot.register_next_step_handler(msg, process_check_amount, client_id, photo_id)
    else:
        bot.send_message(message.chat.id, 'Пожалуйста, загрузите фото чека')

def process_check_amount(message, client_id, photo_id):
    amount = float(message.text)
    msg = bot.send_message(message.chat.id, 'На сколько дней выдается долг?')
    bot.register_next_step_handler(msg, process_check_days, client_id, photo_id, amount)

def process_check_days(message, client_id, photo_id, amount):
    days = int(message.text)
    due_date = datetime.now() + timedelta(days=days)
    check = {'photo_id': photo_id, 'amount': amount, 'due_date': due_date}
    clients[client_id]['checks'].append(check)
    bot.send_message(message.chat.id, 'Чек успешно добавлен')

# Обработчик кнопки "Просмотр чеков"
@bot.callback_query_handler(func=lambda call: call.data == 'view_checks')
def view_checks(call):
    if not clients:
        bot.send_message(call.message.chat.id, 'Нет добавленных клиентов')
        return

    keyboard = types.InlineKeyboardMarkup()
    for client_id, client in clients.items():
        button = types.InlineKeyboardButton(client['name'], callback_data=f'view_checks_{client_id}')
        keyboard.add(button)

    bot.send_message(call.message.chat.id, 'Выберите клиента:', reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith('view_checks_'))
def process_view_checks(call):
    client_id = int(call.data.split('_')[2])
    client = clients[client_id]
    checks = client['checks']

    if not checks:
        bot.send_message(call.message.chat.id, 'У клиента нет чеков')
        return

    for check in checks:
        photo_id = check['photo_id']
        amount = check['amount']
        bot.send_photo(call.message.chat.id, photo_id, caption=f'Сумма: {amount}')

# Обработчик кнопки "Просроченные долги"
@bot.callback_query_handler(func=lambda call: call.data == 'overdue_debts')
def overdue_debts(call):
    overdue_checks = []
    for client in clients.values():
        for check in client['checks']:
            if check['due_date'] < datetime.now():
                overdue_checks.append((client['name'], check))

    if not overdue_checks:
        bot.send_message(call.message.chat.id, 'Нет просроченных долгов')
        return

    for client_name, check in overdue_checks:
        photo_id = check['photo_id']
        amount = check['amount']
        bot.send_photo(call.message.chat.id, photo_id, caption=f'Клиент: {client_name}\nСумма: {amount}')

# Обработчик кнопки "Удаление чеков"
@bot.callback_query_handler(func=lambda call: call.data == 'delete_checks')
def delete_checks(call):
    if not clients:
        bot.send_message(call.message.chat.id, 'Нет добавленных клиентов')
        return

    keyboard = types.InlineKeyboardMarkup()
    for client_id, client in clients.items():
        button = types.InlineKeyboardButton(client['name'], callback_data=f'delete_checks_{client_id}')
        keyboard.add(button)

    bot.send_message(call.message.chat.id, 'Выберите клиента:', reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_checks_'))
def process_delete_checks(call):
    client_id = int(call.data.split('_')[2])
    client = clients[client_id]
    checks = client['checks']

    if not checks:
        bot.send_message(call.message.chat.id, 'У клиента нет чеков')
        return

    keyboard = types.InlineKeyboardMarkup()
    for i, check in enumerate(checks):
        photo_id = check['photo_id']
        amount = check['amount']
        button = types.InlineKeyboardButton(f'Чек {i+1} - Сумма: {amount}', callback_data=f'delete_check_{client_id}_{i}')
        keyboard.add(button)

    bot.send_message(call.message.chat.id, 'Выберите чек для удаления:', reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_check_'))
def process_delete_check(call):
    _, client_id, check_index = call.data.split('_')
    client_id = int(client_id)
    check_index = int(check_index)
    del clients[client_id]['checks'][check_index]
    bot.send_message(call.message.chat.id, 'Чек успешно удален')

# Обработчик кнопки "Оплата долгов"
@bot.callback_query_handler(func=lambda call: call.data == 'pay_debts')
def pay_debts(call):
    if not clients:
        bot.send_message(call.message.chat.id, 'Нет добавленных клиентов')
        return

    keyboard = types.InlineKeyboardMarkup()
    for client_id, client in clients.items():
        button = types.InlineKeyboardButton(client['name'], callback_data=f'pay_debts_{client_id}')
        keyboard.add(button)

    bot.send_message(call.message.chat.id, 'Выберите клиента:', reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith('pay_debts_'))
def process_pay_debts(call):
    client_id = int(call.data.split('_')[2])
    msg = bot.send_message(call.message.chat.id, 'Введите сумму оплаты:')
    bot.register_next_step_handler(msg, process_payment_amount, client_id)

def process_payment_amount(message, client_id):
    amount = float(message.text)
    client = clients[client_id]
    checks = client['checks']

    paid_amount = 0
    paid_checks = []
    for check in checks:
        if paid_amount + check['amount'] <= amount:
            paid_amount += check['amount']
            paid_checks.append(check)
        else:
            break

    for check in paid_checks:
        checks.remove(check)

    remaining_debt = sum(check['amount'] for check in checks)
    bot.send_message(message.chat.id, f'Оплачено: {paid_amount}\nОставшийся долг: {remaining_debt}')

# Запускаем бота
bot.polling()
