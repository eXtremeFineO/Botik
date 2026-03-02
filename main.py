import os
import json
import random
import time
import html
import asyncio
import hashlib
import hmac
import re
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, LabeledPrice, PreCheckoutQuery
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения!")

CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@ZenlessCards")
ADMIN_IDS = [int(id) for id in os.getenv("ADMIN_IDS", "831108038,7691491139").split(",")]

bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
rt = Router()
dp.include_router(rt)

# ================== FSM для добавления агента ==================
class AddAgent(StatesGroup):
    waiting_for_photo = State()

DATA_DIR = "data"
AGENTS_DIR = "agents"
USERS_FILE = f"{DATA_DIR}/users.json"
AGENTS_FILE = f"{DATA_DIR}/agents.json"
DONATIONS_FILE = f"{DATA_DIR}/donations.json"
SUBSCRIPTION_CHECK_FILE = f"{DATA_DIR}/last_subscription_check.json"
PROMOCODES_FILE = f"{DATA_DIR}/promocodes.json"
UPDATE_NOTIFICATIONS_FILE = f"{DATA_DIR}/update_notifications.json"

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(AGENTS_DIR, exist_ok=True)

# ================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================
def load_data(filename, default=None):
    if default is None: default = {}
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(default, f, indent=4, ensure_ascii=False)
        return default

def save_data(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_update_notifications():
    return load_data(UPDATE_NOTIFICATIONS_FILE, {"sent_versions": [], "last_check": 0})

def save_update_notifications(data):
    save_data(UPDATE_NOTIFICATIONS_FILE, data)

async def send_emergency_update_notification():
    try:
        update_data = load_update_notifications()
        current_version = "V2.0.0"
        if current_version in update_data.get("sent_versions", []):
            return
        update_message = (
            "📡 ОБНОВЛЕНИЕ INTER-KNOT!\n"
            f"{current_version}\n\n"
            "✨ Уважаемые Прокси! Произведено обновление терминала.\n\n"
            "🔧 ИСПРАВЛЕНИЯ И УЛУЧШЕНИЯ:\n\n"
            "🧬 АГЕНТЫ:\n"
            "<blockquote>• Исправлена система определения новых агентов и резонанса\n"
            "• Корректный подсчёт репутации за агентов</blockquote>\n\n"
            "🌐 РЕЙТИНГ ПРОКСИ:\n"
            "<blockquote>• Обновление отображаемых данных в топе</blockquote>\n\n"
            "📡 SIGNAL SEARCH:\n"
            "<blockquote>• Сбалансированы шансы выпадения агентов различных рангов\n"
            "• Повышен шанс получения нового агента до 60%</blockquote>\n\n"
            "📄 АРХИВ АГЕНТОВ:\n"
            "<blockquote>• Добавлена пагинация для удобного просмотра коллекции</blockquote>\n\n"
            "⚡️ ДОПОЛНИТЕЛЬНО:\n"
            "<blockquote>• Исправлена кнопка возврата в профиль\n"
            "• Улучшена стабильность работы\n"
            "• Оптимизирована система промокодов</blockquote>\n\n"
            "🔄 ЕСЛИ У ВАС БЫЛИ ПРОБЛЕМЫ:\n"
            "<blockquote>Если ранее система некорректно определяла новых агентов – теперь это исправлено. Продолжайте исследования Холлоу!</blockquote>"
        )
        await bot.send_message(chat_id=CHANNEL_USERNAME, text=update_message, parse_mode=ParseMode.HTML)
        update_data["sent_versions"].append(current_version)
        update_data["last_check"] = time.time()
        save_update_notifications(update_data)
        print(f"✅ Уведомление об обновлении {current_version} отправлено")
    except Exception as e:
        print(f"❌ Ошибка при отправке уведомления об обновлении: {e}")

# ================== АГЕНТЫ (РАНЕЕ КАРТОЧКИ) ==================
AGENT_RANK_MAP = {
    "rank_a": "Rank A",
    "rank_a+": "Rank A+",
    "rank_s": "Rank S",
    "rank_s+": "Rank S+",
    "rank_s++": "🔥 Rank S++"
}

DROP_RATES = {
    "Rank A": 0.55,
    "Rank A+": 0.25,
    "Rank S": 0.12,
    "Rank S+": 0.06,
    "🔥 Rank S++": 0.02
}

RANK_REPUTATION = {
    "Rank A": 1000,
    "Rank A+": 2500,
    "Rank S": 5000,
    "Rank S+": 15000,
    "🔥 Rank S++": 50000
}

RANK_DENNY = {
    "Rank A": 3,
    "Rank A+": 8,
    "Rank S": 15,
    "Rank S+": 50,
    "🔥 Rank S++": 200
}

def scan_agents():
    agents = []
    agent_id = 1
    for rank_folder, rank_name in AGENT_RANK_MAP.items():
        folder_path = os.path.join(AGENTS_DIR, rank_folder)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            continue
        for filename in os.listdir(folder_path):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
                agent_name = os.path.splitext(filename)[0]
                agents.append({
                    "id": agent_id,
                    "name": agent_name,
                    "rank": rank_name,
                    "image": f"{AGENTS_DIR}/{rank_folder}/{filename}",
                    "file_extension": os.path.splitext(filename)[1].lower()
                })
                agent_id += 1
    save_data(AGENTS_FILE, {"agents": agents, "total_agents": len(agents)})
    return agents

def load_agents():
    data = load_data(AGENTS_FILE, {"agents": [], "total_agents": 0})
    if not data["agents"]:
        return scan_agents()
    return data["agents"]

def get_total_agents_count():
    data = load_data(AGENTS_FILE, {"agents": [], "total_agents": 0})
    if data.get("total_agents", 0) == 0 and data.get("agents"):
        data["total_agents"] = len(data["agents"])
        save_data(AGENTS_FILE, data)
    return data.get("total_agents", 0)

agents_data = load_agents()
TOTAL_AGENTS = get_total_agents_count()
print(f"📊 Загружено агентов: {len(agents_data)}")
print(f"🎯 Всего агентов в системе: {TOTAL_AGENTS}")

def get_user_unique_agents_count(user_agents):
    return len(set(user_agents))

# ================== ПОЛЬЗОВАТЕЛИ ==================
def migrate_user_data(user_data):
    default_structure = {
        "name": None,
        "denny": 0,
        "reputation": 3000,
        "agents": [],
        "last_search": 0,
        "last_supply_drop": 0,
        "main_agent": None,
        "vip_contract": False,
        "vip_until": 0,
        "proxy_rank": "Новобранец",
        "registered": datetime.now().isoformat(),
        "total_agents_collected": 0,
        "supply_drops": 0,
        "total_stars_spent": 0,
        "is_vip_sponsor": False,
        "had_supply_drop": False,
        "notified_unsubscribed": False,
        "telegram_first_name": None,
        "telegram_last_name": None,
        "telegram_username": None,
        "used_promocodes": [],
        "extra_runs": 0
    }
    migrated = default_structure.copy()
    # Преобразование старых ключей
    if "coins" in user_data: migrated["denny"] = user_data["coins"]
    if "points" in user_data: migrated["reputation"] = user_data["points"]
    if "cards" in user_data: migrated["agents"] = user_data["cards"]
    if "last_card" in user_data: migrated["last_search"] = user_data["last_card"]
    if "last_bonus" in user_data: migrated["last_supply_drop"] = user_data["last_bonus"]
    if "favorite" in user_data: migrated["main_agent"] = user_data["favorite"]
    if "premium" in user_data: migrated["vip_contract"] = user_data["premium"]
    if "premium_until" in user_data: migrated["vip_until"] = user_data["premium_until"]
    if "title" in user_data: migrated["proxy_rank"] = user_data["title"]
    if "total_cards_collected" in user_data: migrated["total_agents_collected"] = user_data["total_cards_collected"]
    if "bonus_attempts" in user_data: migrated["supply_drops"] = user_data["bonus_attempts"]
    if "total_donated" in user_data: migrated["total_stars_spent"] = user_data["total_donated"]
    if "is_supporter" in user_data: migrated["is_vip_sponsor"] = user_data["is_supporter"]
    if "had_bonus" in user_data: migrated["had_supply_drop"] = user_data["had_bonus"]
    if "extra_attempts" in user_data: migrated["extra_runs"] = user_data["extra_attempts"]
    for key, value in user_data.items():
        if key not in migrated:
            migrated[key] = value
    return migrated

def generate_display_name(user_id_str, telegram_user=None, user_data=None):
    if telegram_user:
        if telegram_user.first_name:
            if telegram_user.last_name:
                return f"{telegram_user.first_name} {telegram_user.last_name}"
            else:
                return telegram_user.first_name
        elif telegram_user.username:
            return f"@{telegram_user.username}"
    if user_data:
        if user_data.get("telegram_first_name"):
            if user_data.get("telegram_last_name"):
                return f"{user_data['telegram_first_name']} {user_data['telegram_last_name']}"
            else:
                return user_data['telegram_first_name']
        elif user_data.get("telegram_username"):
            return f"@{user_data['telegram_username']}"
    random_names = ["Proxy", "Operator", "Neo", "Zero", "Signal"]
    return f"{random.choice(random_names)}{user_id_str[-2:]}"

def get_user_display_name(user_data, user_id, telegram_user=None):
    if user_data.get("name"):
        return user_data["name"]
    return generate_display_name(str(user_id), telegram_user, user_data)

def get_user_display_name_from_saved(user_data, user_id):
    if user_data.get("name"):
        return user_data["name"]
    return generate_display_name(str(user_id), None, user_data)

async def update_user_names_automatically():
    users = load_data(USERS_FILE, {})
    updated_count = 0
    for user_id_str, user_data in users.items():
        try:
            user_id = int(user_id_str)
            chat_member = await bot.get_chat_member(user_id, user_id)
            telegram_user = chat_member.user
            current_name = user_data.get("name")
            new_name = generate_display_name(user_id_str, telegram_user, user_data)
            if (not current_name or current_name in ["Alex", "Max", "Kate", "Player"] or
                current_name.startswith("Player") or current_name.startswith("User")):
                old_name = current_name or "None"
                users[user_id_str]["name"] = new_name
                users[user_id_str]["telegram_first_name"] = telegram_user.first_name
                users[user_id_str]["telegram_last_name"] = telegram_user.last_name
                users[user_id_str]["telegram_username"] = telegram_user.username
                updated_count += 1
                print(f"🔄 Автообновление: {user_id_str} {old_name} -> {new_name}")
        except Exception as e:
            continue
    if updated_count > 0:
        save_data(USERS_FILE, users)
        print(f"🎉 Автоматически обновлено {updated_count} пользователей!")
    return updated_count

def get_user(user_id, telegram_user=None):
    users = load_data(USERS_FILE, {})
    user_id_str = str(user_id)
    if user_id_str not in users:
        display_name = generate_display_name(user_id_str, telegram_user)
        users[user_id_str] = {
            "name": display_name,
            "denny": 0,
            "reputation": 3000,
            "agents": [],
            "last_search": 0,
            "last_supply_drop": 0,
            "main_agent": None,
            "vip_contract": False,
            "vip_until": 0,
            "proxy_rank": "Новобранец",
            "registered": datetime.now().isoformat(),
            "total_agents_collected": 0,
            "supply_drops": 0,
            "total_stars_spent": 0,
            "is_vip_sponsor": False,
            "had_supply_drop": False,
            "notified_unsubscribed": False,
            "telegram_first_name": telegram_user.first_name if telegram_user else None,
            "telegram_last_name": telegram_user.last_name if telegram_user else None,
            "telegram_username": telegram_user.username if telegram_user else None,
            "used_promocodes": [],
            "extra_runs": 0
        }
        save_data(USERS_FILE, users)
        print(f"🆕 Создан новый Прокси: {user_id_str} -> {display_name}")
    else:
        if telegram_user:
            users[user_id_str]["telegram_first_name"] = telegram_user.first_name
            users[user_id_str]["telegram_last_name"] = telegram_user.last_name
            users[user_id_str]["telegram_username"] = telegram_user.username
            current_name = users[user_id_str].get("name")
            new_name = generate_display_name(user_id_str, telegram_user, users[user_id_str])
            if not current_name or current_name != new_name:
                old_name = current_name or "None"
                users[user_id_str]["name"] = new_name
                print(f"🔄 Обновлено имя Прокси {user_id_str}: {old_name} -> {new_name}")
        users[user_id_str] = migrate_user_data(users[user_id_str])
        save_data(USERS_FILE, users)
    return users[user_id_str]

def update_user(user_id, **kwargs):
    users = load_data(USERS_FILE, {})
    user_id = str(user_id)
    if user_id not in users:
        get_user(user_id)
        users = load_data(USERS_FILE, {})
    for key, value in kwargs.items():
        users[user_id][key] = value
    save_data(USERS_FILE, users)
    return users[user_id]

def load_donations():
    return load_data(DONATIONS_FILE, {"donations": [], "total_stars": 0})

def save_donation(user_id, username, stars, product="vip_contract"):
    donations = load_donations()
    donations["donations"].append({
        "user_id": user_id,
        "username": username,
        "stars": stars,
        "product": product,
        "timestamp": datetime.now().isoformat()
    })
    donations["total_stars"] += stars
    save_data(DONATIONS_FILE, donations)

# ================== РАНГИ ПРОКСИ ==================
PROXY_RANKS = {
    0: "Новобранец",
    5000: "Младший Прокси",
    15000: "Оперативный Прокси",
    30000: "Старший Прокси",
    50000: "Элитный Прокси",
    100000: "Фаэтон"  # был огонёк убран
}

def get_proxy_rank(reputation):
    sorted_thresholds = sorted(PROXY_RANKS.keys(), reverse=True)
    for threshold in sorted_thresholds:
        if reputation >= threshold:
            return PROXY_RANKS[threshold]
    return "Новобранец"

def has_vip_contract(user_id):
    user = get_user(user_id)
    if "vip_contract" not in user:
        user = migrate_user_data(user)
        update_user(user_id, **user)
    if user.get("vip_contract", False) and user.get("vip_until", 0) > time.time():
        return True
    elif user.get("vip_contract", False) and user.get("vip_until", 0) <= time.time():
        update_user(user_id, vip_contract=False)
        return False
    return False

# ================== ПРОВЕРКА ПОДПИСКИ НА КАНАЛ ==================
async def check_channel_subscription(user_id: int) -> bool:
    try:
        chat_member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Ошибка проверки подписки: {e}")
        return False

async def check_subscriptions_periodically():
    while True:
        try:
            await asyncio.sleep(3600)
            users = load_data(USERS_FILE, {})
            for user_id_str, user_data in users.items():
                if user_data.get("had_supply_drop", False):
                    user_id = int(user_id_str)
                    is_subscribed = await check_channel_subscription(user_id)
                    if not is_subscribed and not user_data.get("notified_unsubscribed", False):
                        try:
                            await bot.send_message(
                                user_id,
                                "❌ <b>Вы отключились от канала Inter-Knot!</b>\n\n"
                                "<blockquote>Для получения Supply Drop необходимо восстановить подключение.</blockquote>"
                            )
                            update_user(user_id, notified_unsubscribed=True)
                        except Exception:
                            pass
            print(f"🔍 Проверка подписок завершена: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception as e:
            print(f"Ошибка при проверке подписок: {e}")
            await asyncio.sleep(300)

# ================== АВТОПРОВЕРКА НОВЫХ АГЕНТОВ ==================
async def check_new_agents_periodically():
    global agents_data, TOTAL_AGENTS
    while True:
        try:
            await asyncio.sleep(60)
            old_count = len(agents_data)
            new_agents = scan_agents()
            new_count = len(new_agents)
            agents_data = new_agents
            TOTAL_AGENTS = get_total_agents_count()
            if new_count > old_count:
                added_count = new_count - old_count
                print(f"🎉 Обнаружено {added_count} новых агентов! Всего: {new_count}")
                for admin_id in ADMIN_IDS:
                    try:
                        await bot.send_message(
                            admin_id,
                            f"🎊 <b>Обнаружены новые агенты!</b>\n\n"
                            f"<blockquote>Добавлено: <b>{added_count}</b> новых агентов\n"
                            f"Теперь всего: <b>{new_count}</b> агентов в системе</blockquote>"
                        )
                    except Exception:
                        pass
            elif new_count < old_count:
                removed_count = old_count - new_count
                print(f"🗑️ Удалено {removed_count} агентов! Теперь: {new_count}")
        except Exception as e:
            print(f"❌ Ошибка при проверке новых агентов: {e}")
            await asyncio.sleep(30)

# ================== ТОП ПРОКСИ ==================
async def get_top_proxies_text(limit=15):
    users = load_data(USERS_FILE, {})
    top_users = []
    for user_id, user_data in users.items():
        user_data = migrate_user_data(user_data)
        users[user_id] = user_data
        if user_data.get("reputation", 0) > 0:
            user_name = html.escape(get_user_display_name_from_saved(user_data, user_id))
            unique_agents = get_user_unique_agents_count(user_data.get("agents", []))
            has_vip = has_vip_contract(int(user_id))
            top_users.append((user_name, user_data["reputation"], unique_agents, has_vip))
    save_data(USERS_FILE, users)
    top_users.sort(key=lambda x: x[1], reverse=True)
    top_text = "🌐 <b>Рейтинг Прокси Inter-Knot</b>\n\n<blockquote>"
    for i, (name, reputation, agents_count, is_vip) in enumerate(top_users[:limit], 1):
        vip_badge = "💠 " if is_vip else ""
        top_text += f"{i}. {vip_badge}{name} - {reputation:,} реп. | {agents_count} аг.\n"
    top_text += "</blockquote>"
    return top_text

# ================== ПРОМОКОДЫ ==================
def load_promocodes():
    return load_data(PROMOCODES_FILE, {"promocodes": {}})

def save_promocodes(data):
    save_data(PROMOCODES_FILE, data)

def fix_broken_promocodes():
    promocodes = load_promocodes()
    fixed_count = 0
    for code, data in promocodes.get("promocodes", {}).items():
        if "type" not in data:
            data["type"] = "denny"
            data["value"] = data.get("value", 10)
            data["uses"] = data.get("uses", 0)
            data["max_uses"] = data.get("max_uses", 10)
            data["active"] = data.get("active", True)
            data["created_by"] = data.get("created_by", "system")
            data["created_at"] = data.get("created_at", datetime.now().isoformat())
            fixed_count += 1
    if fixed_count > 0:
        save_promocodes(promocodes)
        print(f"🔧 Исправлено {fixed_count} поврежденных промокодов")
    return fixed_count

def init_promocodes():
    promocodes = load_promocodes()
    if "test" not in promocodes.get("promocodes", {}):
        promocodes["promocodes"]["test"] = {
            "type": "denny",
            "value": 2,
            "uses": 0,
            "max_uses": 100,
            "active": True,
            "created_by": "system",
            "created_at": datetime.now().isoformat()
        }
        save_promocodes(promocodes)
        print("✅ Инициализирован тестовый промокод: test")

def get_random_agent_with_rank_balanced():
    rank_roll = random.random()
    cumulative = 0
    selected_rank = "Rank A"
    for rank, chance in DROP_RATES.items():
        cumulative += chance
        if rank_roll <= cumulative:
            selected_rank = rank
            break
    available_agents = [a for a in agents_data if a["rank"] == selected_rank]
    if not available_agents:
        selected_rank = "Rank A"
        available_agents = [a for a in agents_data if a["rank"] == "Rank A"]
    return random.choice(available_agents), selected_rank

def get_promocode_info(code):
    promocodes = load_promocodes()
    if code not in promocodes.get("promocodes", {}):
        return None
    promo_data = promocodes["promocodes"][code]
    if "type" not in promo_data:
        return None
    reward_info = ""
    promo_type = promo_data.get("type", "")
    if promo_type == "denny":
        reward_info = f"{promo_data.get('value', 0)} Денни"
    elif promo_type == "vip":
        reward_info = f"{promo_data.get('value', 0)} дней VIP Контракта"
    elif promo_type == "agent":
        agent_name = next((a["name"] for a in agents_data if a["id"] == promo_data.get("value", 0)), "Неизвестный агент")
        reward_info = f"Агент: {agent_name} (ID: {promo_data.get('value', 0)})"
    elif promo_type == "reputation":
        reward_info = f"{promo_data.get('value', 0)} репутации"
    elif promo_type == "hollow_run":
        reward_info = "Дополнительный выход в Холлоу"
    elif promo_type == "random_agent":
        reward_info = "Случайный агент"
    else:
        reward_info = "Неизвестная награда"
    return {
        "code": code,
        "type": promo_type,
        "value": promo_data.get("value", 0),
        "uses": promo_data.get("uses", 0),
        "max_uses": promo_data.get("max_uses", 1),
        "active": promo_data.get("active", True),
        "created_by": promo_data.get("created_by", "unknown"),
        "created_at": promo_data.get("created_at", "unknown"),
        "reward_info": reward_info
    }

def use_promocode(promo_code, user_id, message=None):
    promocodes = load_promocodes()
    users = load_data(USERS_FILE, {})
    user_id_str = str(user_id)
    if promo_code not in promocodes.get("promocodes", {}):
        return False, "❌ Промокод не найден"
    promo_data = promocodes["promocodes"][promo_code]
    if not promo_data.get("active", True):
        return False, "❌ Промокод неактивен"
    if promo_data["uses"] >= promo_data["max_uses"]:
        return False, "❌ Лимит использований промокода исчерпан"
    if user_id_str not in users:
        return False, "❌ Пользователь не найден"
    if promo_code in users[user_id_str].get("used_promocodes", []):
        return False, "❌ Вы уже использовали этот промокод"
    promo_type = promo_data.get("type", "denny")
    success_message = ""
    if promo_type == "denny":
        value = promo_data["value"]
        users[user_id_str]["denny"] += value
        success_message = f"✅ Промокод активирован! Получено +{value} Денни"
    elif promo_type == "vip":
        days = promo_data["value"]
        vip_until = datetime.now() + timedelta(days=days)
        current_until = users[user_id_str].get("vip_until", 0)
        if current_until > time.time():
            new_until = datetime.fromtimestamp(current_until) + timedelta(days=days)
            users[user_id_str]["vip_until"] = new_until.timestamp()
        else:
            users[user_id_str]["vip_until"] = vip_until.timestamp()
            users[user_id_str]["vip_contract"] = True
        success_message = f"✅ Промокод активирован! Получено +{days} дней VIP Контракта"
    elif promo_type == "agent":
        agent_id = promo_data["value"]
        agent_exists = any(a["id"] == agent_id for a in agents_data)
        if not agent_exists:
            return False, "❌ Указанный агент не существует"
        users[user_id_str]["agents"].append(agent_id)
        agent_name = next((a["name"] for a in agents_data if a["id"] == agent_id), "Неизвестный агент")
        success_message = f"✅ Промокод активирован! Получен агент: {agent_name}"
    elif promo_type == "reputation":
        value = promo_data["value"]
        users[user_id_str]["reputation"] += value
        success_message = f"✅ Промокод активирован! Получено +{value} репутации"
    elif promo_type == "hollow_run":
        if "extra_runs" not in users[user_id_str]:
            users[user_id_str]["extra_runs"] = 0
        users[user_id_str]["extra_runs"] += 1
        success_message = f"✅ Промокод активирован! Получен дополнительный выход в Холлоу"
    elif promo_type == "random_agent":
        agent, _ = get_random_agent_with_rank_balanced()
        user_agent_set = set(users[user_id_str]["agents"])
        is_new = agent["id"] not in user_agent_set
        rep_earned = RANK_REPUTATION[agent["rank"]] // 2 if not is_new else RANK_REPUTATION[agent["rank"]]
        denny_earned = RANK_DENNY[agent["rank"]]
        if has_vip_contract(user_id):
            rep_earned = int(rep_earned * 1.2)
            denny_earned = int(denny_earned * 1.5)
        new_agents = users[user_id_str]["agents"].copy()
        if is_new:
            new_agents.append(agent["id"])
        users[user_id_str]["agents"] = new_agents
        users[user_id_str]["reputation"] += rep_earned
        users[user_id_str]["denny"] += denny_earned
        users[user_id_str]["total_agents_collected"] = users[user_id_str].get("total_agents_collected", 0) + (1 if is_new else 0)
        users[user_id_str]["proxy_rank"] = get_proxy_rank(users[user_id_str]["reputation"])
        success_message = f"✅ Промокод активирован! Получен случайный агент: {agent['name']} ({agent['rank']})"
        if message:
            try:
                file = FSInputFile(agent["image"])
                caption = (
                    f"📡 <b>Промокод: {'Новый агент!' if is_new else 'Резонанс'}</b>\n\n"
                    f"<blockquote>🧬 <b>{html.escape(agent['name'])}</b>\n"
                    f"🏅 Ранг: <b>{agent['rank']}</b>\n"
                    f"🌐 Репутация: <b>+{rep_earned}</b>\n"
                    f"💳 Денни: <b>+{denny_earned}</b></blockquote>\n\n"
                    f"🎯 Статус: <b>{'🆕 Новый агент' if is_new else '🔁 Резонанс'}</b>"
                )
                ext = agent.get("file_extension", "").lower()
                if ext == ".gif":
                    asyncio.create_task(message.answer_animation(animation=file, caption=caption))
                else:
                    asyncio.create_task(message.answer_photo(photo=file, caption=caption))
            except Exception as e:
                print(f"Ошибка отправки изображения агента: {e}")
    else:
        return False, "❌ Неизвестный тип промокода"
    if "used_promocodes" not in users[user_id_str]:
        users[user_id_str]["used_promocodes"] = []
    users[user_id_str]["used_promocodes"].append(promo_code)
    promocodes["promocodes"][promo_code]["uses"] += 1
    save_data(USERS_FILE, users)
    save_promocodes(promocodes)
    return True, success_message

def create_promocode(code, promo_type, value, max_uses, created_by="admin"):
    promocodes = load_promocodes()
    if code in promocodes.get("promocodes", {}):
        return False, "❌ Промокод уже существует"
    valid_types = ["denny", "vip", "agent", "reputation", "hollow_run", "random_agent"]
    if promo_type not in valid_types:
        return False, f"❌ Неверный тип промокода. Допустимые типы: {', '.join(valid_types)}"
    if promo_type == "agent":
        agent_exists = any(a["id"] == value for a in agents_data)
        if not agent_exists:
            return False, "❌ Указанный агент не существует"
    promocodes["promocodes"][code] = {
        "type": promo_type,
        "value": value,
        "uses": 0,
        "max_uses": max_uses,
        "active": True,
        "created_by": created_by,
        "created_at": datetime.now().isoformat()
    }
    save_promocodes(promocodes)
    return True, f"✅ Промокод '{code}' успешно создан!"

def toggle_promocode(code, active):
    promocodes = load_promocodes()
    if code not in promocodes.get("promocodes", {}):
        return False, "❌ Промокод не найден"
    promocodes["promocodes"][code]["active"] = active
    save_promocodes(promocodes)
    status = "активирован" if active else "деактивирован"
    return True, f"✅ Промокод '{code}' {status}!"

def delete_promocode(code):
    promocodes = load_promocodes()
    if code not in promocodes.get("promocodes", {}):
        return False, "❌ Промокод не найден"
    del promocodes["promocodes"][code]
    save_promocodes(promocodes)
    return True, f"✅ Промокод '{code}' удален!"

# ================== КЛАВИАТУРЫ ==================
def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить бота в чат", url="https://t.me/SealsCards_bot?startgroup=new")]
    ])

def profile_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧬 Архив агентов", callback_data="my_agents")]
    ])

def back_to_profile_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 К профилю", callback_data="back_to_profile")]
    ])

def vip_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💠 Активировать VIP Контракт (10 Stars)", callback_data="buy_vip_stars")],
        [InlineKeyboardButton(text="🔙 К профилю", callback_data="back_to_profile")]
    ])

def supply_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📡 Подключиться к Inter-Knot", url=f"https://t.me/SealCards")],
        [InlineKeyboardButton(text="🎁 Supply Drop", callback_data="get_supply_drop")]
    ])

def agent_with_supply_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Supply Drop", callback_data="get_supply_drop")]
    ])

# ================== ВЫДАЧА АГЕНТА ==================
async def process_agent_drop_balanced(message: Message, update_timer=True):
    user = get_user(message.from_user.id, message.from_user)
    user_agent_set = set(user["agents"])
    has_new_agents_available = len(user_agent_set) < TOTAL_AGENTS
    if has_new_agents_available:
        if random.random() < 0.6:
            available_new = [a for a in agents_data if a["id"] not in user_agent_set]
            if available_new:
                agent, selected_rank = get_random_agent_with_rank_balanced()
                new_in_rank = [a for a in available_new if a["rank"] == selected_rank]
                if new_in_rank:
                    agent = random.choice(new_in_rank)
                else:
                    agent = random.choice(available_new)
            else:
                agent, _ = get_random_agent_with_rank_balanced()
        else:
            agent, _ = get_random_agent_with_rank_balanced()
    else:
        agent, _ = get_random_agent_with_rank_balanced()
    is_new = agent["id"] not in user_agent_set
    rep_earned = RANK_REPUTATION[agent["rank"]] // 2 if not is_new else RANK_REPUTATION[agent["rank"]]
    denny_earned = RANK_DENNY[agent["rank"]]
    if has_vip_contract(message.from_user.id):
        rep_earned = int(rep_earned * 1.2)
        denny_earned = int(denny_earned * 1.5)
    new_agents_list = user["agents"].copy()
    if is_new:
        new_agents_list.append(agent["id"])
    update_data = {
        "agents": new_agents_list,
        "reputation": user["reputation"] + rep_earned,
        "denny": user["denny"] + denny_earned,
        "total_agents_collected": user.get("total_agents_collected", 0) + (1 if is_new else 0),
        "proxy_rank": get_proxy_rank(user["reputation"] + rep_earned)
    }
    if update_timer:
        update_data["last_search"] = time.time()
    update_user(message.from_user.id, **update_data)
    status_text = "🆕 Новый агент" if is_new else "🔁 Резонанс"
    card_type_text = "Signal Search завершён"
    try:
        file = FSInputFile(agent["image"])
        caption = (
            f"📡 <b>{card_type_text}</b>\n\n"
            f"<blockquote>🧬 <b>{html.escape(agent['name'])}</b>\n"
            f"🏅 Ранг: <b>{agent['rank']}</b>\n"
            f"🌐 Репутация: <b>+{rep_earned}</b>\n"
            f"💳 Денни: <b>+{denny_earned}</b></blockquote>\n\n"
            f"🎯 Статус: <b>{status_text}</b>"
        )
        ext = agent.get("file_extension", "").lower()
        if ext == ".gif":
            await message.answer_animation(animation=file, caption=caption, reply_markup=agent_with_supply_keyboard())
        else:
            await message.answer_photo(photo=file, caption=caption, reply_markup=agent_with_supply_keyboard())
    except Exception as e:
        await message.answer(
            f"📡 <b>{card_type_text}</b>\n\n"
            f"<blockquote>🧬 <b>{html.escape(agent['name'])}</b>\n"
            f"🏅 Ранг: <b>{agent['rank']}</b>\n"
            f"🌐 Репутация: <b>+{rep_earned}</b>\n"
            f"💳 Денни: <b>+{denny_earned}</b></blockquote>\n\n"
            f"🎯 Статус: <b>{status_text}</b>\n\n⚠️ Изображение временно недоступно",
            reply_markup=agent_with_supply_keyboard()
        )

# ================== ПАГИНАЦИЯ АГЕНТОВ ==================
def get_agents_pagination_keyboard(user_agents, current_page=0, page_size=6):
    unique_agents = list(set(user_agents))
    total_pages = (len(unique_agents) + page_size - 1) // page_size
    if current_page >= total_pages:
        current_page = total_pages - 1
    if current_page < 0:
        current_page = 0
    start_idx = current_page * page_size
    end_idx = start_idx + page_size
    page_agents = unique_agents[start_idx:end_idx]
    keyboard = []
    row = []
    rank_emojis = {
        "Rank A": "⚪",
        "Rank A+": "🔵",
        "Rank S": "🟣",
        "Rank S+": "🟡",
        "🔥 Rank S++": "🔴"
    }
    for i, agent_id in enumerate(page_agents):
        agent = next((a for a in agents_data if a["id"] == agent_id), None)
        if agent:
            emoji = rank_emojis.get(agent["rank"], "⚪")
            btn_text = f"{emoji} {agent['name']}"
            if len(btn_text) > 15:
                btn_text = btn_text[:12] + "..."
            row.append(InlineKeyboardButton(text=btn_text, callback_data=f"view_agent_{agent_id}"))
            if len(row) == 2 or i == len(page_agents) - 1:
                keyboard.append(row)
                row = []
    pagination_btns = []
    if current_page > 0:
        pagination_btns.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"agents_page_{current_page-1}"))
    pagination_btns.append(InlineKeyboardButton(text=f"{current_page+1}/{total_pages}", callback_data="current_page"))
    if current_page < total_pages - 1:
        pagination_btns.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"agents_page_{current_page+1}"))
    if pagination_btns:
        keyboard.append(pagination_btns)
    keyboard.append([InlineKeyboardButton(text="⚡ Назначить основного", callback_data="choose_main_agent")])
    keyboard.append([InlineKeyboardButton(text="🔙 К профилю", callback_data="back_to_profile")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ================== АДМИН-КОМАНДЫ ==================
@dp.message(Command("admin_help"))
async def admin_help_command(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет доступа к админ командам")
        return
    admin_text = (
        "🛠️ <b>Команды администратора</b>\n\n"
        "<blockquote>👥 <b>Управление Прокси:</b>\n"
        "/grant_vip [ID] [дни] - выдать VIP Контракт\n"
        "/user_list - список всех Прокси\n"
        "/admin_stats - статистика бота\n\n"
        "🎫 <b>Промокоды:</b>\n"
        "/add_promo [код] [тип] [значение] [макс.исп.] - создать промокод\n"
        "/promo_info [код] - информация о промокоде\n"
        "/promo_list - список всех промокодов\n"
        "/promo_toggle [код] [on/off] - активировать/деактивировать\n"
        "/promo_delete [код] - удалить промокод\n\n"
        "📸 <b>Добавление агентов:</b>\n"
        "/add_agent - запустить режим добавления нового агента через фото\n"
        "/cancel - отменить текущее действие</blockquote>\n\n"
        "<b>🎫 Типы промокодов:</b>\n"
        "<blockquote>• denny - Денни\n"
        "• vip - дни VIP Контракта\n"
        "• agent - ID агента\n"
        "• reputation - репутация\n"
        "• hollow_run - доп. выход в Холлоу\n"
        "• random_agent - случайный агент</blockquote>"
    )
    await message.answer(admin_text)

@dp.message(Command("grant_vip"))
async def grant_vip_command(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет доступа")
        return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("❌ Использование: /grant_vip [ID] [дни]")
        return
    try:
        user_id = int(args[1])
        days = int(args[2])
        user = get_user(user_id)
        if not user:
            await message.answer("❌ Пользователь не найден")
            return
        vip_until = datetime.now() + timedelta(days=days)
        update_user(user_id, vip_contract=True, vip_until=vip_until.timestamp())
        try:
            user_name = get_user_display_name_from_saved(user, user_id)
            msg = (
                f"🎉 <b>VIP Контракт Inter-Knot активирован!</b>\n\n"
                f"<blockquote>Дорогой {user_name}!\n"
                f"Вам выдан VIP Контракт на {days} дней.\n"
                f"Действует до: {vip_until.strftime('%d.%m.%Y %H:%M')}</blockquote>\n\n"
                f"💠 <b>Преимущества:</b>\n"
                f"<blockquote>• +20% репутации и +30% Денни\n"
                f"• Повышенный шанс на агентов высоких рангов\n"
                f"• Особый значок в профиле</blockquote>"
            )
            await bot.send_message(user_id, msg)
        except Exception:
            pass
        await message.answer(f"✅ VIP Контракт выдан пользователю {user_id} на {days} дней")
    except ValueError:
        await message.answer("❌ Ошибка: ID и дни должны быть числами")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@dp.message(Command("user_list"))
async def user_list_command(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет доступа")
        return
    users = load_data(USERS_FILE, {})
    if not users:
        await message.answer("📝 Пользователей пока нет")
        return
    text = "📋 <b>Список Прокси:</b>\n\n"
    for i, (uid, ud) in enumerate(list(users.items())[:50], 1):
        name = html.escape(get_user_display_name_from_saved(ud, uid))
        rep = ud.get("reputation", 0)
        agents_cnt = len(set(ud.get("agents", [])))
        vip = "💠" if has_vip_contract(int(uid)) else "⚪"
        text += f"{i}. {vip} {name} (ID: {uid})\n   🌐 {rep:,} реп. | 🧬 {agents_cnt} аг.\n\n"
    if len(users) > 50:
        text += f"... и еще {len(users) - 50} Прокси"
    await message.answer(text)

@dp.message(Command("admin_stats"))
async def admin_stats_command(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет доступа")
        return
    users = load_data(USERS_FILE, {})
    agents_data = load_data(AGENTS_FILE, {"agents": [], "total_agents": 0})
    donations = load_donations()
    promocodes = load_promocodes()
    total_users = len(users)
    vip_users = 0
    total_rep = 0
    total_denny = 0
    total_agents_collected = 0
    for ud in users.values():
        if ud.get("vip_contract", False) and ud.get("vip_until", 0) > time.time():
            vip_users += 1
        total_rep += ud.get("reputation", 0)
        total_denny += ud.get("denny", 0)
        total_agents_collected += len(ud.get("agents", []))
    text = (
        "📊 <b>Статистика Inter-Knot</b>\n\n"
        f"<blockquote>👥 Прокси: {total_users}\n"
        f"💠 VIP: {vip_users}\n"
        f"🌐 Всего репутации: {total_rep:,}\n"
        f"💳 Всего Денни: {total_denny}\n"
        f"🧬 Агентов в системе: {agents_data.get('total_agents', 0)}\n"
        f"🎯 Собрано агентов: {total_agents_collected}\n"
        f"⭐ Всего донатов (Stars): {donations.get('total_stars', 0)}\n"
        f"🎫 Промокодов: {len(promocodes.get('promocodes', {}))}</blockquote>"
    )
    await message.answer(text)

@dp.message(Command("add_promo"))
async def add_promo_command(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет доступа")
        return
    args = message.text.split()
    if len(args) != 5:
        help_text = (
            "❌ Использование: /add_promo [код] [тип] [значение] [макс.исп.]\n\n"
            "Типы: denny, vip, agent, reputation, hollow_run, random_agent\n"
            "Пример: /add_promo TEST denny 100 10"
        )
        await message.answer(help_text)
        return
    try:
        code = args[1].lower()
        ptype = args[2].lower()
        value = int(args[3])
        max_uses = int(args[4])
        ok, msg = create_promocode(code, ptype, value, max_uses, f"admin_{message.from_user.id}")
        await message.answer(msg)
    except ValueError:
        await message.answer("❌ Значение и макс.исп. должны быть числами")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@dp.message(Command("promo_info"))
async def promo_info_command(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет доступа")
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /promo_info [код]")
        return
    info = get_promocode_info(args[1].lower())
    if not info:
        await message.answer("❌ Промокод не найден")
        return
    status = "✅ Активен" if info["active"] else "❌ Неактивен"
    text = (
        f"🎫 <b>Промокод {info['code']}</b>\n\n"
        f"Тип: {info['type']}\n"
        f"Награда: {info['reward_info']}\n"
        f"Использовано: {info['uses']}/{info['max_uses']}\n"
        f"Статус: {status}\n"
        f"Создан: {info['created_by']} в {info['created_at']}"
    )
    await message.answer(text)

@dp.message(Command("promo_list"))
async def promo_list_command(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет доступа")
        return
    promos = load_promocodes().get("promocodes", {})
    if not promos:
        await message.answer("📝 Промокодов нет")
        return
    active = []
    inactive = []
    for code, data in promos.items():
        info = get_promocode_info(code)
        if info:
            if data.get("active", True):
                active.append(info)
            else:
                inactive.append(info)
    text = "🎫 <b>Список промокодов</b>\n\n"
    if active:
        text += "✅ Активные:\n"
        for p in active:
            text += f"• {p['code']} - {p['reward_info']} ({p['uses']}/{p['max_uses']})\n"
    if inactive:
        text += "\n❌ Неактивные:\n"
        for p in inactive:
            text += f"• {p['code']} - {p['reward_info']}\n"
    await message.answer(text)

@dp.message(Command("promo_toggle"))
async def promo_toggle_command(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет доступа")
        return
    args = message.text.split()
    if len(args) != 3 or args[2] not in ["on", "off"]:
        await message.answer("❌ Использование: /promo_toggle [код] [on/off]")
        return
    ok, msg = toggle_promocode(args[1].lower(), args[2] == "on")
    await message.answer(msg)

@dp.message(Command("promo_delete"))
async def promo_delete_command(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет доступа")
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /promo_delete [код]")
        return
    ok, msg = delete_promocode(args[1].lower())
    await message.answer(msg)

# ================== КОМАНДЫ ДЛЯ ДОБАВЛЕНИЯ АГЕНТА (НОВЫЕ) ==================
@dp.message(Command("add_agent"))
async def cmd_add_agent(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет доступа")
        return
    await state.set_state(AddAgent.waiting_for_photo)
    await message.answer(
        "📸 <b>Режим добавления агента</b>\n\n"
        "Отправьте фото агента с подписью в формате:\n"
        "<code>Название ранг</code>\n\n"
        "Ранг указывается цифрой от 1 до 5:\n"
        "1 → Rank A\n"
        "2 → Rank A+\n"
        "3 → Rank S\n"
        "4 → Rank S+\n"
        "5 → 🔥 Rank S++\n\n"
        "Пример: <code>Кибер-тюлень 3</code>\n\n"
        "Для отмены введите /cancel"
    )

@dp.message(AddAgent.waiting_for_photo, F.photo)
async def handle_agent_photo(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id not in ADMIN_IDS:
        await state.clear()
        await message.answer("❌ Доступ запрещён")
        return

    caption = message.caption
    if not caption:
        await message.answer("❌ Нужна подпись с названием и рангом")
        return

    parts = caption.strip().split()
    if len(parts) < 2:
        await message.answer("❌ Формат: название и ранг (1-5)")
        return

    rank_str = parts[-1]
    if not rank_str.isdigit() or int(rank_str) not in range(1, 6):
        await message.answer("❌ Ранг должен быть числом от 1 до 5")
        return

    rank_num = int(rank_str)
    name = " ".join(parts[:-1]).strip()
    if not name:
        await message.answer("❌ Название не может быть пустым")
        return

    rank_folder = {
        1: "rank_a",
        2: "rank_a+",
        3: "rank_s",
        4: "rank_s+",
        5: "rank_s++"
    }[rank_num]

    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_path = file.file_path
    ext = os.path.splitext(file_path)[1] or ".jpg"

    # Очищаем название от недопустимых символов
    safe_name = re.sub(r'[^\w\s-]', '', name).strip()
    safe_name = re.sub(r'[-\s]+', '_', safe_name)
    filename = f"{safe_name}{ext}"
    full_path = os.path.join(AGENTS_DIR, rank_folder, filename)

    await bot.download_file(file_path, full_path)

    # Обновляем базу агентов
    scan_agents()

    await message.answer(f"✅ Агент «{name}» с рангом {rank_num} успешно добавлен в папку {rank_folder}!")
    await state.clear()

@dp.message(AddAgent.waiting_for_photo)
async def wrong_add_agent_message(message: Message, state: FSMContext):
    await message.answer("❌ Пожалуйста, отправьте фото с подписью. Для отмены /cancel")

@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("❌ Нет активного действия")
        return
    await state.clear()
    await message.answer("✅ Действие отменено")

# ================== КОМАНДЫ ПОЛЬЗОВАТЕЛЕЙ ==================
@dp.message(CommandStart())
async def start_command(message: Message):
    get_user(message.from_user.id, message.from_user)
    text = (
        "📡 <b>Добро пожаловать в Inter-Knot, Прокси!</b>\n\n"
        "<blockquote>Здесь ты можешь исследовать Холлоу, находить новых агентов и повышать свою репутацию.</blockquote>\n\n"
        "<b>🔍 Как провести Signal Search?</b>\n"
        "<blockquote>Отправь в чат одно из слов:\n"
        "• агент\n"
        "• signal\n"
        "• search\n"
        "• дай агента\n"
        "• хочу агента\n"
        "• новый агент\n"
        "• резонанс\n"
        "• proxy\n"
        "• agent</blockquote>"
    )
    await message.answer(text, reply_markup=main_keyboard())

@dp.message(Command("profile"))
async def profile_command(message: Message):
    user = get_user(message.from_user.id, message.from_user)
    name = html.escape(get_user_display_name(user, message.from_user.id, message.from_user))
    main_info = "Не назначен"
    if user["main_agent"]:
        ag = next((a for a in agents_data if a["id"] == user["main_agent"]), None)
        if ag:
            main_info = f'{ag["rank"]} "{html.escape(ag["name"])}"'
    unique = get_user_unique_agents_count(user["agents"])
    profile = (
        f"🌐 <b>Профиль Прокси — {name}</b>\n\n"
        f"🆔 Proxy ID • {message.from_user.id}\n"
        f"🧬 Агенты • {unique} из {TOTAL_AGENTS}\n"
        f"🌐 Репутация • {user['reputation']:,}\n"
        f"💳 Денни • {user['denny']}\n"
        f"🏅 Ранг • {user['proxy_rank']}\n"
        f"🎯 Выходы в Холлоу • {user.get('supply_drops', 0)}\n"
        f"⚡ Основной агент • {main_info}"
    )
    if has_vip_contract(message.from_user.id):
        until = datetime.fromtimestamp(user["vip_until"])
        days_left = (until - datetime.now()).days
        profile += f"\n💠 VIP Контракт • активен (осталось {days_left} дн.)"
    else:
        profile += "\n\n<blockquote>💠 Активируйте VIP Контракт для эксклюзивных преимуществ.</blockquote>"
    if user["proxy_rank"] == "Фаэтон":
        profile += "\n🔥 Статус: Высший уровень допуска Inter-Knot"
    extra = user.get("extra_runs", 0)
    if extra > 0:
        profile += f"\n➕ Доп. выходы • {extra}"
    await message.answer(profile, reply_markup=profile_keyboard())

@dp.message(Command("help"))
async def help_command(message: Message):
    text = (
        "📘 <b>Справка Inter-Knot</b>\n\n"
        "👤 /profile — ваш профиль\n"
        "📡 /search — провести Signal Search (получить агента)\n"
        "🌐 /rating — топ Прокси\n"
        "💠 /vip — VIP Контракт\n"
        "🎁 /supply — Supply Drop (бонус за подписку)\n"
        "🎫 /promo [код] — активировать промокод\n\n"
        "<b>🔍 Signal Search:</b>\n"
        "<blockquote>агент, signal, search, дай агента, хочу агента, новый агент, резонанс, proxy, agent</blockquote>"
    )
    await message.answer(text)

@dp.message(Command("search"))
async def search_command(message: Message):
    await give_random_agent(message)

@dp.message(Command("supply"))
async def supply_command(message: Message):
    user = get_user(message.from_user.id, message.from_user)
    now = time.time()
    if now - user["last_supply_drop"] < 43200:
        wait = 43200 - (now - user["last_supply_drop"])
        h = int(wait // 3600)
        m = int((wait % 3600) // 60)
        await message.answer(f"⏳ <b>Следующий Supply Drop через</b>\n<blockquote>{h}ч {m}м</blockquote>")
        return
    subscribed = await check_channel_subscription(message.from_user.id)
    if not subscribed:
        await message.answer(
            "🎁 <b>Supply Drop</b>\n\n"
            f"<blockquote>Чтобы получить припасы, нужно:\n1. Подписаться на канал {CHANNEL_USERNAME}\n2. Нажать «🎁 Supply Drop»</blockquote>",
            reply_markup=supply_keyboard()
        )
    else:
        bonus = random.randint(15, 30)
        if has_vip_contract(message.from_user.id):
            bonus = int(bonus * 1.5)
        update_user(
            message.from_user.id,
            denny=user["denny"] + bonus,
            last_supply_drop=now,
            last_search=0,
            supply_drops=user.get("supply_drops", 0) + 1,
            had_supply_drop=True,
            notified_unsubscribed=False
        )
        await message.answer(
            f"🎉 <b>Supply Drop получен!</b>\n\n"
            f"<blockquote>Вы получили <b>+{bonus} Денни</b>\n"
            f"💫 Теперь можно провести Signal Search без ожидания.</blockquote>"
        )

@dp.message(Command("rating"))
async def rating_command(message: Message):
    top = await get_top_proxies_text(15)
    await message.answer(top)

@dp.message(Command("vip"))
async def vip_command(message: Message):
    user = get_user(message.from_user.id, message.from_user)
    text = (
        "💠 <b>VIP Контракт Inter-Knot</b>\n\n"
        "<blockquote>30 дней VIP — 10 Stars</blockquote>\n\n"
        "⚡ <b>Преимущества:</b>\n"
        "<blockquote>• Уменьшенное время между Signal Search (3ч вместо 4ч)\n"
        "• +30% Денни за Supply Drop\n"
        "• +20% репутации за агентов\n"
        "• Повышенный шанс на агентов Rank S и выше\n"
        "• Значок 💠 в профиле и топе</blockquote>"
    )
    if has_vip_contract(message.from_user.id):
        until = datetime.fromtimestamp(user["vip_until"])
        days = (until - datetime.now()).days
        text += f"\n\n✅ <b>VIP активен! Осталось {days} дней</b>"
    await message.answer(text, reply_markup=vip_keyboard())

@dp.message(Command("promo"))
async def promo_command(message: Message):
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /promo [код]")
        return
    code = args[1].strip().lower()
    ok, msg = use_promocode(code, message.from_user.id, message)
    if ok:
        user = get_user(message.from_user.id)
        if "Денни" in msg:
            msg += f"\n\n💳 Теперь у вас: {user['denny']} Денни"
        elif "репутации" in msg:
            msg += f"\n\n🌐 Теперь у вас: {user['reputation']:,} репутации"
        elif "VIP" in msg:
            until = datetime.fromtimestamp(user['vip_until'])
            days = (until - datetime.now()).days
            msg += f"\n\n💠 VIP до {until.strftime('%d.%m.%Y')} ({days} дн.)"
        elif "агент" in msg and "случайный" not in msg:
            unique = get_user_unique_agents_count(user['agents'])
            msg += f"\n\n🧬 Уникальных агентов: {unique}"
        await message.answer(msg)
    else:
        await message.answer(msg)

# ================== ОСНОВНОЙ АГЕНТ ==================
@rt.callback_query(F.data == "choose_main_agent")
async def choose_main_agent(callback: CallbackQuery):
    try:
        user = get_user(callback.from_user.id, callback.from_user)
        if not user["agents"]:
            await callback.answer("У вас нет агентов для выбора", show_alert=True)
            return
        unique = list(set(user["agents"]))[:20]
        kb = []
        rank_emojis = {"Rank A":"⚪","Rank A+":"🔵","Rank S":"🟣","Rank S+":"🟡","🔥 Rank S++":"🔴"}
        for aid in unique:
            agent = next((a for a in agents_data if a["id"] == aid), None)
            if agent:
                emoji = rank_emojis.get(agent["rank"], "⚪")
                txt = f"{emoji} {agent['name']}"
                if len(txt) > 30: txt = txt[:27]+"..."
                kb.append([InlineKeyboardButton(text=txt, callback_data=f"main_{aid}")])
        kb.append([InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_profile")])
        await callback.message.edit_text(
            "⚡ <b>Назначьте основного агента</b>\n\n"
            "<blockquote>Этот агент будет отображаться в вашем профиле.</blockquote>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
        )
        await callback.answer()
    except Exception as e:
        await callback.answer("❌ Ошибка", show_alert=True)
        print(e)

@rt.callback_query(F.data.startswith("main_"))
async def set_main_agent(callback: CallbackQuery):
    try:
        aid = int(callback.data.split("_")[1])
        user = get_user(callback.from_user.id, callback.from_user)
        if aid not in user["agents"]:
            await callback.answer("❌ У вас нет этого агента", show_alert=True)
            return
        agent = next((a for a in agents_data if a["id"] == aid), None)
        if not agent:
            await callback.answer("❌ Агент не найден", show_alert=True)
            return
        update_user(callback.from_user.id, main_agent=aid)
        back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 К профилю", callback_data="back_to_profile")]])
        try:
            file = FSInputFile(agent["image"])
            cap = f'⚡ <b>Основной агент назначен!</b>\n\n<blockquote>"{html.escape(agent["name"])}"</blockquote>\n🏅 Ранг: {agent["rank"]}'
            ext = agent.get("file_extension","")
            if ext == ".gif":
                await callback.message.answer_animation(animation=file, caption=cap, reply_markup=back_kb)
            else:
                await callback.message.answer_photo(photo=file, caption=cap, reply_markup=back_kb)
            await callback.message.delete()
        except Exception:
            await callback.message.edit_text(
                f'⚡ <b>Основной агент назначен!</b>\n\n<blockquote>"{html.escape(agent["name"])}"</blockquote>\n🏅 Ранг: {agent["rank"]}',
                reply_markup=back_kb
            )
        await callback.answer()
    except Exception as e:
        await callback.answer("❌ Ошибка", show_alert=True)
        print(e)

# ================== АРХИВ АГЕНТОВ ==================
@rt.callback_query(F.data == "my_agents")
async def show_my_agents(callback: CallbackQuery):
    try:
        user = get_user(callback.from_user.id, callback.from_user)
        if not user["agents"]:
            await callback.message.edit_text(
                "🧬 <b>Архив агентов пуст.</b>\n\n"
                "<blockquote>Проведите Signal Search, чтобы найти первого агента.</blockquote>",
                reply_markup=back_to_profile_keyboard()
            )
            return
        unique = get_user_unique_agents_count(user["agents"])
        total = len(user["agents"])
        main_txt = ""
        if user["main_agent"]:
            ma = next((a for a in agents_data if a["id"] == user["main_agent"]), None)
            if ma:
                main_txt = f"\n⚡ <b>Основной:</b> {html.escape(ma['name'])}"
        text = (
            f"🧬 <b>Архив агентов</b>{main_txt}\n\n"
            f"✨ <b>Уникальные:</b> {unique} из {TOTAL_AGENTS}\n"
            f"📦 <b>Всего агентов:</b> {total}\n"
            f"📈 <b>Собрано:</b> {unique/TOTAL_AGENTS*100:.1f}%\n\n"
            f"<i>Выберите агента для просмотра:</i>"
        )
        await callback.message.edit_text(text, reply_markup=get_agents_pagination_keyboard(user["agents"], 0))
        await callback.answer()
    except Exception as e:
        await callback.answer("❌ Ошибка", show_alert=True)
        print(e)

@rt.callback_query(F.data.startswith("agents_page_"))
async def agents_pagination(callback: CallbackQuery):
    try:
        page = int(callback.data.split("_")[2])
        user = get_user(callback.from_user.id, callback.from_user)
        unique = get_user_unique_agents_count(user["agents"])
        total = len(user["agents"])
        main_txt = ""
        if user["main_agent"]:
            ma = next((a for a in agents_data if a["id"] == user["main_agent"]), None)
            if ma:
                main_txt = f"\n⚡ <b>Основной:</b> {html.escape(ma['name'])}"
        text = (
            f"🧬 <b>Архив агентов</b>{main_txt}\n\n"
            f"✨ <b>Уникальные:</b> {unique} из {TOTAL_AGENTS}\n"
            f"📦 <b>Всего агентов:</b> {total}\n"
            f"📈 <b>Собрано:</b> {unique/TOTAL_AGENTS*100:.1f}%\n\n"
            f"<i>Выберите агента для просмотра:</i>"
        )
        await callback.message.edit_text(text, reply_markup=get_agents_pagination_keyboard(user["agents"], page))
        await callback.answer()
    except Exception as e:
        await callback.answer("❌ Ошибка", show_alert=True)
        print(e)

@rt.callback_query(F.data.startswith("view_agent_"))
async def view_agent_details(callback: CallbackQuery):
    try:
        aid = int(callback.data.split("_")[2])
        user = get_user(callback.from_user.id, callback.from_user)
        agent = next((a for a in agents_data if a["id"] == aid), None)
        if not agent or aid not in user["agents"]:
            await callback.answer("❌ Агент не найден", show_alert=True)
            return
        dup = user["agents"].count(aid) - 1
        if dup < 0: dup = 0
        kb = []
        if user["main_agent"] != aid:
            kb.append([InlineKeyboardButton(text="⚡ Назначить основным", callback_data=f"main_{aid}")])
        kb.append([InlineKeyboardButton(text="🔙 К архиву", callback_data="my_agents")])
        try:
            file = FSInputFile(agent["image"])
            cap = (
                f"🧬 <b>Детали агента</b>\n\n"
                f"<blockquote>🧬 <b>{html.escape(agent['name'])}</b>\n"
                f"🏅 Ранг: <b>{agent['rank']}</b>\n"
                f"🎯 ID: <b>{aid}</b>\n"
                f"🔁 Резонансов: <b>{dup}</b></blockquote>\n\n"
                f"💎 <b>Базовая награда:</b>\n"
                f"<blockquote>🌐 Репутация: {RANK_REPUTATION[agent['rank']]:,}\n"
                f"💳 Денни: {RANK_DENNY[agent['rank']]}</blockquote>"
            )
            ext = agent.get("file_extension","").lower()
            if ext == ".gif":
                await callback.message.answer_animation(animation=file, caption=cap, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
            else:
                await callback.message.answer_photo(photo=file, caption=cap, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
            await callback.message.delete()
        except Exception:
            await callback.message.edit_text(
                f"🧬 <b>Детали агента</b>\n\n"
                f"<blockquote>🧬 <b>{html.escape(agent['name'])}</b>\n"
                f"🏅 Ранг: <b>{agent['rank']}</b>\n"
                f"🎯 ID: <b>{aid}</b>\n"
                f"🔁 Резонансов: <b>{dup}</b></blockquote>\n\n"
                f"💎 <b>Базовая награда:</b>\n"
                f"<blockquote>🌐 Репутация: {RANK_REPUTATION[agent['rank']]:,}\n"
                f"💳 Денни: {RANK_DENNY[agent['rank']]}</blockquote>\n\n⚠️ Изображение недоступно",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
            )
        await callback.answer()
    except Exception as e:
        await callback.answer("❌ Ошибка", show_alert=True)
        print(e)

# ================== SUPPLY DROP ==================
@rt.callback_query(F.data == "get_supply_drop")
async def supply_drop_callback(callback: CallbackQuery):
    try:
        user = get_user(callback.from_user.id, callback.from_user)
        now = time.time()
        if now - user["last_supply_drop"] < 43200:
            wait = 43200 - (now - user["last_supply_drop"])
            h = int(wait // 3600)
            m = int((wait % 3600) // 60)
            await callback.message.answer(f"⏳ <b>Следующий Supply Drop через</b>\n<blockquote>{h}ч {m}м</blockquote>")
            await callback.answer()
            return
        sub = await check_channel_subscription(callback.from_user.id)
        if not sub:
            await callback.message.answer(
                "🎁 <b>Supply Drop</b>\n\n"
                f"<blockquote>Чтобы получить припасы, нужно:\n1. Подписаться на канал {CHANNEL_USERNAME}\n2. Нажать «🎁 Supply Drop»</blockquote>",
                reply_markup=supply_keyboard()
            )
        else:
            bonus = random.randint(15, 30)
            if has_vip_contract(callback.from_user.id):
                bonus = int(bonus * 1.5)
            update_user(
                callback.from_user.id,
                denny=user["denny"] + bonus,
                last_supply_drop=now,
                last_search=0,
                supply_drops=user.get("supply_drops", 0) + 1,
                had_supply_drop=True,
                notified_unsubscribed=False
            )
            await callback.message.answer(
                f"🎉 <b>Supply Drop получен!</b>\n\n"
                f"<blockquote>Вы получили <b>+{bonus} Денни</b>\n"
                f"💫 Теперь можно провести Signal Search без ожидания.</blockquote>"
            )
        await callback.answer()
    except Exception as e:
        await callback.answer("❌ Ошибка", show_alert=True)
        print(e)

@rt.callback_query(F.data == "back_to_profile")
async def back_to_profile(callback: CallbackQuery):
    try:
        user = get_user(callback.from_user.id, callback.from_user)
        name = html.escape(get_user_display_name(user, callback.from_user.id, callback.from_user))
        main_info = "Не назначен"
        if user["main_agent"]:
            ag = next((a for a in agents_data if a["id"] == user["main_agent"]), None)
            if ag:
                main_info = f'{ag["rank"]} "{html.escape(ag["name"])}"'
        unique = get_user_unique_agents_count(user["agents"])
        profile = (
            f"🌐 <b>Профиль Прокси — {name}</b>\n\n"
            f"🆔 Proxy ID • {callback.from_user.id}\n"
            f"🧬 Агенты • {unique} из {TOTAL_AGENTS}\n"
            f"🌐 Репутация • {user['reputation']:,}\n"
            f"💳 Денни • {user['denny']}\n"
            f"🏅 Ранг • {user['proxy_rank']}\n"
            f"🎯 Выходы в Холлоу • {user.get('supply_drops', 0)}\n"
            f"⚡ Основной агент • {main_info}"
        )
        if has_vip_contract(callback.from_user.id):
            until = datetime.fromtimestamp(user["vip_until"])
            days_left = (until - datetime.now()).days
            profile += f"\n💠 VIP Контракт • активен (осталось {days_left} дн.)"
        else:
            profile += "\n\n<blockquote>💠 Активируйте VIP Контракт для эксклюзивных преимуществ.</blockquote>"
        if user["proxy_rank"] == "Фаэтон":
            profile += "\n🔥 Статус: Высший уровень допуска Inter-Knot"
        extra = user.get("extra_runs", 0)
        if extra > 0:
            profile += f"\n➕ Доп. выходы • {extra}"
        try:
            await callback.message.edit_text(profile, reply_markup=profile_keyboard())
        except Exception:
            await callback.message.answer(profile, reply_markup=profile_keyboard())
            await callback.message.delete()
        await callback.answer()
    except Exception as e:
        await callback.answer("❌ Ошибка", show_alert=True)
        print(e)

@rt.callback_query(F.data == "buy_vip_stars")
async def buy_vip_stars(callback: CallbackQuery):
    try:
        if has_vip_contract(callback.from_user.id):
            await callback.answer("❌ VIP Контракт уже активен", show_alert=True)
            return
        prices = [LabeledPrice(label="VIP Контракт 30 дней", amount=10)]
        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title="VIP Контракт Inter-Knot",
            description="VIP Контракт на 30 дней",
            payload=f"vip_30_{callback.from_user.id}",
            provider_token="",
            currency="XTR",
            prices=prices,
            start_parameter="vip"
        )
        await callback.answer()
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

@rt.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@rt.message(F.successful_payment)
async def successful_payment(message: Message):
    payment = message.successful_payment
    user = get_user(message.from_user.id, message.from_user)
    stars = payment.total_amount // 100
    if payment.invoice_payload.startswith("vip"):
        vip_until = datetime.now() + timedelta(days=30)
        update_user(
            message.from_user.id,
            vip_contract=True,
            vip_until=vip_until.timestamp(),
            total_stars_spent=user.get("total_stars_spent", 0) + stars,
            is_vip_sponsor=True
        )
        save_donation(message.from_user.id, message.from_user.username or message.from_user.first_name, stars, "vip_contract")
        await message.answer(
            f"🎉 <b>VIP Контракт активирован!</b>\n\n"
            f"<blockquote>Спасибо за поддержку! VIP активен до {vip_until.strftime('%d.%m.%Y')}</blockquote>"
        )
        await message.answer_sticker("CAACAgIAAxkBAAECfbZppWxk0C5WNKTgZQt8QwOmWSQpoAACRXQAAnXJKEowmdZubcrOTzoE")
    elif payment.invoice_payload.startswith("donate"):
        update_user(
            message.from_user.id,
            total_stars_spent=user.get("total_stars_spent", 0) + stars,
            is_vip_sponsor=True if stars >= 10 else user.get("is_vip_sponsor", False)
        )
        save_donation(message.from_user.id, message.from_user.username or message.from_user.first_name, stars, "donation")
        await message.answer(f"❤️ <b>Спасибо за поддержку!</b>\n\n<blockquote>Вы поддержали бота на {stars} Stars</blockquote>")

# ================== SIGNAL SEARCH TRIGGERS ==================
SIGNAL_TRIGGERS = [
    "агент", "signal", "search", "дай агента", "хочу агента", 
    "новый агент", "резонанс", "proxy", "agent", "сигнал", "поиск"
]

async def give_random_agent(message: Message):
    user = get_user(message.from_user.id, message.from_user)
    now = time.time()
    cooldown = 10800 if has_vip_contract(message.from_user.id) else 14400  # 3ч vs 4ч
    extra = user.get("extra_runs", 0) > 0
    if now - user["last_search"] < cooldown and not extra:
        remaining = cooldown - (now - user["last_search"])
        h = int(remaining // 3600)
        m = int((remaining % 3600) // 60)
        await message.answer(f"⏳ <b>Signal Search пока недоступен</b>\n\n<blockquote>Подождите ещё {h}ч {m}м</blockquote>")
        return
    if extra:
        update_user(message.from_user.id, extra_runs=user.get("extra_runs", 0) - 1)
        await process_agent_drop_balanced(message, update_timer=False)
    else:
        update_user(message.from_user.id, last_search=now)
        await process_agent_drop_balanced(message, update_timer=True)

@rt.message(F.text.lower().in_(SIGNAL_TRIGGERS))
async def handle_signal_message(message: Message):
    await give_random_agent(message)

@rt.callback_query()
async def unknown_callback(callback: CallbackQuery):
    await callback.answer("❌ Неизвестная команда", show_alert=True)

# ================== ЗАПУСК ==================
async def run_bot():
    print("📡 Inter-Knot Proxy Terminal запущен!")
    await send_emergency_update_notification()
    fix_broken_promocodes()
    init_promocodes()
    users = load_data(USERS_FILE, {})
    migrated = 0
    for uid, ud in users.items():
        if "vip_contract" not in ud:
            users[uid] = migrate_user_data(ud)
            migrated += 1
    if migrated:
        save_data(USERS_FILE, users)
        print(f"🔧 Мигрировано Прокси: {migrated}")
    updated = await update_user_names_automatically()
    if updated:
        print(f"✅ Автообновлено имён: {updated}")
    asyncio.create_task(check_subscriptions_periodically())
    asyncio.create_task(check_new_agents_periodically())
    await dp.start_polling(bot)

async def main():
    await run_bot()

if __name__ == "__main__":
    asyncio.run(main())