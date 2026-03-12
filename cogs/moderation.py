import discord
from discord.ext import commands
from discord import app_commands
from database import db_handler

class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="membercount", description="Show the total number of members in the server")
    async def membercount(self, interaction: discord.Interaction):
        count = interaction.guild.member_count
        embed = discord.Embed(
            title="Member Count",
            description=f"There are currently **{count}** members in {interaction.guild.name}.",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(target="The member to ban", reason="The reason for the ban")
    @app_commands.default_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, target: discord.Member, reason: str | None = None):
        if target.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("You cannot ban someone with an equal or higher role than you.", ephemeral=True)
            return

        try:
            await target.ban(reason=f"Banned by {interaction.user}: {reason or 'No reason provided'}")
            
            embed = discord.Embed(
                title="Member Banned",
                description=f"**{target.name}** has been banned.",
                color=discord.Color.red()
            )
            embed.add_field(name="Reason", value=reason or "No reason provided")
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to ban that member.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(target="The member to kick", reason="The reason for the kick")
    @app_commands.default_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, target: discord.Member, reason: str | None = None):
        if target.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("You cannot kick someone with an equal or higher role than you.", ephemeral=True)
            return

        try:
            await target.kick(reason=f"Kicked by {interaction.user}: {reason or 'No reason provided'}")
            
            embed = discord.Embed(
                title="Member Kicked",
                description=f"**{target.name}** has been kicked.",
                color=discord.Color.orange()
            )
            embed.add_field(name="Reason", value=reason or "No reason provided")
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to kick that member.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

    @app_commands.command(name="warn", description="Warn a member")
    @app_commands.describe(target="The member to warn", reason="The reason for the warning")
    @app_commands.default_permissions(kick_members=True) # Usually kick perms are enough for warnings
    async def warn(self, interaction: discord.Interaction, target: discord.Member, reason: str):
        if target.bot:
            await interaction.response.send_message("You cannot warn bots.", ephemeral=True)
            return
            
        try:
            # Add to database
            await db_handler.add_warning(target.id, interaction.guild.id, interaction.user.id, reason)
            
            # Attempt to DM user
            try:
                dm_channel = await target.create_dm()
                dm_embed = discord.Embed(
                    title=f"You have been warned in {interaction.guild.name}",
                    description=f"**Reason:** {reason}",
                    color=discord.Color.gold()
                )
                await dm_channel.send(embed=dm_embed)
                dm_status = "User was notified via DM."
            except discord.Forbidden:
                dm_status = "User has DMs disabled."
            except discord.HTTPException as e:
                dm_status = f"Could not DM user (Error: {e.code})."

            # Send public acknowledgment
            embed = discord.Embed(
                title="Member Warned",
                description=f"**{target.mention}** has been warned.",
                color=discord.Color.gold()
            )
            embed.add_field(name="Reason", value=reason)
            embed.set_footer(text=dm_status)
            
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

    @app_commands.command(name="warnings", description="View a member's warning history")
    @app_commands.describe(target="The member to check")
    async def view_warnings(self, interaction: discord.Interaction, target: discord.Member):
        try:
            warnings = await db_handler.get_user_warnings(target.id, interaction.guild.id)
            
            if not warnings:
                await interaction.response.send_message(f"✅ **{target.name}** has a clean record (no warnings).", ephemeral=True)
                return

            embed = discord.Embed(
                title=f"Warning History: {target.name}",
                color=discord.Color.gold()
            )
            embed.set_thumbnail(url=target.display_avatar.url)
            
            for i, (admin_id, reason, timestamp) in enumerate(warnings, 1):
                admin = interaction.guild.get_member(admin_id)
                admin_name = admin.name if admin else f"Unknown Admin (ID: {admin_id})"
                embed.add_field(
                    name=f"Warning #{i}",
                    value=f"**Reason:** {reason}\n**By:** {admin_name}\n**Date:** {timestamp}",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(ModerationCog(bot))
