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
