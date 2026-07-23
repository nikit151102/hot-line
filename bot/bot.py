import os
import asyncio
import logging
import re
import requests
from typing import Dict, Optional, Any, List
from enum import Enum
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Импорты maxapi
from maxapi import Bot, Dispatcher, F
from maxapi.types import MessageCreated, BotStarted, Command, MessageCallback, CallbackButton, ButtonsPayload, Attachment
from maxapi.enums.intent import Intent


# ========== КОНФИГУРАЦИЯ ==========
@dataclass
class HotlineBotConfig:
    name: str
    token: str
    default_channel_id: str  # Запасной ID канала, если в ссылке его нет


# ========== СОСТОЯНИЯ ПОЛЬЗОВАТЕЛЯ ==========
class UserState(Enum):
    IDLE = "idle"
    AWAITING_REQUEST_TYPE = "awaiting_request_type"  # Ждем выбор типа обращения
    AWAITING_MESSAGE = "awaiting_message"            # Ждем текст обращения
    COMPLETED = "completed"                          # Обращение отправлено


# ========== КЛАСС БОТА ГОРЯЧЕЙ ЛИНИИ ==========
class HotlineBot:
    def __init__(self, config: HotlineBotConfig):
        self.config = config
        self.bot = Bot(token=config.token)
        self.dp = Dispatcher()
        
        # Хранилища данных
        self.user_states: Dict[int, UserState] = {}
        self.user_data: Dict[int, Dict[str, Any]] = {}
        
        # Кэш типов обращений
        self.request_types: List[Dict[str, str]] = []
        
        self._setup_handlers()
    
    def get_state(self, user_id: int) -> UserState:
        return self.user_states.get(user_id, UserState.IDLE)
    
    def set_state(self, user_id: int, state: UserState):
        self.user_states[user_id] = state
    
    def get_user_data(self, user_id: int) -> Dict:
        if user_id not in self.user_data:
            self.user_data[user_id] = {
                "message_content": None,
                "channel_id": self.config.default_channel_id,
                "request_type_id": None,
                "completed": False
            }
        return self.user_data[user_id]

    def _extract_channel_id(self, text: str) -> Optional[str]:
        """Извлекает UUID канала из текста команды /start <uuid>"""
        parts = text.strip().split()
        if len(parts) > 1:
            potential_uuid = parts[1]
            if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', potential_uuid, re.I):
                return potential_uuid
        return None

    async def _load_request_types(self):
        """Загружает типы обращений из API или использует резервные"""
        api_url = os.getenv("HOTLINE_API_URL", "http://back_tghr_department:8070").rstrip('/')
        try:
            response = requests.get(f"{api_url}/hotline/request-types/", timeout=5)
            if response.status_code == 200:
                self.request_types = response.json()
                logger.info(f"✅ Загружено {len(self.request_types)} типов обращений из API")
                return
        except Exception as e:
            logger.warning(f"Не удалось получить типы обращений из API: {e}. Используются резервные.")
        
        # Резервные типы (замените UUID на реальные из вашей БД, если API недоступен)
        self.request_types = [
            {"id": "00000000-0000-0000-0000-000000000001", "name": "Жалоба"},
            {"id": "00000000-0000-0000-0000-000000000002", "name": "Предложение"},
            {"id": "00000000-0000-0000-0000-000000000003", "name": "Вопрос"},
            {"id": "00000000-0000-0000-0000-000000000004", "name": "Благодарность"}
        ]
        logger.info("⚠️ Используются резервные типы обращений")

    async def _send_request_type_selection(self, chat_id: int, user_id: int):
        """Отправляет сообщение с кнопками выбора типа обращения"""
        if not self.request_types:
            await self._load_request_types()
            
        buttons = []
        for rt in self.request_types:
            buttons.append([
                CallbackButton(
                    text=rt["name"],
                    payload=f"type_{rt['id']}",
                    intent=Intent.DEFAULT
                )
            ])
        
        attachment = Attachment(
            type="inline_keyboard",
            payload=ButtonsPayload(buttons=buttons)
        )
        
        await self.bot.send_message(
            chat_id=chat_id,
            text="📋 Пожалуйста, выберите тип вашего обращения:",
            attachments=[attachment]
        )

    def _setup_handlers(self):
        # 1. Обработка запуска бота (в том числе по ссылке с параметром)
        @self.dp.bot_started()
        async def handle_bot_started(event: BotStarted):
            user = event.user
            user_id = user.user_id
            chat_id = event.chat_id
            name = getattr(user, 'first_name', None) or 'пользователь'
            
            start_param = getattr(event, 'payload', '') or ''
            self._init_user_session(user_id, start_param)
            
            await self.bot.send_message(
                chat_id=chat_id, 
                text=f"Здравствуйте, {name}! 👋\n\nЭто анонимная горячая линия. Мы ценим вашу конфиденциальность."
            )
            await self._send_request_type_selection(chat_id, user_id)

        # 2. Обработка команды /start вручную
        @self.dp.message_created(Command('start'))
        async def cmd_start(event: MessageCreated):
            user = event.message.sender
            user_id = user.user_id
            chat_id = event.message.recipient.chat_id
            name = getattr(user, 'first_name', None) or 'пользователь'
            text = event.message.body.text
            
            channel_id = self._extract_channel_id(text)
            self._init_user_session(user_id, channel_id)
            
            await event.message.answer(
                f"Здравствуйте, {name}! 👋\n\nЭто анонимная горячая линия. Мы ценим вашу конфиденциальность."
            )
            await self._send_request_type_selection(chat_id, user_id)

        @self.dp.message_created(Command('help'))
        async def cmd_help(event: MessageCreated):
            help_text = (
                "**Команды:**\n"
                "/start — Начать новое анонимное обращение\n"
                "/help — Справка"
            )
            await event.message.answer(help_text)

        # 3. Обработка нажатий на кнопки (Callback)
        @self.dp.message_callback(F.callback.payload)
        async def handle_callback(event: MessageCallback):
            payload = event.callback.payload
            user_id = event.callback.user.user_id
            chat_id = event.message.recipient.chat_id
            
            # Обработка выбора типа обращения
            if payload.startswith("type_"):
                await event.answer() # Подтверждаем получение нажатия
                
                request_type_id = payload.replace("type_", "")
                data = self.get_user_data(user_id)
                data["request_type_id"] = request_type_id
                
                # Находим имя типа для красивого ответа
                req_type_name = "выбранный тип"
                for rt in self.request_types:
                    if rt["id"] == request_type_id:
                        req_type_name = rt["name"]
                        break
                
                self.set_state(user_id, UserState.AWAITING_MESSAGE)
                
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ Вы выбрали: **{req_type_name}**.\n\nТеперь кратко опишите суть вашего обращения:\n(Что случилось? Какой у вас вопрос или предложение?)"
                )
                return

        # 4. Обработка текстовых сообщений
        @self.dp.message_created(F.message.body.text)
        async def handle_text(event: MessageCreated):
            text = event.message.body.text.strip()
            
            if text.startswith('/'):
                return
            
            user_id = event.message.sender.user_id
            chat_id = event.message.recipient.chat_id
            state = self.get_state(user_id)
            data = self.get_user_data(user_id)
            
            # Если обращение уже отправлено
            if state == UserState.COMPLETED:
                await event.message.answer(
                    "Ваше обращение уже принято. Спасибо!\n"
                    "Если у вас есть новое обращение, нажмите /start"
                )
                return

            # Если пользователь пишет текст, когда мы ждем выбор типа
            if state == UserState.AWAITING_REQUEST_TYPE:
                await event.message.answer(
                    "Пожалуйста, выберите тип обращения, нажав на одну из кнопок ниже 👇"
                )
                return

            # Ожидаем текст обращения
            if state == UserState.AWAITING_MESSAGE:
                if len(text) < 5:
                    await event.message.answer(
                        "⚠️ Сообщение слишком короткое. Пожалуйста, опишите проблему подробнее."
                    )
                    return
                
                data["message_content"] = text
                self.set_state(user_id, UserState.COMPLETED)
                
                # Отправляем данные в API
                success = await self._send_to_api(data)
                
                if success:
                    await event.message.answer(
                        "✅ **Ваше анонимное обращение успешно принято!**\n\n"
                        "Мы уже передали его специалисту. Спасибо, что помогаете нам становиться лучше! 🙏"
                    )
                else:
                    await event.message.answer(
                        "⚠️ Произошла техническая ошибка при отправке.\n"
                        "Пожалуйста, попробуйте еще раз позже."
                    )
                return

    def _init_user_session(self, user_id: int, start_param: str):
        """Инициализирует или сбрасывает сессию пользователя"""
        self.set_state(user_id, UserState.AWAITING_REQUEST_TYPE)
        data = self.get_user_data(user_id)
        data["message_content"] = None
        data["request_type_id"] = None
        data["completed"] = False
        
        if start_param and re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', start_param, re.I):
            data["channel_id"] = start_param
            logger.info(f"Пользователь {user_id} начал сессию с каналом: {start_param}")
        else:
            logger.info(f"Пользователь {user_id} начал сессию с каналом по умолчанию: {data['channel_id']}")

    async def _send_to_api(self, data: Dict) -> bool:
        """Отправляет данные обращения в наш FastAPI backend"""
        api_url = os.getenv("HOTLINE_API_URL", "http://back_tghr_department:8070/hotline/journal/")
        
        payload = {
            "channel_id": data["channel_id"],
            "request_type_id": data["request_type_id"],
            "message_content": data["message_content"],
            "acceptance_info": "Анонимное обращение из Telegram-бота",
            "administrator": "Telegram Bot"
        }
        
        logger.info(f"Отправка анонимного обращения в API: {payload}")
        
        try:
            response = requests.post(api_url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("✅ Обращение успешно сохранено в базе данных!")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Ошибка при отправке в API: {e}")
            return False

    async def run(self):
        """Запуск бота"""
        logger.info(f"🤖 [{self.config.name}] Бот горячей линии запускается...")
        
        # Загружаем типы обращений при старте
        await self._load_request_types()
        
        try:
            bot_info = await self.bot.get_me()
            logger.info(f"[{self.config.name}] Бот успешно подключен: @{bot_info.username}")
        except Exception as e:
            logger.error(f"[{self.config.name}] Ошибка подключения: {e}")
            return
        
        try:
            await self.bot.delete_webhook()
            logger.info(f"[{self.config.name}] Webhook удалён, переходим в polling")
        except Exception as e:
            logger.warning(f"[{self.config.name}] Ошибка удаления webhook: {e}")
        
        await self.dp.start_polling(self.bot)


# ========== СОЗДАНИЕ КОНФИГУРАЦИЙ ==========
def create_bot_configs() -> list:
    """Создает конфигурации для ботов"""
    return [
        HotlineBotConfig(
            name="hotline_anonymous_bot",
            token=os.getenv("MAX_BOT_TOKEN"),
            default_channel_id="00000000-0000-0000-0000-000000000000" # Замените на реальный UUID канала из БД
        )
    ]


# ========== ГЛАВНАЯ ФУНКЦИЯ ==========
async def main():
    logger.info("🚀 Запуск системы ботов горячей линии...")
    
    configs = create_bot_configs()
    bots = [HotlineBot(config) for config in configs]
    
    logger.info(f"✅ Создано {len(bots)} ботов")
    
    tasks = [bot.run() for bot in bots]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Боты остановлены пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")