import aiosqlite
import os

DB_PATH = 'database/store_bot.db'

async def init_db():
    if not os.path.exists('database'):
        os.makedirs('database')
        
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS autoresponder (
                trigger_word TEXT PRIMARY KEY,
                response_text TEXT,
                image_url TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                admin_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS bump_config (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                role_id INTEGER
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS auction_config (
                guild_id INTEGER PRIMARY KEY,
                bid_channel_id INTEGER,
                rules_channel_id INTEGER,
                admin_role_id INTEGER,
                mod_role_id INTEGER
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS auctions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                message_id INTEGER,
                title TEXT NOT NULL,
                details TEXT,
                starting_price REAL NOT NULL,
                min_raise REAL NOT NULL,
                inr_rate REAL NOT NULL,
                end_time DATETIME NOT NULL,
                status TEXT DEFAULT 'Active'
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS bids (
                auction_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                amount_usd REAL NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (auction_id) REFERENCES auctions (id)
            )
        ''')
        await db.commit()

async def add_autoresponder(trigger: str, response_text: str | None = None, image_url: str | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT OR REPLACE INTO autoresponder (trigger_word, response_text, image_url)
            VALUES (?, ?, ?)
        ''', (trigger, response_text, image_url))
        await db.commit()

async def get_autoresponder(trigger: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT response_text, image_url FROM autoresponder WHERE trigger_word = ?', (trigger,)) as cursor:
            return await cursor.fetchone()

async def delete_autoresponder(trigger: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM autoresponder WHERE trigger_word = ?', (trigger,))
        await db.commit()

async def get_all_autoresponders():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT trigger_word FROM autoresponder') as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

# --- Warning Functions ---
async def add_warning(user_id: int, guild_id: int, admin_id: int, reason: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO warnings (user_id, guild_id, admin_id, reason)
            VALUES (?, ?, ?, ?)
        ''', (user_id, guild_id, admin_id, reason))
        await db.commit()

async def get_user_warnings(user_id: int, guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('''
            SELECT admin_id, reason, timestamp FROM warnings 
            ''', (user_id, guild_id)) as cursor:
            return await cursor.fetchall()

# --- Bump Config Functions ---
async def get_bump_config(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT channel_id, role_id FROM bump_config WHERE guild_id = ?', (guild_id,)) as cursor:
            return await cursor.fetchone()

async def set_bump_config(guild_id: int, channel_id: int | None = None, role_id: int | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT channel_id, role_id FROM bump_config WHERE guild_id = ?', (guild_id,)) as cursor:
            row = await cursor.fetchone()
        
        if row:
            new_chan = channel_id if channel_id is not None else row[0]
            new_role = role_id if role_id is not None else row[1]
            await db.execute('UPDATE bump_config SET channel_id = ?, role_id = ? WHERE guild_id = ?', (new_chan, new_role, guild_id))
        else:
            await db.execute('INSERT INTO bump_config (guild_id, channel_id, role_id) VALUES (?, ?, ?)', (guild_id, channel_id, role_id))
        await db.commit()

# --- Auction Functions ---
async def get_auction_config(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT bid_channel_id, rules_channel_id, admin_role_id, mod_role_id FROM auction_config WHERE guild_id = ?', (guild_id,)) as cursor:
            return await cursor.fetchone()

async def set_auction_config(guild_id: int, bid_channel_id: int, rules_channel_id: int | None, admin_role_id: int, mod_role_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT OR REPLACE INTO auction_config (guild_id, bid_channel_id, rules_channel_id, admin_role_id, mod_role_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (guild_id, bid_channel_id, rules_channel_id, admin_role_id, mod_role_id))
        await db.commit()

async def create_auction(guild_id: int, title: str, details: str, starting_price: float, min_raise: float, inr_rate: float, end_time):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('''
            INSERT INTO auctions (guild_id, title, details, starting_price, min_raise, inr_rate, end_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (guild_id, title, details, starting_price, min_raise, inr_rate, end_time))
        auction_id = cursor.lastrowid
        await db.commit()
        return auction_id

async def set_auction_message(auction_id: int, message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE auctions SET message_id = ? WHERE id = ?', (message_id, auction_id))
        await db.commit()

async def get_auction_by_channel(guild_id: int):
    # For now, we assume one active auction per guild in the bidding channel
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT id, message_id, title, starting_price, min_raise, inr_rate, end_time FROM auctions WHERE guild_id = ? AND status = "Active"', (guild_id,)) as cursor:
            return await cursor.fetchone()

async def add_bid(auction_id: int, user_id: int, amount_usd: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT INTO bids (auction_id, user_id, amount_usd) VALUES (?, ?, ?)', (auction_id, user_id, amount_usd))
        await db.commit()

async def get_highest_bid(auction_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT user_id, amount_usd FROM bids WHERE auction_id = ? ORDER BY amount_usd DESC LIMIT 1', (auction_id,)) as cursor:
            return await cursor.fetchone()

async def end_auction(auction_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE auctions SET status = "Ended" WHERE id = ?', (auction_id,))
        await db.commit()

async def increase_auction_deadline(auction_id: int, new_end_time):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE auctions SET end_time = ? WHERE id = ?', (new_end_time, auction_id))
        await db.commit()

async def get_all_active_auctions():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT id, guild_id, message_id, end_time FROM auctions WHERE status = "Active"') as cursor:
            return await cursor.fetchall()
