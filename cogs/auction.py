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
        self.hourly_cleanup.start()
        self.sticky_task.start()
        self.sticky_message_ids = {} # {channel_id: message_id}

    async def cog_load(self):
        """Register persistent views for all active auctions on startup."""
        active_auctions = await db_handler.get_all_active_auctions()
        for auction_id, _, _, _ in active_auctions:
            self.bot.add_view(AuctionControlView(auction_id, self))
        print(f"Registered {len(active_auctions)} persistent auction views.")

    def cog_unload(self):
        self.auction_cleanup.cancel()
        self.hourly_cleanup.cancel()
        self.sticky_task.cancel()

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

    @tasks.loop(hours=1.0)
    async def hourly_cleanup(self):
        """Delete messages with ❌ reactions every hour."""
        configs = await db_handler.get_all_auction_configs()
        for guild_id, bid_channel_id, _, _, _ in configs:
            guild = self.bot.get_guild(guild_id)
            if not guild: continue
            channel = guild.get_channel(bid_channel_id)
            if not channel: continue
            
            try:
                async for message in channel.history(limit=100):
                    if any(str(reaction.emoji) == "❌" for reaction in message.reactions):
                        await message.delete()
            except:
                pass

    @tasks.loop(seconds=30)
    async def sticky_task(self):
        """Ensure a sticky info message is at the bottom of auction channels."""
        configs = await db_handler.get_all_auction_configs()
        for guild_id, bid_channel_id, _, _, _ in configs:
            guild = self.bot.get_guild(guild_id)
            if not guild: continue
            channel = guild.get_channel(bid_channel_id)
            if not channel: continue
            
            # Check if there's an active auction
            auction = await db_handler.get_auction_by_channel(guild_id)
            if not auction: continue
            
            embed = discord.Embed(
                title="📌 How to Bid",
                description=(
                    "• **Format**: `100$` or `8000₹`\n"
                    "• **Rules**: Type `/auction-rules` to read all terms.\n"
                    "• **Validity**: Wait for ✅ reaction. ❌ means your bid was invalid."
                ),
                color=discord.Color.blue()
            )
            
            last_msg_id = self.sticky_message_ids.get(bid_channel_id)
            is_at_bottom = False
            
            try:
                # Check if our sticky is the last message
                async for last_msg in channel.history(limit=1):
                    if last_msg_id and last_msg.id == last_msg_id:
                        is_at_bottom = True
                    break
                
                if not is_at_bottom:
                    if last_msg_id:
                        try:
                            old_msg = await channel.fetch_message(last_msg_id)
                            await old_msg.delete()
                        except: pass
                    
                    new_msg = await channel.send(embed=embed)
                    self.sticky_message_ids[bid_channel_id] = new_msg.id
            except:
                pass

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
                rules_embed = self.get_rules_embed()
                await rules_channel.send(embed=rules_embed)
                
        except Exception as e:
            await interaction.response.send_message(f"❌ Setup failed: {e}", ephemeral=True)

    def get_rules_embed(self):
        rules_text = (
            "### 📜 OFFICIAL AUCTION RULES\n\n"
            "**1. General Conduct**\n"
            "• **No Fake Bidding**: Do not bid if you do not have the funds ready. Backing out of a winning bid will result in an immediate and permanent ban.\n"
            "• **No Bid Retractions**: Once a bid is placed, it is final. Think before you type.\n"
            "• **Verification Required**: All sellers must provide account details to Admin before starting. Auction won't stop once started if account owner says.\n\n"
            "**2. COMMISSION**\n"
            "• **10%** of the final sale price must go to the Server Owner for facilitating the auction.\n\n"
            "**3. The Bidding Process**\n"
            "• **Format**: Bids must follow `50$` or `5000₹` format ONLY. Plain numbers are rejected.\n"
            "• **Increments**: Respect the Minimum Bid Increment set for each auction.\n"
            "• **Starting Bid (SB)**: Agreed upon with the seller before the auction goes live.\n\n"
            "**4. Anti-Snipe Protection**\n"
            "• If a bid is placed within the **last 5 minutes**, the timer is automatically extended by **10 minutes**.\n\n"
            "**5. Payment & Middleman (MM)**\n"
            "• **Payment Window**: Winners must contact the ADMIN and initiate payment within 24 hours.\n\n"
            "**6. Restrictions**\n"
            "• STEAM LINKED OPBR ACCOUNTS WONT BE PUT ON AUCTION."
        )
        embed = discord.Embed(
            title="Auction Terms & Conditions",
            description=rules_text,
            color=discord.Color.dark_gold()
        )
        embed.set_footer(text="By bidding, you agree to all rules above.")
        return embed

    @app_commands.command(name="auction-rules", description="Display the auction rules")
    async def auction_rules(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self.get_rules_embed())

    def parse_numeric(self, val_str: str) -> float:
        """Helper to extract float from strings like '1$', '5h', '83.50₹'"""
        cleaned = re.sub(r'[^\d.]', '', val_str)
        return float(cleaned) if cleaned else 0.0

    def parse_duration(self, duration_str: str) -> float:
        """Parses durations like '1h 30m', '45m', '2h' into total hours (float)."""
        duration_str = duration_str.lower().strip()
        # Handle '1h 30m' or '1h30m'
        parts = re.findall(r'(\d+)\s*([hm])', duration_str)
        if parts:
            total_minutes = 0
            for val, unit in parts:
                if unit == 'h':
                    total_minutes += int(val) * 60
                elif unit == 'm':
                    total_minutes += int(val)
            return total_minutes / 60.0
        # Fallback for plain numbers (assume hours)
        cleaned = re.sub(r'[^\d.]', '', duration_str)
        return float(cleaned) if cleaned else 0.0

    @app_commands.command(name="create-auction", description="Start a new auction")
    @app_commands.describe(
        title="Title of the auction",
        details="Details about the account",
        starting_price="Starting price (e.g. 1$)",
        min_raise="Minimum raise (e.g. 0.5$)",
        duration="Duration (e.g. 5h, 1h 30m, 45m)",
        inr_rate="Conversion rate (e.g. 100 or 100₹)",
        image="Optional image of the account"
    )
    async def create_auction(self, interaction: discord.Interaction, title: str, details: str, starting_price: str, min_raise: str, duration: str, inr_rate: str, image: discord.Attachment | None = None):
        config = await db_handler.get_auction_config(interaction.guild_id)
        if not config:
            await interaction.response.send_message("❌ Auction system is not set up. Use `/auction-setup` first.", ephemeral=True)
            return
            
        _, _, admin_role_id, _ = config
        member = interaction.user
        if not member.guild_permissions.administrator and not any(r.id == admin_role_id for r in member.roles):
            await interaction.response.send_message("❌ You don't have permission to start auctions.", ephemeral=True)
            return

        try:
            s_price = self.parse_numeric(starting_price)
            m_raise = self.parse_numeric(min_raise)
            h_val = self.parse_duration(duration)
            i_rate = self.parse_numeric(inr_rate)
            
            if s_price <= 0 or h_val <= 0 or i_rate <= 0:
                raise ValueError("Values must be greater than zero.")
        except Exception:
            await interaction.response.send_message("❌ Invalid values. Provide formats like `1$`, `1h 30m`, or `100₹`.", ephemeral=True)
            return

        bid_channel_id = config[0]
        channel = interaction.guild.get_channel(bid_channel_id)
        if not channel:
            await interaction.response.send_message("❌ Bidding channel not found.", ephemeral=True)
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        end_time = now + datetime.timedelta(hours=h_val)
        
        auction_id = await db_handler.create_auction(
            interaction.guild_id, title, details, s_price, m_raise, i_rate, end_time.isoformat()
        )
        
        embed = discord.Embed(
            title=f"🟢 ACTIVE AUCTION: {title}",
            description=details,
            color=discord.Color.green(),
        )
        embed.add_field(name="Starting Price", value=f"${s_price:.2f}", inline=True)
        embed.add_field(name="Minimum Raise", value=f"${m_raise:.2f}", inline=True)
        embed.add_field(name="INR Rate", value=f"$1 = ₹{i_rate:.2f}", inline=True)
        embed.add_field(name="Ends At", value=f"<t:{int(end_time.timestamp())}:F> (<t:{int(end_time.timestamp())}:R>)", inline=False)
        embed.add_field(name="Current Bid", value="None", inline=True)
        embed.add_field(name="High Bidder", value="None", inline=True)
        
        if image:
            embed.set_image(url=image.url)
            
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

        if message.author.guild_permissions.administrator or any(r.id == mod_role_id for r in message.author.roles):
            return

        content = message.content.strip()
        match = re.search(r'(\d+(\.\d+)?)\s*([$₹])', content)
        
        if not match:
            await message.add_reaction("❌")
            error_msg = f"❌ {message.author.mention}, invalid format! Only `50$` or `5000₹` allowed. (Deleting this in 10s)"
            await message.channel.send(error_msg, delete_after=10)
            try:
                await message.author.send(f"⚠️ **Auction Alert**: In #{message.channel.name}, your bid was rejected because of the wrong format. Please use `100$` or `8000₹`.")
            except: pass
            return

        amount = float(match.group(1))
        currency = match.group(3)
        
        auction_data = await db_handler.get_auction_by_channel(message.guild.id)
        if not auction_data:
            await message.add_reaction("❌")
            return

        auction_id, msg_id, title, start_price, min_raise, i_rate, end_time_str = auction_data
        bid_usd = amount / i_rate if currency == '₹' else amount
        
        highest_bid = await db_handler.get_highest_bid(auction_id)
        current_max = highest_bid[1] if highest_bid else (start_price - min_raise) # Fix: next bid must be >= start_price
        required_bid = current_max + min_raise
        
        # Precise comparison
        if bid_usd < (required_bid - 0.001):
            await message.add_reaction("❌")
            next_bid_inr = required_bid * i_rate
            await message.channel.send(f"❌ {message.author.mention}, your bid of **${bid_usd:.2f}** is too low. Minimum required: **${required_bid:.2f}** (≈₹{next_bid_inr:.2f}).", delete_after=10)
            return

        await message.add_reaction("✅")
        await db_handler.add_bid(auction_id, message.author.id, bid_usd)
        
        end_time = datetime.datetime.fromisoformat(end_time_str)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=datetime.timezone.utc)
            
        now = datetime.datetime.now(datetime.timezone.utc)
        if 0 < (end_time - now).total_seconds() < 180: # 180s = 3m
            new_end_time = end_time + datetime.timedelta(minutes=3)
            await db_handler.increase_auction_deadline(auction_id, new_end_time.isoformat())
            end_time = new_end_time
            
        try:
            main_msg = await message.channel.fetch_message(msg_id)
            embed = main_msg.embeds[0]
            embed.set_field_at(3, name="Ends At", value=f"<t:{int(end_time.timestamp())}:F> (<t:{int(end_time.timestamp())}:R>)", inline=False)
            embed.set_field_at(4, name="Current Bid", value=f"**${bid_usd:.2f}** (₹{bid_usd * i_rate:.2f})", inline=True)
            embed.set_field_at(5, name="High Bidder", value=message.author.mention, inline=True)
            await main_msg.edit(embed=embed)
            await message.channel.send(f"📈 **New Highest Bid!** {message.author.mention} bid **${bid_usd:.2f}**", delete_after=10)
        except Exception as e:
            print(f"Error updating auction: {e}")

class IncreaseDeadlineModal(discord.ui.Modal, title='Increase Auction Deadline'):
    duration = discord.ui.TextInput(
        label='Additional Duration',
        placeholder='e.g. 1h, 30m, 1h 30m',
        required=True
    )

    def __init__(self, auction_id, cog, original_message):
        super().__init__()
        self.auction_id = auction_id
        self.cog = cog
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        added_hours = self.cog.parse_duration(self.duration.value)
        if added_hours <= 0:
            await interaction.response.send_message("❌ Invalid duration format.", ephemeral=True)
            return

        async with db_handler.aiosqlite.connect(db_handler.DB_PATH) as db:
            async with db.execute('SELECT end_time FROM auctions WHERE id = ?', (self.auction_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    await interaction.response.send_message("❌ Auction not found.", ephemeral=True)
                    return
                
                current_end = datetime.datetime.fromisoformat(row[0])
                if current_end.tzinfo is None:
                    current_end = current_end.replace(tzinfo=datetime.timezone.utc)
                
                new_end = current_end + datetime.timedelta(hours=added_hours)
                await db_handler.increase_auction_deadline(self.auction_id, new_end.isoformat())
                
                try:
                    embed = self.original_message.embeds[0]
                    embed.set_field_at(3, name="Ends At", value=f"<t:{int(new_end.timestamp())}:F> (<t:{int(new_end.timestamp())}:R>)", inline=False)
                    await self.original_message.edit(embed=embed)
                    await interaction.response.send_message(f"✅ Deadline increased by {self.duration.value}!", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"❌ Failed to update embed: {e}", ephemeral=True)

class AuctionControlView(discord.ui.View):
    def __init__(self, auction_id, cog):
        super().__init__(timeout=None)
        self.auction_id = auction_id
        self.cog = cog
        
        # Explicit custom_ids for persistence across bot restarts
        self.increase_btn.custom_id = f"auc_inc_{auction_id}"
        self.stop_btn.custom_id = f"auc_stp_{auction_id}"

    @discord.ui.button(label="Increase Deadline", style=discord.ButtonStyle.secondary)
    async def increase_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await db_handler.get_auction_config(interaction.guild_id)
        if not config or (not interaction.user.guild_permissions.administrator and not any(r.id == config[2] for r in interaction.user.roles)):
            await interaction.response.send_message("❌ Only admins can use this.", ephemeral=True)
            return

        await interaction.response.send_modal(IncreaseDeadlineModal(self.auction_id, self.cog, interaction.message))

    @discord.ui.button(label="Stop Auction", style=discord.ButtonStyle.danger)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await db_handler.get_auction_config(interaction.guild_id)
        if not config or (not interaction.user.guild_permissions.administrator and not any(r.id == config[2] for r in interaction.user.roles)):
            await interaction.response.send_message("❌ Only admins can stop the auction.", ephemeral=True)
            return

        # Defer to prevent "Interaction failed" while processing DB and message updates
        await interaction.response.defer(ephemeral=True)
        await self.cog.finalize_auction(self.auction_id, interaction.guild_id, interaction.message.id)
        await interaction.followup.send("🛑 Auction stopped manually.")

async def setup(bot):
    await bot.add_cog(AuctionCog(bot))
