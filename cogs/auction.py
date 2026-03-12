import discord
from discord.ext import commands, tasks
from discord import app_commands
from database import db_handler
import datetime
import re
import asyncio

class AuctionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auction_cleanup.start()

    def cog_unload(self):
        self.auction_cleanup.cancel()

    @tasks.loop(minutes=1.0)
    async def auction_cleanup(self):
        """Background task to check for ended auctions every minute."""
        active_auctions = await db_handler.get_all_active_auctions()
        now = datetime.datetime.now(datetime.timezone.utc)
        
        for auction_id, guild_id, message_id, end_time_str in active_auctions:
            # Database stores ISO format strings for datetime
            end_time = datetime.datetime.fromisoformat(end_time_str)
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=datetime.timezone.utc)
                
            if now >= end_time:
                await self.finalize_auction(auction_id, guild_id, message_id)

    async def finalize_auction(self, auction_id, guild_id, message_id):
        """Mark auction as ended and update the embed."""
        await db_handler.end_auction(auction_id)
        guild = self.bot.get_guild(guild_id)
        if not guild: return
        
        config = await db_handler.get_auction_config(guild_id)
        if not config: return
        
        bid_channel_id = config[0]
        channel = guild.get_channel(bid_channel_id)
        if not channel: return
        
        try:
            message = await channel.fetch_message(message_id)
            embed = message.embeds[0]
            embed.title = f"🔴 AUCTION ENDED: {embed.title.replace('🟢 ACTIVE AUCTION: ', '')}"
            embed.color = discord.Color.red()
            
            highest_bid = await db_handler.get_highest_bid(auction_id)
            if highest_bid:
                user_id, amount = highest_bid
                winner = guild.get_member(user_id)
                winner_mention = winner.mention if winner else f"User ID: {user_id}"
                embed.add_field(name="WINNER", value=f"{winner_mention} with a bid of **${amount:.2f}**", inline=False)
                await channel.send(content=f"🔨 **Auction Ended!** {winner_mention} won with **${amount:.2f}**!")
            else:
                embed.add_field(name="RESULT", value="No bids were placed.", inline=False)
                await channel.send(content="🔨 **Auction Ended!** No bids were placed.")
            
            await message.edit(embed=embed, view=None)
        except Exception as e:
            print(f"Error finalizing auction {auction_id}: {e}")

    @app_commands.command(name="auction-setup", description="Admin only: Configure auction channels and roles")
    @app_commands.describe(
        bid_channel="The channel where bidding happens (Required)",
        rules_channel="The channel where rules are posted (Optional)",
        admin_role="The role allowed to create auctions",
        mod_role="The role allowed to post in bidding channel"
    )
    @app_commands.default_permissions(administrator=True)
    async def auction_setup(self, interaction: discord.Interaction, bid_channel: discord.TextChannel, mod_role: discord.Role, admin_role: discord.Role, rules_channel: discord.TextChannel | None = None):
        try:
            rules_id = rules_channel.id if rules_channel else None
            await db_handler.set_auction_config(interaction.guild_id, bid_channel.id, rules_id, admin_role.id, mod_role.id)
            
            embed = discord.Embed(
                title="🔨 Auction System Configured",
                description="The auction system is ready to use!",
                color=discord.Color.blue()
            )
            embed.add_field(name="Bidding Channel", value=bid_channel.mention, inline=True)
            embed.add_field(name="Rules Channel", value=rules_channel.mention if rules_channel else "Not set", inline=True)
            embed.add_field(name="Admin Role", value=admin_role.mention, inline=True)
            embed.add_field(name="Mod Role", value=mod_role.mention, inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Post rules if channel provided
            if rules_channel:
                rules_embed = discord.Embed(
                    title="📜 Auction Rules",
                    description=(
                        "1. Only bid if you intend to pay.\n"
                        "2. Bids must use `$` or `₹` signs.\n"
                        "3. Anti-Snipe: Bids in last 5m extend the timer by 10m.\n"
                        "4. Respect the minimum raise requirement.\n"
                        "5. Failure to follow rules may result in a ban."
                    ),
                    color=discord.Color.gold()
                )
                await rules_channel.send(embed=rules_embed)
                
        except Exception as e:
            await interaction.response.send_message(f"❌ Setup failed: {e}", ephemeral=True)

    @app_commands.command(name="create-auction", description="Start a new auction")
    @app_commands.describe(
        title="Title of the auction",
        details="Details about the account",
        starting_price="Starting price in USD",
        min_raise="Minimum raise amount in USD",
        hours="Duration in hours",
        inr_rate="Conversion rate (1 USD = X INR)",
        image="Optional image of the account"
    )
    async def create_auction(self, interaction: discord.Interaction, title: str, details: str, starting_price: float, min_raise: float, hours: int, inr_rate: float, image: discord.Attachment | None = None):
        # Permission check
        config = await db_handler.get_auction_config(interaction.guild_id)
        if not config:
            await interaction.response.send_message("❌ Auction system is not set up. Use `/auction-setup` first.", ephemeral=True)
            return
            
        _, _, admin_role_id, _ = config
        member = interaction.user
        if not member.guild_permissions.administrator and not any(r.id == admin_role_id for r in member.roles):
            await interaction.response.send_message("❌ You don't have permission to start auctions.", ephemeral=True)
            return

        bid_channel_id = config[0]
        channel = interaction.guild.get_channel(bid_channel_id)
        if not channel:
            await interaction.response.send_message("❌ Bidding channel not found. Re-run setup.", ephemeral=True)
            return

        # Time calculation
        now = datetime.datetime.now(datetime.timezone.utc)
        end_time = now + datetime.timedelta(hours=hours)
        
        # Save to DB
        auction_id = await db_handler.create_auction(
            interaction.guild_id, title, details, starting_price, min_raise, inr_rate, end_time.isoformat()
        )
        
        # Create Embed
        embed = discord.Embed(
            title=f"🟢 ACTIVE AUCTION: {title}",
            description=details,
            color=discord.Color.green(),
            timestamp=end_time
        )
        embed.add_field(name="Starting Price", value=f"${starting_price:.2f}", inline=True)
        embed.add_field(name="Minimum Raise", value=f"${min_raise:.2f}", inline=True)
        embed.add_field(name="INR Rate", value=f"$1 = ₹{inr_rate:.2f}", inline=True)
        embed.add_field(name="Ends At", value=f"<t:{int(end_time.timestamp())}:F> (<t:{int(end_time.timestamp())}:R>)", inline=False)
        embed.add_field(name="Current Bid", value="None", inline=True)
        embed.add_field(name="High Bidder", value="None", inline=True)
        
        if image:
            embed.set_image(url=image.url)
            
        # Add buttons
        view = AuctionControlView(auction_id, self)
        msg = await channel.send(embed=embed, view=view)
        await db_handler.set_auction_message(auction_id, msg.id)
        
        await interaction.response.send_message(f"✅ Auction started in {channel.mention}!", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        config = await db_handler.get_auction_config(message.guild.id)
        if not config: return
        
        bid_channel_id, _, _, mod_role_id = config
        if message.channel.id != bid_channel_id:
            return

        # Admin/Mod bypass
        if message.author.guild_permissions.administrator or any(r.id == mod_role_id for r in message.author.roles):
            return

        # Member moderation: Check if it's a valid bid
        content = message.content.strip()
        
        # Regex to find $ or ₹ followed by number
        match = re.search(r'([$₹])\s?(\d+(\.\d+)?)', content)
        
        if not match:
            await message.delete()
            try:
                await message.author.send("❌ In the bidding channel, you can only post bids. Example: `$100` or `₹8000`. Plain numbers are not allowed.")
            except: pass
            return

        currency = match.group(1)
        amount = float(match.group(2))
        
        # Get active auction
        auction_data = await db_handler.get_auction_by_channel(message.guild.id)
        if not auction_data:
            await message.delete()
            return

        auction_id, msg_id, title, start_price, min_raise, inr_rate, end_time_str = auction_data
        
        # Convert to USD if needed
        bid_usd = amount
        if currency == '₹':
            bid_usd = amount / inr_rate
        
        # Validate bid amount
        highest_bid = await db_handler.get_highest_bid(auction_id)
        current_max = highest_bid[1] if highest_bid else start_price
        
        # If it's the first bid, it just needs to be >= start_price
        # If not, it needs for be >= current_max + min_raise
        required_bid = current_max + (min_raise if highest_bid else 0)
        
        if bid_usd < required_bid:
            await message.delete()
            try:
                await message.author.send(f"❌ Your bid of **${bid_usd:.2f}** is too low. The minimum bid required is **${required_bid:.2f}**.")
            except: pass
            return

        # VALID BID!
        # Delete the user message to keep channel clean
        await message.delete()
        
        # Save bid
        await db_handler.add_bid(auction_id, message.author.id, bid_usd)
        
        # Anti-Snipe: If bid in last 5m, extend 10m
        end_time = datetime.datetime.fromisoformat(end_time_str)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=datetime.timezone.utc)
            
        now = datetime.datetime.now(datetime.timezone.utc)
        time_left = (end_time - now).total_seconds()
        
        if 0 < time_left < 300: # 300s = 5m
            new_end_time = end_time + datetime.timedelta(minutes=10)
            await db_handler.increase_auction_deadline(auction_id, new_end_time.isoformat())
            end_time = new_end_time # For embed update
            
        # Update Auction Embed
        try:
            bid_channel = message.channel
            main_msg = await bid_channel.fetch_message(msg_id)
            embed = main_msg.embeds[0]
            
            # Update fields
            # Fields: 0:Starting, 1:MinRaise, 2:INR, 3:Ends, 4:CurrentBid, 5:HighBidder
            embed.set_field_at(3, name="Ends At", value=f"<t:{int(end_time.timestamp())}:F> (<t:{int(end_time.timestamp())}:R>)", inline=False)
            embed.set_field_at(4, name="Current Bid", value=f"**${bid_usd:.2f}** (₹{bid_usd * inr_rate:.2f})", inline=True)
            embed.set_field_at(5, name="High Bidder", value=message.author.mention, inline=True)
            
            await main_msg.edit(embed=embed)
            await bid_channel.send(f"📈 **New Highest Bid!** {message.author.mention} bid **${bid_usd:.2f}**", delete_after=10)
        except Exception as e:
            print(f"Error updating auction embed: {e}")

class AuctionControlView(discord.ui.View):
    def __init__(self, auction_id, cog):
        super().__init__(timeout=None)
        self.auction_id = auction_id
        self.cog = cog

    @discord.ui.button(label="Increase Deadline (+3h)", style=discord.ButtonStyle.secondary)
    async def increase_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Permission check (Admin only based on config)
        config = await db_handler.get_auction_config(interaction.guild_id)
        if not config: return
        _, _, admin_role_id, _ = config
        
        member = interaction.user
        if not member.guild_permissions.administrator and not any(r.id == admin_role_id for r in member.roles):
            await interaction.response.send_message("❌ Only admins can increase the deadline.", ephemeral=True)
            return

        # Logic to fetch current auction time and add 3h
        async with db_handler.aiosqlite.connect(db_handler.DB_PATH) as db:
            async with db.execute('SELECT end_time FROM auctions WHERE id = ?', (self.auction_id,)) as cursor:
                row = await cursor.fetchone()
                if not row: return
                
                current_end = datetime.datetime.fromisoformat(row[0])
                if current_end.tzinfo is None:
                    current_end = current_end.replace(tzinfo=datetime.timezone.utc)
                
                new_end = current_end + datetime.timedelta(hours=3)
                await db_handler.increase_auction_deadline(self.auction_id, new_end.isoformat())
                
                # Update embed
                embed = interaction.message.embeds[0]
                embed.set_field_at(3, name="Ends At", value=f"<t:{int(new_end.timestamp())}:F> (<t:{int(new_end.timestamp())}:R>)", inline=False)
                await interaction.message.edit(embed=embed)
                await interaction.response.send_message(f"✅ Deadline increased by 3 hours!", ephemeral=True)

    @discord.ui.button(label="Stop Auction", style=discord.ButtonStyle.danger)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Permission check
        config = await db_handler.get_auction_config(interaction.guild_id)
        if not config: return
        _, _, admin_role_id, _ = config
        
        member = interaction.user
        if not member.guild_permissions.administrator and not any(r.id == admin_role_id for r in member.roles):
            await interaction.response.send_message("❌ Only admins can stop the auction.", ephemeral=True)
            return

        await self.cog.finalize_auction(self.auction_id, interaction.guild_id, interaction.message.id)
        await interaction.response.send_message("🛑 Auction stopped manually.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AuctionCog(bot))
