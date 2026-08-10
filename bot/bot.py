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

from maxapi import Bot, Dispatcher, F
from maxapi.types import MessageCreated, BotStarted, Command, MessageCallback, CallbackButton, ButtonsPayload, Attachment
from maxapi.enums.intent import Intent


# ========== КОНФИГУРАЦИЯ ==========
@dataclass
class HotlineBotConfig:
    name: str
    token: str
    default_channel_id: str


# ========== СОСТОЯНИЯ ПОЛЬЗОВАТЕЛЯ ==========
class UserState(Enum):
    IDLE = "idle"
    AWAITING_REQUESTER_TYPE = "awaiting_requester_type"
    AWAITING_REQUEST_TYPE = "awaiting_request_type"
    AWAITING_MESSAGE = "awaiting_message"
    COMPLETED = "completed"


# ========== КЛАСС БОТА ГОРЯЧЕЙ ЛИНИИ ==========
class HotlineBot:
    def __init__(self, config: HotlineBotConfig):
        self.config = config
        self.bot = Bot(token=config.token)
        self.dp = Dispatcher()
        
        self.user_states: Dict[int, UserState] = {}
        self.user_data: Dict[int, Dict[str, Any]] = {}
        
        # Глобальный кэш для типов заявителей (загружается при старте, обновляется при запросах)
        self.requester_types: List[Dict[str, str]] = []
        
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
                "requester_type_id": None,
                "requester_code": None,
                "request_type_id": None,
                "allowed_request_types": [],
                "completed": False
            }
        return self.user_data[user_id]

    def _extract_channel_id(self, text: str) -> Optional[str]:
        parts = text.strip().split()
        if len(parts) > 1:
            potential_uuid = parts[1]
            if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', potential_uuid, re.I):
                return potential_uuid
        return None

    async def _load_requester_types(self) -> List[Dict[str, str]]:
        """Загружает типы заявителей из API с детальным логированием"""
        api_url = os.getenv("HOTLINE_API_URL", "http://back_tghr_department:8070").rstrip('/')
        endpoint = f"{api_url}/public/requester-types/"
        
        logger.info(f"🔍 Запрос типов заявителей: {endpoint}")
        
        try:
            response = requests.get(endpoint, timeout=5)
            logger.info(f"📡 Ответ API: статус {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ Загружено {len(data)} типов заявителей из API")
                
                # Обновляем глобальный кэш
                self.requester_types = data
                return data
            else:
                logger.error(f"❌ API вернул ошибку: {response.status_code} - {response.text}")
                
        except requests.exceptions.ConnectionError as e:
            logger.error(f"❌ Не удалось подключиться к API ({endpoint}): {e}")
        except requests.exceptions.Timeout:
            logger.error(f"❌ Таймаут при запросе к API ({endpoint})")
        except Exception as e:
            logger.error(f"❌ Ошибка при запросе к API: {e}")
        
        # Резервные данные (с NIL_UUID, чтобы API точно принял их)
        logger.warning("⚠️ Используются резервные типы заявителей")
        return [
            {"id": "00000000-0000-0000-0000-000000000000", "name": "Анонимный посетитель", "code": "anonymous"},
            {"id": "00000000-0000-0000-0000-000000000000", "name": "Клиент", "code": "client"},
        ]

    async def _load_allowed_request_types(self, requester_code: str) -> List[Dict]:
        """Загружает доступные типы обращений для конкретного заявителя"""
        api_url = os.getenv("HOTLINE_API_URL", "http://back_tghr_department:8070").rstrip('/')
        endpoint = f"{api_url}/public/request-types/allowed"
        
        logger.info(f"🔍 Запрос типов обращений для {requester_code}: {endpoint}")
        
        try:
            response = requests.get(
                endpoint, 
                params={"requester_code": requester_code}, 
                timeout=5
            )
            logger.info(f"📡 Ответ API: статус {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ Загружено {len(data)} типов обращений для {requester_code}")
                return data
            else:
                logger.error(f"❌ API вернул ошибку: {response.status_code} - {response.text}")
                
        except requests.exceptions.ConnectionError as e:
            logger.error(f"❌ Не удалось подключиться к API ({endpoint}): {e}")
        except requests.exceptions.Timeout:
            logger.error(f"❌ Таймаут при запросе к API ({endpoint})")
        except Exception as e:
            logger.error(f"❌ Ошибка при запросе к API: {e}")
        
        logger.warning("⚠️ Используются резервные типы обращений")
        return [
            {"id": "00000000-0000-0000-0000-000000000000", "name": "Жалоба"},
            {"id": "00000000-0000-0000-0000-000000000000", "name": "Предложение"},
        ]

    async def _send_requester_type_selection(self, chat_id: int, user_id: int):
        """Шаг 1: Отправляет кнопки выбора типа заявителя"""
        # Всегда запрашиваем актуальные данные из API
        requester_types = await self._load_requester_types()
        
        logger.info(f"📋 Показываем {len(requester_types)} типов заявителей пользователю {user_id}")
            
        buttons = []
        for rt in requester_types:
            logger.debug(f"  Кнопка: {rt['name']} (ID: {rt['id']}, Code: {rt['code']})")
            buttons.append([
                CallbackButton(
                    text=rt["name"],
                    payload=f"req_{rt['id']}_{rt['code']}",
                    intent=Intent.DEFAULT
                )
            ])
        
        if not buttons:
            logger.error("❌ Нет кнопок для показа!")
            await self.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Ошибка загрузки данных. Попробуйте позже или напишите /start"
            )
            return
        
        attachment = Attachment(
            type="inline_keyboard",
            payload=ButtonsPayload(buttons=buttons)
        )
        
        await self.bot.send_message(
            chat_id=chat_id,
            text="👤 Пожалуйста, выберите, кто вы (Клиент, Сотрудник, Партнер и т.д.):",
            attachments=[attachment]
        )

    async def _send_request_type_selection(self, chat_id: int, user_id: int, requester_code: str):
        """Шаг 2: Отправляет кнопки выбора типа обращения"""
        data = self.get_user_data(user_id)
        request_types = await self._load_allowed_request_types(requester_code)
        data["allowed_request_types"] = request_types
        
        logger.info(f"📋 Показываем {len(request_types)} типов обращений пользователю {user_id}")
            
        buttons = []
        for rt in request_types:
            logger.debug(f"  Кнопка: {rt['name']} (ID: {rt['id']})")
            buttons.append([
                CallbackButton(
                    text=rt["name"],
                    payload=f"type_{rt['id']}",
                    intent=Intent.DEFAULT
                )
            ])
        
        if not buttons:
            await self.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Для выбранной категории пока нет доступных типов обращений. Попробуйте выбрать другую категорию или напишите /start."
            )
            self.set_state(user_id, UserState.IDLE)
            return

        attachment = Attachment(
            type="inline_keyboard",
            payload=ButtonsPayload(buttons=buttons)
        )
        
        await self.bot.send_message(
            chat_id=chat_id,
            text="📋 Теперь выберите тип вашего обращения:",
            attachments=[attachment]
        )

    def _setup_handlers(self):
        @self.dp.bot_started()
        async def handle_bot_started(event: BotStarted):
            user = event.user
            user_id = user.user_id
            chat_id = event.chat_id
            name = getattr(user, 'first_name', None) or 'пользователь'
            
            logger.info(f"👤 Пользователь {user_id} ({name}) запустил бота")
            
            start_param = getattr(event, 'payload', '') or ''
            self._init_user_session(user_id, start_param)
            
            await self.bot.send_message(
                chat_id=chat_id, 
                text=f"Здравствуйте, {name}! 👋\n\nЭто горячая линия. Мы ценим вашу конфиденциальность."
            )
            await self._send_requester_type_selection(chat_id, user_id)

        @self.dp.message_created(Command('start'))
        async def cmd_start(event: MessageCreated):
            user = event.message.sender
            user_id = user.user_id
            chat_id = event.message.recipient.chat_id
            name = getattr(user, 'first_name', None) or 'пользователь'
            text = event.message.body.text
            
            logger.info(f"👤 Пользователь {user_id} ({name}) ввел /start")
            
            channel_id = self._extract_channel_id(text)
            self._init_user_session(user_id, channel_id)
            
            await event.message.answer(
                f"Здравствуйте, {name}! 👋\n\nЭто горячая линия. Мы ценим вашу конфиденциальность."
            )
            await self._send_requester_type_selection(chat_id, user_id)

        @self.dp.message_created(Command('help'))
        async def cmd_help(event: MessageCreated):
            help_text = (
                "**Команды:**\n"
                "/start — Начать новое обращение\n"
                "/help — Справка"
            )
            await event.message.answer(help_text)

        @self.dp.message_callback(F.callback.payload)
        async def handle_callback(event: MessageCallback):
            payload = event.callback.payload
            user_id = event.callback.user.user_id
            chat_id = event.message.recipient.chat_id
            data = self.get_user_data(user_id)
            
            logger.info(f"🔘 Пользователь {user_id} нажал кнопку: {payload}")
            
            # ШАГ 1: Обработка выбора типа заявителя
            if payload.startswith("req_"):
                await event.answer()
                
                parts = payload.split("_")
                if len(parts) >= 3:
                    requester_type_id = parts[1]
                    requester_code = parts[2]
                    
                    data["requester_type_id"] = requester_type_id
                    data["requester_code"] = requester_code
                    
                    req_name = "выбранную категорию"
                    # Берем из глобального кэша
                    for rt in self.requester_types:
                        if rt["id"] == requester_type_id:
                            req_name = rt["name"]
                            break
                    
                    logger.info(f"✅ Пользователь {user_id} выбрал категорию: {req_name} (code: {requester_code})")
                    
                    self.set_state(user_id, UserState.AWAITING_REQUEST_TYPE)
                    
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text=f"✅ Вы выбрали категорию: **{req_name}**."
                    )
                    await self._send_request_type_selection(chat_id, user_id, requester_code)
                return

            # ШАГ 2: Обработка выбора типа обращения
            if payload.startswith("type_"):
                await event.answer()
                
                request_type_id = payload.replace("type_", "")
                data["request_type_id"] = request_type_id
                
                req_type_name = "выбранный тип"
                for rt in data.get("allowed_request_types", []):
                    if rt["id"] == request_type_id:
                        req_type_name = rt["name"]
                        break
                
                logger.info(f"✅ Пользователь {user_id} выбрал тип обращения: {req_type_name}")
                
                self.set_state(user_id, UserState.AWAITING_MESSAGE)
                
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ Вы выбрали: **{req_type_name}**.\n\nТеперь кратко опишите суть вашего обращения:\n(Что случилось? Какой у вас вопрос или предложение?)"
                )
                return

        @self.dp.message_created(F.message.body.text)
        async def handle_text(event: MessageCreated):
            text = event.message.body.text.strip()
            if text.startswith('/'):
                return
            
            user_id = event.message.sender.user_id
            chat_id = event.message.recipient.chat_id
            state = self.get_state(user_id)
            data = self.get_user_data(user_id)
            
            if state == UserState.COMPLETED:
                await event.message.answer(
                    "Ваше обращение уже принято. Спасибо!\n"
                    "Если у вас есть новое обращение, нажмите /start"
                )
                return

            if state == UserState.AWAITING_REQUESTER_TYPE:
                await event.message.answer("Пожалуйста, выберите вашу категорию, нажав на одну из кнопок ниже 👇")
                await self._send_requester_type_selection(chat_id, user_id)
                return

            if state == UserState.AWAITING_REQUEST_TYPE:
                await event.message.answer("Пожалуйста, выберите тип обращения, нажав на одну из кнопок ниже 👇")
                await self._send_request_type_selection(chat_id, user_id, data.get("requester_code"))
                return

            # ШАГ 3: Ожидаем текст обращения
            if state == UserState.AWAITING_MESSAGE:
                if len(text) < 5:
                    await event.message.answer("⚠️ Сообщение слишком короткое. Пожалуйста, опишите проблему подробнее.")
                    return
                
                logger.info(f"💬 Пользователь {user_id} отправил текст обращения ({len(text)} символов)")
                
                data["message_content"] = text
                self.set_state(user_id, UserState.COMPLETED)
                
                success = await self._send_to_api(data)
                
                if success:
                    await event.message.answer(
                        "✅ **Ваше обращение успешно принято!**\n\n"
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
        self.set_state(user_id, UserState.AWAITING_REQUESTER_TYPE)
        data = self.get_user_data(user_id)
        data["message_content"] = None
        data["requester_type_id"] = None
        data["requester_code"] = None
        data["request_type_id"] = None
        data["allowed_request_types"] = []
        data["completed"] = False
        
        if start_param and re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', start_param, re.I):
            data["channel_id"] = start_param
            logger.info(f"📍 Пользователь {user_id} начал сессию с каналом: {start_param}")
        else:
            logger.info(f"📍 Пользователь {user_id} начал сессию с каналом по умолчанию: {data['channel_id']}")

    async def _send_to_api(self, data: Dict) -> bool:
        """Отправляет данные обращения в FastAPI backend"""
        api_url = os.getenv("HOTLINE_API_URL", "http://back_tghr_department:8070").rstrip('/')
        endpoint = f"{api_url}/admin/journals/"
        
        payload = {
            "channel_id": data["channel_id"],
            "requester_type_id": data["requester_type_id"],
            "request_type_id": data["request_type_id"],
            "message_content": data["message_content"],
            "acceptance_info": "Обращение из Telegram-бота",
            "administrator": "Telegram Bot"
        }
        
        logger.info(f"📤 Отправка обращения в API: {endpoint}")
        logger.debug(f"Payload: {payload}")
        
        try:
            response = requests.post(endpoint, json=payload, timeout=10)
            logger.info(f"📡 Ответ API: статус {response.status_code}")
            
            if response.status_code in [200, 201]:
                logger.info("✅ Обращение успешно сохранено в базе данных!")
                return True
            else:
                logger.error(f"❌ API вернул ошибку: {response.status_code}")
                logger.error(f"Ответ: {response.text}")
                return False
                
        except requests.exceptions.ConnectionError as e:
            logger.error(f"❌ Не удалось подключиться к API ({endpoint}): {e}")
            return False
        except requests.exceptions.Timeout:
            logger.error(f"❌ Таймаут при запросе к API ({endpoint})")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке в API: {e}")
            return False

    async def run(self):
        logger.info(f"🤖 [{self.config.name}] Бот горячей линии запускается...")
        
        # Загружаем типы заявителей при старте
        logger.info("🔄 Первичная загрузка типов заявителей...")
        await self._load_requester_types()
        logger.info(f"✅ Загружено {len(self.requester_types)} типов заявителей")
        
        try:
            bot_info = await self.bot.get_me()
            logger.info(f"[{self.config.name}] Бот успешно подключен: @{bot_info.username}")
        except Exception as e:
            logger.error(f"[{self.config.name}] Ошибка подключения: {e}")
            return
        
        try:
            await self.bot.delete_webhook()
        except Exception as e:
            logger.warning(f"[{self.config.name}] Ошибка удаления webhook: {e}")
        
        logger.info(f"🚀 [{self.config.name}] Бот готов к работе!")
        await self.dp.start_polling(self.bot)


def create_bot_configs() -> list:
    api_url = os.getenv("HOTLINE_API_URL", "http://back_tghr_department:8070")
    logger.info(f"🌐 API URL: {api_url}")
    
    return [
        HotlineBotConfig(
            name="hotline_anonymous_bot",
            token=os.getenv("MAX_BOT_TOKEN"),
            default_channel_id="00000000-0000-0000-0000-000000000000"
        )
    ]


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