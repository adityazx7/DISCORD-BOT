import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
from playwright.async_api import async_playwright
from database import db_handler
import re

SELLERS = [
    "MuZiJin",
    "asd28202659",
    "week1997"
]

def apply_markup(real_price: float) -> float:
    if 1.0 <= real_price <= 1.99:
        return real_price + 0.50
    elif 2.0 <= real_price <= 3.99:
        return real_price + 1.00
    elif 4.0 <= real_price <= 9.99:
        return real_price + 2.00
    elif 10.0 <= real_price <= 19.99:
        return real_price + 3.00
    elif 20.0 <= real_price <= 39.99:
        return real_price + 4.00
    else:
        # Fallback for prices outside the specified ranges
        return real_price

class G2GScraperCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.scraper_task.start()

    def cog_unload(self):
        self.scraper_task.cancel()

    @app_commands.command(name="g2g_setup", description="Admin only: Set channels for G2G stock updates")
    @app_commands.describe(
        public_channel="Channel for marked-up public stock postings",
        admin_channel="Channel for real prices and direct supplier links"
    )
    @app_commands.default_permissions(administrator=True)
    async def g2g_setup(self, interaction: discord.Interaction, public_channel: discord.TextChannel, admin_channel: discord.TextChannel):
        try:
            await db_handler.set_g2g_config(interaction.guild_id, public_channel.id, admin_channel.id)
            await interaction.response.send_message(
                f"✅ G2G Stock channels configured!\n**Public Output:** {public_channel.mention}\n**Admin Log:** {admin_channel.mention}",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to configure G2G scraper: {e}", ephemeral=True)

    @app_commands.command(name="g2g_force", description="Admin only: Force run the G2G stock scraper")
    @app_commands.default_permissions(administrator=True)
    async def g2g_force(self, interaction: discord.Interaction):
        await interaction.response.send_message("🔍 Starting forced G2G scrape in the background...", ephemeral=True)
        print(f"DEBUG: /g2g_force triggered by {interaction.user}")
        
        # Run it asynchronously but catch errors
        async def run_and_catch():
            try:
                await self.scrape_g2g(interaction.guild)
            except Exception as e:
                print(f"DEBUG: Error inside forced scrape task: {e}")
                
        asyncio.create_task(run_and_catch())

    @tasks.loop(hours=1.0)
    async def scraper_task(self):
        # We need to run this for all configured guilds.
        # Since it's a simple bot right now, we will just iterate over all guilds the bot is in.
        for guild in self.bot.guilds:
            await self.scrape_g2g(guild)

    @scraper_task.before_loop
    async def before_scraper(self):
        await self.bot.wait_until_ready()

    async def scrape_g2g(self, guild: discord.Guild):
        print(f"DEBUG: scrape_g2g called for guild {guild.name}")
        config = await db_handler.get_g2g_config(guild.id)
        
        print(f"DEBUG: Config result for {guild.id}: {config}")
        if not config or not config[0] or not config[1]:
            print("DEBUG: Scraping aborted. Channels not configured in database.")
            return

        public_channel = guild.get_channel(config[0])
        admin_channel = guild.get_channel(config[1])

        print(f"DEBUG: Public Channel Object: {public_channel}")
        print(f"DEBUG: Admin Channel Object: {admin_channel}")

        if not public_channel or not admin_channel:
            print("DEBUG: Scraping aborted. Could not resolve discord.TextChannel objects from IDs.")
            return

        print(f"[{guild.name}] Generating G2G Scraper Session...")
        
        try:
            # Connect to playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
                page = await context.new_page()

                offers_found = []

                async def handle_response(response):
                    # Intercept the exact API call G2G makes to load offers
                    if "sls.g2g.com/offer/search" in response.url and response.status == 200:
                        try:
                            data = await response.json()
                            if "payload" in data and "results" in data["payload"]:
                                results = data["payload"]["results"]
                                offers_found.extend(results)
                        except Exception as e:
                            print(f"Failed to parse JSON response: {e}")

                page.on("response", handle_response)

                for seller in SELLERS:
                    try:
                        url = f"https://www.g2g.com/{seller}"
                        # Go to seller page, which triggers the SPA to fetch the API
                        await page.goto(url, wait_until="networkidle", timeout=30000)
                        # Wait an extra few seconds to ensure background API calls finish
                        await page.wait_for_timeout(3000)
                    except Exception as e:
                        print(f"Error loading seller {seller}: {e}")

                await browser.close()
                
                # Process the captured offers
                for offer in offers_found:
                    offer_id = offer.get("offer_id")
                    
                    if not offer_id:
                        continue
                        
                    # 1. Check if already scraped
                    if await db_handler.is_offer_scraped(offer_id):
                        continue
                        
                    # 2. Extract Details
                    title = offer.get("title", "Unknown Account")
                    
                    # Remove "Automatic delivery" from the title as requested
                    clean_title = re.sub(r"(?i)\s*\[?automatic delivery\]?\s*", "", title).strip()
                    
                    # Ensure it's for the right game (One Piece Bounty Rush) if needed, 
                    # but since it's from specific sellers, we assume it's correct context.
                    seller_name = offer.get("seller_name", "Unknown Seller")
                    raw_price_str = offer.get("display_price", "0")
                    currency = offer.get("currency", "USD")
                    
                    try:
                        real_price = float(raw_price_str)
                    except ValueError:
                        continue # Skip if price is unreadable
                        
                    # 3. Apply Markup Conditions
                    marked_up_price = apply_markup(real_price)
                    
                    # 4. Generate Embeds
                    direct_url = f"https://www.g2g.com/categories/one-piece-bounty-rush-account/offer/{offer_id}"

                    # Public Output (Only Clean Title & Marked Up Price)
                    public_embed = discord.Embed(
                        title=f"🛒 {clean_title}",
                        color=discord.Color.green()
                    )
                    public_embed.add_field(name="💰 Price", value=f"**${marked_up_price:.2f} {currency}**", inline=False)
                    
                    # Admin Logging Output (Real Price, Link, Seller, Raw Title)
                    admin_embed = discord.Embed(
                        title="🕵️ New G2G Stock Found",
                        color=discord.Color.gold()
                    )
                    admin_embed.add_field(name="Raw Title", value=title, inline=False)
                    admin_embed.add_field(name="Seller", value=seller_name, inline=True)
                    admin_embed.add_field(name="Real Price", value=f"${real_price:.2f} {currency}", inline=True)
                    admin_embed.add_field(name="Direct Link", value=f"[Click Here to View]({direct_url})", inline=False)

                    # 5. Send messages
                    await public_channel.send(embed=public_embed)
                    await admin_channel.send(embed=admin_embed)
                    
                    # 6. Mark as scraped in memory
                    await db_handler.add_scraped_offer(offer_id)
                    
                    # Optional: small delay to avoid ratelimiting Discord
                    await asyncio.sleep(1)

        except Exception as e:
            print(f"[{guild.name}] Critical Scraper Error: {e}")

async def setup(bot):
    await bot.add_cog(G2GScraperCog(bot))
