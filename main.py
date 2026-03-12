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

    async def reload_cogs(self):
        """Helper to reload all extensions from the cogs folder."""
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py") and filename != "__init__.py":
                try:
                    await self.reload_extension(f"cogs.{filename[:-3]}")
                except commands.ExtensionNotLoaded:
                    await self.load_extension(f"cogs.{filename[:-3]}")
                except Exception as e:
                    print(f"Failed to reload {filename}: {e}")

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
    """
    Syncs the slash commands array.
    
    HOW TO FIX DUPLICATE COMMANDS:
    1. !sync ^   (Clears all commands from this guild)
    2. !sync ~   (Registers them to ONLY this guild - instant & no duplicates)
    
    Flags:
      !sync      -> Global sync (Can take 1 hour, use only for final release)
      !sync ~    -> Current guild sync (Instant, best for your server)
      !sync *    -> Copies global to guild (Causes duplicates! Avoid this)
      !sync ^    -> Clears guild commands (Use this to fix duplicates)
      !sync !!   -> Clears GLOBAL commands (Fixes duplicates permanently)
    """
    if not guilds:
        if spec == "~":
            ctx.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "*":
            ctx.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "!!":
            ctx.bot.tree.clear_commands(guild=None)
            await ctx.bot.tree.sync()
            await ctx.bot.reload_cogs() # Put them back in memory so they aren't lost
            await ctx.send("🌐 **GLOBAL commands cleared from Discord.**\n⚠️ **Note**: These will still show in your menu for up to 1 hour because of Discord's cache.\n✅ **Bot memory reloaded**: You can now run `!sync ~` to keep your guild commands active.")
            return
        else:
            synced = await ctx.bot.tree.sync()

        await ctx.send(
            f"✅ Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild.'}\n"
            f"{'🕒 *Note: Global changes can take 1 hour to appear/disappear.*' if spec is None or spec == '!!' else '⚡ *Note: Guild sync is instant.*'}"
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
