import sqlite3
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters
import warnings
import os

# Подавление предупреждений о совместимости
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Конфигурация ---
BOT_TOKEN = "8188336261:AAEFx--KbsYpytvRE4AE0nELkIVrSK9uhbE"  # Замените на ваш токен бота
ADMIN_USER_IDS = [6772666050, 7610385492] # Замените на ваш Telegram User ID

# --- Управление базой данных ---
class ProfitBotDB:
    def __init__(self, db_path="profit_bot.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Инициализация базы данных с необходимыми таблицами и данными по умолчанию."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Таблица настроек для хранения процентов
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS rates (
                        user_name TEXT PRIMARY KEY,
                        rate REAL
                    )
                ''')

                # Таблица балансов для хранения общей и дневной прибыли
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS balances (
                        user_name TEXT PRIMARY KEY,
                        total_profit REAL DEFAULT 0,
                        daily_profit REAL DEFAULT 0
                    )
                ''')

                # Инициализация пользователей с процентами по умолчанию и нулевым балансом
                users = {
                    'butch': 30.0,
                    'jules': 20.0,
                    'vincent': 20.0
                }
                
                for user, rate in users.items():
                    cursor.execute('''
                        INSERT OR IGNORE INTO rates (user_name, rate) VALUES (?, ?)
                    ''', (user, rate))
                    cursor.execute('''
                        INSERT OR IGNORE INTO balances (user_name, total_profit, daily_profit) VALUES (?, ?, ?)
                    ''', (user, 0.0, 0.0))
                
                # Инициализация резерва
                cursor.execute('''
                    INSERT OR IGNORE INTO balances (user_name, total_profit, daily_profit) VALUES (?, ?, ?)
                ''', ('reserve', 0.0, 0.0))

                conn.commit()
                logger.info("База данных успешно инициализирована.")
        except Exception as e:
            logger.error(f"Ошибка при инициализации базы данных: {e}")
            raise

    def get_rates(self):
        """Получить все проценты пользователей из базы данных."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_name, rate FROM rates')
            return dict(cursor.fetchall())

    def get_balances(self):
        """Получить все балансы пользователей из базы данных."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_name, total_profit, daily_profit FROM balances')
            return {row[0]: {'total': row[1], 'daily': row[2]} for row in cursor.fetchall()}

    def update_balance(self, user_name, amount):
        """Добавить сумму к общему и дневному балансу пользователя."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE balances
                SET total_profit = total_profit + ?, daily_profit = daily_profit + ?
                WHERE user_name = ?
            ''', (amount, amount, user_name))
            conn.commit()

    def set_rate(self, user_name, rate):
        """Установить процент для пользователя."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO rates (user_name, rate) VALUES (?, ?)
            ''', (user_name, rate))
            conn.commit()

    def reset_daily_profits(self):
        """Обнулить всю дневную прибыль."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE balances SET daily_profit = 0')
            conn.commit()

# --- Ядро бота ---
try:
    db = ProfitBotDB()
except Exception as e:
    logger.error(f"Не удалось создать экземпляр бота: {e}")
    exit(1)

def is_admin(user_id):
    """Проверка, является ли пользователь администратором."""
    return user_id in ADMIN_USER_IDS

# --- Команды ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start."""
    await update.message.reply_text("Привет! Я бот для управления прибылью. Используйте /help, чтобы увидеть доступные команды.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Предоставляет список всех доступных команд."""
    help_text = """
📊 **Команды Бота-Финансиста**

*Общие команды:*
- `/add [сумма]` - Распределяет указанную сумму между участниками согласно их процентам.
- `/stats` - Показывает текущие балансы и дневные поступления для всех участников.
- `/morning` - Показывает статистику за прошедший день и обнуляет дневные счетчики.
- `/finish` - Показывает итоговую статистику за день и обнуляет дневные поступления.

*Команды администратора:*
- `/set_rate [имя] [процент]` - Устанавливает процент для конкретного участника (напр., `/set_rate butch 35`).
"""
    await update.message.reply_text(help_text)

async def set_rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Устанавливает процент распределения для конкретного пользователя."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Доступ запрещен. Эта команда только для администраторов.")
        return

    try:
        if len(context.args) != 2:
            await update.message.reply_text("❌ Использование: /set_rate [имя] [процент]")
            return

        user_name = context.args[0].lower()
        rate = float(context.args[1])
        
        if rate < 0 or rate > 100:
            await update.message.reply_text("❌ Процент должен быть от 0 до 100.")
            return

        valid_users = ['butch', 'jules', 'vincent']
        if user_name not in valid_users:
            await update.message.reply_text(f"❌ Неверное имя пользователя. Допустимые имена: {', '.join(valid_users)}")
            return

        db.set_rate(user_name, rate)
        
        rates = db.get_rates()
        total_rate = sum(rates.values())
        
        if total_rate > 100:
            await update.message.reply_text(f"⚠️ Внимание: Суммарный процент превышает 100% ({total_rate:.1f}%). Пожалуйста, скорректируйте другие проценты.")
        elif total_rate < 100:
            reserve_rate = 100 - total_rate
            await update.message.reply_text(f"✅ Процент для {user_name} установлен на {rate:.1f}%. Процент резерва теперь {reserve_rate:.1f}%.")
        else:
            await update.message.reply_text(f"✅ Процент для {user_name} установлен на {rate:.1f}%. Суммарный процент ровно 100%.")

    except ValueError:
        await update.message.reply_text("❌ Неверный формат числа.")
    except Exception as e:
        logger.error(f"Ошибка в команде /set_rate: {e}")
        await update.message.reply_text("❌ Произошла ошибка при установке процента.")

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Распределяет сумму между участниками согласно их процентам."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Доступ запрещен. Эта команда только для администраторов.")
        return

    try:
        if len(context.args) != 1:
            await update.message.reply_text("❌ Использование: /add [сумма]")
            return

        amount = float(context.args[0])
        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть положительной.")
            return

        rates = db.get_rates()
        total_rate = sum(rates.values())
        
        if total_rate > 100:
            await update.message.reply_text("❌ Суммарный процент превышает 100%. Пожалуйста, сначала скорректируйте проценты.")
            return

        # Расчет сумм для каждого участника
        distributions = {}
        for user_name, rate in rates.items():
            distributed_amount = amount * (rate / 100)
            distributions[user_name] = distributed_amount
            db.update_balance(user_name, distributed_amount)
        
        # Расчет и распределение в резерв
        reserve_rate = 100 - total_rate
        if reserve_rate > 0:
            reserve_amount = amount * (reserve_rate / 100)
            distributions['reserve'] = reserve_amount
            db.update_balance('reserve', reserve_amount)

        # Генерация сообщения
        message = f"💰 **{amount:.2f}$ распределено!**\n\n"
        for user_name, dist_amount in distributions.items():
            message += f"• **{user_name.capitalize()}**: +{dist_amount:.2f}$\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')

    except ValueError:
        await update.message.reply_text("❌ Неверный формат числа.")
    except Exception as e:
        logger.error(f"Ошибка в команде /add: {e}")
        await update.message.reply_text("❌ Произошла ошибка при распределении суммы.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает текущий баланс для всех участников."""
    try:
        balances = db.get_balances()
        rates = db.get_rates()
        
        message = "📊 **Текущая статистика**\n\n"
        message += "--- **Общая прибыль** ---\n"
        for user_name, balance in balances.items():
            message += f"• **{user_name.capitalize()}**: {balance['total']:.2f}$"
            if user_name != 'reserve':
                message += f" ({rates.get(user_name, 0):.1f}%)"
            message += "\n"
        
        message += "\n--- **Поступления за сегодня** ---\n"
        for user_name, balance in balances.items():
            message += f"• **{user_name.capitalize()}**: +{balance['daily']:.2f}$\n"

        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка в команде /stats: {e}")
        await update.message.reply_text("❌ Произошла ошибка при получении статистики.")

async def finish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает итоговую дневную статистику и сбрасывает дневную прибыль."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Доступ запрещен. Эта команда только для администраторов.")
        return

    try:
        # Получение балансов до сброса
        balances = db.get_balances()

        # Генерация отформатированного сообщения
        message = "✅ **Итоговая статистика за день**\n\n"
        message += f"**Дата:** {datetime.now().strftime('%d.%m.%Y')}\n\n"

        for user_name, balance in balances.items():
            message += f"• **{user_name.capitalize()}**: Общая: {balance['total']:.2f}$ | Дневная: +{balance['daily']:.2f}$\n"

        # Обнуление дневной прибыли
        db.reset_daily_profits()
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка в команде /finish: {e}")
        await update.message.reply_text("❌ Произошла ошибка при подведении итогов дня.")

async def morning_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обнуляет дневную прибыль и показывает текущую статистику (для утреннего отчета)."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Доступ запрещен. Эта команда только для администраторов.")
        return

    try:
        # Получение балансов до сброса
        balances = db.get_balances()

        message = "☀️ **Утренний отчёт**\n\n"
        message += f"**Дата:** {datetime.now().strftime('%d.%m.%Y')}\n\n"
        message += "--- **Балансы** ---\n"

        for user_name, balance in balances.items():
            message += f"• **{user_name.capitalize()}**: {balance['total']:.2f}$\n"

        message += "\n--- **Поступления за прошедший день** ---\n"
        for user_name, balance in balances.items():
            message += f"• **{user_name.capitalize()}**: +{balance['daily']:.2f}$\n"
        
        # Обнуление дневной прибыли
        db.reset_daily_profits()
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка в команде /morning: {e}")
        await update.message.reply_text("❌ Произошла ошибка при генерации утреннего отчёта.")


def main():
    """Запускает бота."""
    if BOT_TOKEN == "YOUR_BOT_TOKEN":
        print("❌ Ошибка: Не установлен токен бота!")
        print("Пожалуйста, замените 'YOUR_BOT_TOKEN' в скрипте на ваш реальный токен.")
        return
    
    if ADMIN_USER_IDS == [123456789]:
        print("⚠️ Предупреждение: Не установлен ID администратора!")
        print("Пожалуйста, замените 'YOUR_ADMIN_ID' на ваш Telegram User ID, чтобы использовать команды администратора.")
    
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("add", add_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("finish", finish_command))
        application.add_handler(CommandHandler("morning", morning_command))
        application.add_handler(CommandHandler("set_rate", set_rate_command))
        
        print("✅ Бот-Финансист запущен!")
        print("Нажмите Ctrl+C для остановки бота.")
        logger.info("Бот запущен успешно.")
        application.run_polling(drop_pending_updates=True)
    
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")
        print(f"❌ Ошибка: {e}")

if __name__ == '__main__':
    main()