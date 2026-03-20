import os
import json
import time
import logging
import threading
import concurrent.futures
from websocket import WebSocketApp
from dotenv import load_dotenv

from package_theloadunload import *
from package_cardiac import *
from package_recoveryzone import *
from package_connection import client

dotenv_path = os.path.join(os.path.dirname(__file__), 'config', '.credentials.env')
load_dotenv(dotenv_path)

# --- Logger (igual que el tuyo) ---
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
file_handler = logging.FileHandler("logs/positions.log")
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)
if logger.hasHandlers():
    logger.handlers.clear()
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# --- Estado global ---
ws = None
_stop_event = threading.Event()  # Para señalizar parada limpia

# Lock dictionary and lock for managing symbol locks
_symbol_locks = {}
_locks_lock = threading.Lock()

def get_symbol_lock(symbol):
    """Retrieve or create a lock for a specific symbol."""
    with _locks_lock:
        if symbol not in _symbol_locks:
            _symbol_locks[symbol] = threading.Lock()
        return _symbol_locks[symbol]

executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)


def process_message(message):
    try:
        if message['e'] != 'ORDER_TRADE_UPDATE':
            return
        symbol = message['o']['s']
        
        # Use a symbol-specific lock to prevent race conditions for the same token
        with get_symbol_lock(symbol):
            strategy = get_strategy(symbol)
            if strategy == "THE_LOAD_UNLOAD_GRID":
                LUGrid(symbol).attend_message(message)
            elif strategy == "CARDIAC":
                CardiacGrid(symbol).attend_message(message)
            elif strategy == "RECOVERY_ZONE":
                RecoveryZone(symbol).attend_message(message)
    except KeyError as ke:
        logging.error(f"Missing key {ke} in message: {message}")
    except Exception as e:
        logging.exception(f"Error processing message: {e}")


def keepalive_loop(listen_key, interval=30 * 60):
    """Renueva el listen key cada 30 min en un hilo separado."""
    while not _stop_event.wait(timeout=interval):  # espera `interval` segundos o hasta stop
        try:
            client.futures_stream_keepalive(listen_key)
            logging.info("Listen key renovado correctamente")
        except Exception as e:
            logging.error(f"Error renovando listen key: {e}")


def start_futures_stream():
    global ws

    # Backoff exponencial para reconexiones
    retry_delay = 5
    max_delay = 120

    while not _stop_event.is_set():
        listen_key = None
        keepalive_thread = None

        try:
            listen_key = client.futures_stream_get_listen_key()

            is_testnet = (os.getenv('TESTNET') == 'True')
            if is_testnet:
                url = f"wss://fstream.binancefuture.com/ws/{listen_key}"
                logging.info("TESTNET websocket CONNECTED!")
            else:
                url = f"wss://fstream.binance.com/ws/{listen_key}"
                logging.info("PRODUCTION websocket CONNECTED!")

            # Iniciar keepalive en hilo separado
            keepalive_thread = threading.Thread(
                target=keepalive_loop,
                args=(listen_key,),
                daemon=True
            )
            keepalive_thread.start()

            # Handlers
            def on_message(ws, message):
                try:
                    logging.debug(f"MESSAGE RECEIVED -->: {message}")
                    data = json.loads(message)
                    executor.submit(process_message, data)
                except Exception as e:
                    logging.exception(f"Error in on_message: {e}")

            def on_error(ws, error):
                logging.error(f"WebSocket error: {error}")

            def on_close(ws, code, msg):
                logging.warning(f"WebSocket cerrado: {code} - {msg}. Reconectando...")

            def on_open(ws):
                nonlocal retry_delay
                retry_delay = 5  # Reset backoff al conectar exitosamente
                logging.info("WebSocket connection established")

            ws = WebSocketApp(url,
                              on_message=on_message,
                              on_error=on_error,
                              on_close=on_close,
                              on_open=on_open)

            ws.run_forever(ping_interval=120, ping_timeout=20)

            # Si llegamos aquí, el WebSocket se cerró
            if _stop_event.is_set():
                break

            logging.warning(f"WebSocket desconectado. Reintentando en {retry_delay}s...")

        except Exception as e:
            logging.error(f"Error en stream: {e}")

        finally:
            # Limpiar listen key al desconectarse
            if listen_key:
                try:
                    client.futures_stream_close(listen_key)
                    logging.info("Listen key cerrado correctamente")
                except Exception:
                    pass
            # Detener keepalive
            _stop_event.set() if _stop_event.is_set() else None

        # Esperar antes de reconectar (backoff exponencial)
        time.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, max_delay)
        _stop_event.clear() if not _stop_event.is_set() else None


if __name__ == "__main__":
    try:
        start_futures_stream()
    except KeyboardInterrupt:
        logging.info("Deteniendo bot...")
        _stop_event.set()
        if ws:
            ws.close()