import asyncio
import json
import os
from datetime import datetime, timedelta
from telethon import TelegramClient, events
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация с вашими данными
class Config:
    SESSION_FILE = "user_session"
    USERS_FILE = "users.json"
    TARGET_BOT = "@iris_black_bot"
    FARM_COMMAND = "Ферма"
    INTERVAL_HOURS = 4
    INTERVAL_MINUTES = 5
    
    # Ваши данные
    API_ID = 38301798  # Ваш API ID
    API_HASH = "36cf2066c8b42327fdf39f7f735a1858"  # Ваш API Hash
    PHONE_NUMBER = "14192888398"  # Ваш номер телефона

class AutoFarmer:
    """Класс для автоматической фермы"""
    
    def __init__(self, api_id, api_hash, phone):
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.client = None
        self.running = False
        self.task = None
        self.stats = {
            "total_farms": 0,
            "last_farm": None,
            "errors": 0
        }
    
    async def start(self):
        """Запуск клиента и начало фермы"""
        try:
            session_name = f"session_{self.phone}"
            self.client = TelegramClient(session_name, self.api_id, self.api_hash)
            
            logger.info(f"Подключение к аккаунту {self.phone}...")
            await self.client.start(phone=self.phone)
            
            # Проверка подключения
            me = await self.client.get_me()
            logger.info(f"✅ Успешный вход! Аккаунт: {me.first_name} (@{me.username})")
            
            self.running = True
            
            # Запуск цикла фермы
            self.task = asyncio.create_task(self.farm_loop())
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска: {e}")
            self.running = False
            return False
    
    async def stop(self):
        """Остановка клиента"""
        self.running = False
        if self.task:
            self.task.cancel()
        if self.client:
            await self.client.disconnect()
        logger.info(f"Ферма остановлена для {self.phone}")
    
    async def farm_loop(self):
        """Основной цикл фермы"""
        logger.info(f"🚀 Запущен цикл фермы для {self.phone}")
        logger.info(f"⏰ Интервал: каждые {Config.INTERVAL_HOURS} часа {Config.INTERVAL_MINUTES} минут")
        
        while self.running:
            try:
                # Отправка команды в бота
                await self.send_farm_command()
                
                # Обновление статистики
                self.stats["total_farms"] += 1
                self.stats["last_farm"] = datetime.now().isoformat()
                
                # Расчет времени следующей фермы
                wait_time = timedelta(hours=Config.INTERVAL_HOURS, 
                                     minutes=Config.INTERVAL_MINUTES)
                
                next_farm = datetime.now() + wait_time
                logger.info(f"✅ Команда отправлена! Статистика: {self.stats['total_farms']} ферм")
                logger.info(f"⏰ Следующая ферма: {next_farm.strftime('%H:%M:%S %d.%m.%Y')}")
                logger.info(f"💤 Ожидание {Config.INTERVAL_HOURS}ч {Config.INTERVAL_MINUTES}м...")
                
                await asyncio.sleep(wait_time.total_seconds())
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.stats["errors"] += 1
                logger.error(f"❌ Ошибка в цикле фермы: {e}")
                logger.info("⏱ Повторная попытка через 5 минут...")
                await asyncio.sleep(300)  # 5 минут
    
    async def send_farm_command(self):
        """Отправка команды в бота"""
        try:
            logger.info(f"📤 Отправка команды '{Config.FARM_COMMAND}' в {Config.TARGET_BOT}...")
            
            # Получаем сущность бота
            bot = await self.client.get_input_entity(Config.TARGET_BOT)
            
            # Отправляем сообщение
            await self.client.send_message(bot, Config.FARM_COMMAND)
            
            # Ждем ответ от бота
            await asyncio.sleep(3)
            
            # Получаем последние сообщения
            messages = await self.client.get_messages(bot, limit=1)
            if messages:
                response = messages[0].message
                logger.info(f"📥 Ответ от бота: {response[:150]}..." if len(response) > 150 else f"📥 Ответ: {response}")
            else:
                logger.info("📥 Нет ответа от бота")
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки команды: {e}")
            raise
    
    async def get_status(self):
        """Получение статуса"""
        return {
            "running": self.running,
            "phone": self.phone,
            "stats": self.stats,
            "next_farm": (datetime.now() + timedelta(hours=Config.INTERVAL_HOURS, 
                                                     minutes=Config.INTERVAL_MINUTES)).isoformat() if self.running else None
        }

async def save_stats(farmer):
    """Сохранение статистики в файл"""
    stats_file = "farm_stats.json"
    try:
        status = await farmer.get_status()
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
        logger.info(f"📊 Статистика сохранена в {stats_file}")
    except Exception as e:
        logger.error(f"Ошибка сохранения статистики: {e}")

async def main():
    """Основная функция"""
    logger.info("=" * 50)
    logger.info("🚀 ЗАПУСК АВТОМАТИЧЕСКОЙ ФЕРМЫ ДЛЯ @iris_black_bot")
    logger.info("=" * 50)
    
    # Создаем фермера с вашими данными
    farmer = AutoFarmer(
        Config.API_ID,
        Config.API_HASH,
        Config.PHONE_NUMBER
    )
    
    # Запускаем ферму
    logger.info(f"📱 Номер телефона: {Config.PHONE_NUMBER}")
    logger.info(f"🎯 Целевой бот: {Config.TARGET_BOT}")
    logger.info(f"⏰ Интервал: каждые {Config.INTERVAL_HOURS}ч {Config.INTERVAL_MINUTES}м")
    logger.info("-" * 50)
    
    start_success = await farmer.start()
    
    if not start_success:
        logger.error("❌ Не удалось запустить ферму. Проверьте:")
        logger.error("1. Правильность номера телефона")
        logger.error("2. Наличие интернета")
        logger.error("3. Правильность API ID и API Hash")
        return
    
    # Сохраняем статистику каждые 10 минут
    try:
        while farmer.running:
            await asyncio.sleep(600)  # 10 минут
            await save_stats(farmer)
    except KeyboardInterrupt:
        logger.info("\n" + "=" * 50)
        logger.info("⛔ Остановка фермы...")
        await farmer.stop()
        await save_stats(farmer)
        logger.info("📊 Итоговая статистика:")
        logger.info(f"   Всего ферм: {farmer.stats['total_farms']}")
        logger.info(f"   Ошибок: {farmer.stats['errors']}")
        logger.info("✅ Ферма успешно остановлена")
        logger.info("=" * 50)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Программа остановлена пользователем")
