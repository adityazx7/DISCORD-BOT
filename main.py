import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Setup Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class StoreBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )

    async def setup_hook(self):
        # Ensure cogs directory exists
        if not os.path.exists("./cogs"):
            os.makedirs("./cogs")
            
        # Load cogs dynamically
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py") and filename != "__init__.py":
                try:
                    await self.load_extension(f"cogs.{filename[:-3]}")
                    print(f"Loaded {filename}")
                except Exception as e:
                    print(f"Failed to load {filename}: {e}")

        # Syncing is now handled manually via the !sync command to prevent duplication issues
        # print("Syncing slash commands...")
        # await self.tree.sync()
        # print("Slash commands synced.")

bot = StoreBot()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

@bot.command()
@commands.has_permissions(administrator=True)
async def sync(ctx: commands.Context, guilds: commands.Greedy[discord.Object], spec: str = None) -> None:
    """Syncs the slash commands array to the current guild.
    Usage:
      !sync -> global sync
      !sync ~ -> sync current guild
      !sync * -> copies all global app commands to current guild and syncs
      !sync ^ -> clears all commands from the current guild target and syncs
    """
    if not guilds:
        if spec == "~":
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "*":
            ctx.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "^":
            ctx.bot.tree.clear_commands(guild=ctx.guild)
            await ctx.bot.tree.sync(guild=ctx.guild)
            await ctx.send("🧹 **Cleared all slash commands from this guild.** (They may take a moment to disappear from your menu)")
            return
        else:
            synced = await ctx.bot.tree.sync()

        await ctx.send(
            f"✅ Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild.'}"
        )
        return

    ret = 0
    for guild in guilds:
        try:
            await ctx.bot.tree.sync(guild=guild)
        except discord.HTTPException:
            pass
        else:
            ret += 1

    await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.")

if __name__ == "__main__":
    from database import db_handler
    import asyncio
    
    # Initialize the database
    asyncio.run(db_handler.init_db())
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("Error: DISCORD_TOKEN is not set in the .env file.")
