from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import MAIN_BOT_TOKEN, SUPPORTED_PAIRS
from arbitrage import ArbitrageBot
from ml_model import ArbitragePredictor
import logging
import os
import asyncio

# Створюємо папку logs, якщо вона не існує
if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(filename='logs/main_bot.log', level=logging.INFO, encoding='utf-8')

# Зберігаємо користувачів, які активували моніторинг
monitoring_users = set()

async def start(update, context):
    await update.message.reply_text("Вітаю! Використовуйте /arbitrage для пошуку можливостей або /monitor для автосповіщень.")
    logging.info(f"Команда /start від користувача {update.effective_user.id}")

async def arbitrage(update, context):
    keyboard = [
        [InlineKeyboardButton("Міжбіржовий", callback_data='inter')],
        [InlineKeyboardButton("Внутрішньобіржовий", callback_data='intra')],
        [InlineKeyboardButton("P2P", callback_data='p2p')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Виберіть тип арбітражу:", reply_markup=reply_markup)
    logging.info(f"Команда /arbitrage від користувача {update.effective_user.id}")

async def monitor(update, context):
    user_id = update.effective_user.id
    if user_id not in monitoring_users:
        monitoring_users.add(user_id)
        await update.message.reply_text("Автоматичний моніторинг увімкнено! Сповіщення надсилатимуться кожні 5 хвилин.")
        logging.info(f"Моніторинг увімкнено для користувача {user_id}")
    else:
        monitoring_users.remove(user_id)
        await update.message.reply_text("Автоматичний моніторинг вимкнено.")
        logging.info(f"Моніторинг вимкнено для користувача {user_id}")

async def handle_arbitrage_type(update, context):
    query = update.callback_query
    arbitrage_type = query.data
    user_id = query.from_user.id
    bot = ArbitrageBot()
    predictor = ArbitragePredictor()
    response = f"📊 {arbitrage_type.upper()} арбітражні можливості\n\n"
    try:
        if arbitrage_type == 'inter':
            for symbol in SUPPORTED_PAIRS:
                prices = await bot.fetch_prices(symbol)
                inter_ops = await bot.calculate_inter_exchange_arbitrage(symbol, amount=1)
                for op in inter_ops[:3]:
                    # Перевіряємо AI-прогноз
                    buy_data = prices.get(op['buy_exchange'], {})
                    sell_data = prices.get(op['sell_exchange'], {})
                    buy_pred = predictor.is_profitable(op['buy_exchange'], symbol, buy_data) if buy_data else False
                    sell_pred = predictor.is_profitable(op['sell_exchange'], symbol, sell_data) if sell_data else False
                    if buy_pred or sell_pred:
                        response += (f"Купити на {op['buy_exchange']} за {op['buy_price']:.2f} USDT\n"
                                     f"Продати на {op['sell_exchange']} за {op['sell_price']:.2f} USDT\n"
                                     f"Прибуток: {op['profit']:.2f} USDT ({op['profit_percent']:.2f}%) [AI рекомендує]\n\n")
                    else:
                        response += (f"Купити на {op['buy_exchange']} за {op['buy_price']:.2f} USDT\n"
                                     f"Продати на {op['sell_exchange']} за {op['sell_price']:.2f} USDT\n"
                                     f"Прибуток: {op['profit']:.2f} USDT ({op['profit_percent']:.2f}%)\n\n")

        elif arbitrage_type == 'intra':
            for ex in ['binance', 'bybit', 'okx', 'kraken', 'kucoin']:
                intra_ops = await bot.calculate_intra_exchange_arbitrage(ex, [symbol, 'ETH/USDT', 'BTC/ETH'])
                if intra_ops:
                    response += f"🔄 Внутрішньобіржовий арбітраж ({ex.capitalize()}):\n"
                    for op in intra_ops:
                        response += (f"Шлях: {op['path']}\n"
                                     f"Прибуток: {op['profit']:.2f} BTC ({op['profit_percent']:.2f}%)\n\n")

        elif arbitrage_type == 'p2p':
            p2p_ops = await bot.calculate_p2p_arbitrage(crypto='USDT', fiat='UAH', amount=10000)
            if p2p_ops:
                response += "🔄 P2P арбітраж (USDT/UAH):\n"
                for op in p2p_ops[:3]:
                    response += (f"Купити на {op['buy_exchange']} за {op['buy_price']:.2f} UAH\n"
                                 f"Продати на {op['sell_exchange']} за {op['sell_price']:.2f} UAH\n"
                                 f"Прибуток: {op['profit']:.2f} UAH ({op['profit_percent']:.2f}%)\n\n")

        if response == f"📊 {arbitrage_type.upper()} арбітражні можливості\n\n":
            response = "Наразі немає прибуткових можливостей."
        await query.message.reply_text(response)
        logging.info(f"Оброблено {arbitrage_type} арбітраж для користувача {user_id}")
    except Exception as e:
        logging.error(f"Помилка обробки {arbitrage_type}: {e}")
        await query.message.reply_text("Виникла помилка. Спробуйте пізніше.")
    finally:
        await bot.close_exchanges()

async def monitor_arbitrage(context):
    bot = ArbitrageBot()
    predictor = ArbitragePredictor()
    while True:
        response = "📊 Нові арбітражні можливості\n\n"
        try:
            for symbol in SUPPORTED_PAIRS:
                prices = await bot.fetch_prices(symbol)
                inter_ops = await bot.calculate_inter_exchange_arbitrage(symbol, amount=1)
                if inter_ops and inter_ops[0]['profit_percent'] > 1:
                    buy_data = prices.get(inter_ops[0]['buy_exchange'], {})
                    sell_data = prices.get(inter_ops[0]['sell_exchange'], {})
                    buy_pred = predictor.is_profitable(inter_ops[0]['buy_exchange'], symbol, buy_data) if buy_data else False
                    sell_pred = predictor.is_profitable(inter_ops[0]['sell_exchange'], symbol, sell_data) if sell_data else False
                    response += f"🔄 Міжбіржовий арбітраж ({symbol}):\n"
                    for op in inter_ops[:1]:
                        response += (f"Купити на {op['buy_exchange']} за {op['buy_price']:.2f} USDT\n"
                                     f"Продати на {op['sell_exchange']} за {op['sell_price']:.2f} USDT\n"
                                     f"Прибуток: {op['profit']:.2f} USDT ({op['profit_percent']:.2f}%)\n"
                                     f"[AI рекомендує]\n\n" if buy_pred or sell_pred else "\n\n")

                for ex in ['binance', 'bybit', 'okx', 'kraken', 'kucoin']:
                    intra_ops = await bot.calculate_intra_exchange_arbitrage(ex, [symbol, 'ETH/USDT', 'BTC/ETH'])
                    if intra_ops and intra_ops[0]['profit_percent'] > 1:
                        response += f"🔄 Внутрішньобіржовий арбітраж ({ex.capitalize()}):\n"
                        for op in intra_ops[:1]:
                            response += (f"Шлях: {op['path']}\n"
                                         f"Прибуток: {op['profit']:.2f} BTC ({op['profit_percent']:.2f}%)\n\n")

                p2p_ops = await bot.calculate_p2p_arbitrage(crypto='USDT', fiat='UAH', amount=10000)
                if p2p_ops and p2p_ops[0]['profit_percent'] > 1:
                    response += "🔄 P2P арбітраж (USDT/UAH):\n"
                    for op in p2p_ops[:1]:
                        response += (f"Купити на {op['buy_exchange']} за {op['buy_price']:.2f} UAH\n"
                                     f"Продати на {op['sell_exchange']} за {op['sell_price']:.2f} UAH\n"
                                     f"Прибуток: {op['profit']:.2f} UAH ({op['profit_percent']:.2f}%)\n\n")

            if response != "📊 Нові арбітражні можливості\n\n" and monitoring_users:
                for user_id in monitoring_users:
                    await context.bot.send_message(chat_id=user_id, text=response)
                    logging.info(f"Надіслано сповіщення про можливості користувачу {user_id}")
            else:
                logging.info("Немає нових прибуткових можливостей")
        except Exception as e:
            logging.error(f"Помилка моніторингу: {e}")
        finally:
            await bot.close_exchanges()
        await asyncio.sleep(300)  # Чекати 5 хвилин

def main():
    try:
        app = Application.builder().token(MAIN_BOT_TOKEN).read_timeout(30).write_timeout(30).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("arbitrage", arbitrage))
        app.add_handler(CommandHandler("monitor", monitor))
        app.add_handler(CallbackQueryHandler(handle_arbitrage_type))
        app.job_queue.run_repeating(monitor_arbitrage, interval=300, first=10)
        logging.info("Бот запущено")
        app.run_polling()
    except Exception as e:
        logging.error(f"Помилка запуску бота: {e}")

if __name__ == '__main__':
    main()