import discord
from discord.ext import commands
from discord import app_commands
from database import db_handler
import os

class WelcomeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="welcome-setup", description="Admin only: Configure the welcome system")
    @app_commands.describe(
        welcome_channel="The channel where welcome messages are sent",
        shop_channel="The shop/products channel to mention in the welcome message",
        support_channel="The support/ticket channel to mention in the welcome message"
    )
    @app_commands.default_permissions(administrator=True)
    async def welcome_setup(self, interaction: discord.Interaction, welcome_channel: discord.TextChannel, shop_channel: discord.TextChannel, support_channel: discord.TextChannel):
        try:
            await db_handler.set_welcome_config(interaction.guild_id, welcome_channel.id, shop_channel.id, support_channel.id)
            
            embed = discord.Embed(
                title="👋 Welcome System Configured",
                description="The welcome message system is now active!",
                color=discord.Color.green()
            )
            embed.add_field(name="Welcome Channel", value=welcome_channel.mention)
            embed.add_field(name="Shop Channel", value=shop_channel.mention)
            embed.add_field(name="Support Channel", value=support_channel.mention)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Setup failed: {e}", ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        config = await db_handler.get_welcome_config(member.guild.id)
        if not config:
            return
            
        welcome_id, shop_id, support_id = config
        channel = member.guild.get_channel(welcome_id)
        
        if channel:
            shop_mention = f"<#{shop_id}>" if shop_id else "#shop"
            support_mention = f"<#{support_id}>" if support_id else "#support"
            
            embed = discord.Embed(
                title=f"Welcome to the Store, {member.name}! 🎉",
                description=f"Hello {member.mention}! Thanks for joining our community.\n\n"
                            f"🛒 **Check out our products in {shop_mention}**\n"
                            f"🎫 **Need help? Open a ticket in {support_mention}**\n\n"
                            "We hope you enjoy your stay!",
                color=discord.Color.brand_green()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"You are member #{member.guild.member_count}!")
            
            try:
                await channel.send(embed=embed)
            except: pass

async def setup(bot):
    await bot.add_cog(WelcomeCog(bot))
