import logging
import requests
import traceback
from decouple import config

TELEGRAM_TOKEN = config('TELEGRAM_HTTP_API_TOKEN')
CHAT_ID = config('TELEGRAM_CHAT_ID')


def send_telegram_message(message: str):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    payload = {'chat_id': CHAT_ID, 'text': message}
    try:
        requests.post(url, data=payload, timeout=5)
    except Exception as e:
        logging.error("Не удалось отправить сообщение в Telegram: %s", e)


def log_critical_error(exc: Exception):
    error_text = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    send_telegram_message(f"⚠️ Критическая ошибка:\n{error_text}")
