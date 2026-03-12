import discord
from discord.ext import commands
from discord import app_commands
from database import db_handler
import asyncio
import os

class BumpReminderCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.DISBOARD_BOT_ID = 302050872383242240

    @app_commands.command(name="bump-config", description="Admin only: Set the channel and role for the 2-hour Disboard bump reminder")
    @app_commands.describe(
        channel="The channel where the bot will send the reminder",
        role="The role to ping when it is time to bump"
    )
    @app_commands.default_permissions(administrator=True)
    async def bump_config(self, interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role):
        try:
            await db_handler.set_bump_config(interaction.guild_id, channel.id, role.id)
            
            embed = discord.Embed(
                title="⏰ Bump Reminder Configured",
                description="The Disboard bump reminder system has been set up!",
                color=discord.Color.brand_green()
            )
            embed.add_field(name="Channel", value=channel.mention, inline=True)
            embed.add_field(name="Ping Role", value=role.mention, inline=True)
            embed.set_footer(text="I will now listen for successful Disboard bumps.")

            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to save config: {e}", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore DMs or messages not from Disboard
        if not message.guild or message.author.id != self.DISBOARD_BOT_ID:
            return

        # Disboard usually sends an embed when a bump is successful.
        if message.embeds:
            embed = message.embeds[0]
            if embed.description and "Bump done!" in embed.description:
                config = await db_handler.get_bump_config(message.guild.id)
                if not config:
                    return

                channel_id, role_id = config
                bump_channel = message.guild.get_channel(channel_id)
                bump_role = message.guild.get_role(role_id)

                if bump_channel and bump_role:
                    confirm_embed = discord.Embed(
                        description="✅ **Bump registered!** I will remind you again in exactly 2 hours.",
                        color=discord.Color.green()
                    )
                    await message.channel.send(embed=confirm_embed)

                    # Start the 2 hour (7200 seconds) background timer
                    await asyncio.sleep(7200)

                    # Send the reminder
                    reminder_embed = discord.Embed(
                        title="⏰ Time to Bump!",
                        description="It has been 2 hours! Please type `/bump` to boost the server again.",
                        color=discord.Color.brand_green()
                    )
                    
                    # Use a relative path for the banner
                    banner_path = os.path.join("banners", "bump.png")
                    if os.path.exists(banner_path):
                        file = discord.File(banner_path, filename="banner.png")
                        reminder_embed.set_image(url="attachment://banner.png")
                        await bump_channel.send(content=bump_role.mention, embed=reminder_embed, file=file)
                    else:
                        await bump_channel.send(content=bump_role.mention, embed=reminder_embed)

async def setup(bot):
    await bot.add_cog(BumpReminderCog(bot))
