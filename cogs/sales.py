import discord
from discord.ext import commands
from discord import app_commands

class SoldButtonView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=None)
        self.author_id = author_id

    @discord.ui.button(label="Click here if sold", style=discord.ButtonStyle.danger)
    async def mark_sold(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the person who posted this account can mark it as sold.", ephemeral=True)
            return
            
        embed = interaction.message.embeds[0]
        # Keep it clean by only adding sold if not already there
        if "SOLD" not in str(embed.title):
            embed.title = f"🔴 [SOLD] {embed.title}"
            
        embed.color = discord.Color.red()
        
        # Add bold sold message to description
        if embed.description and "**SOLD**" not in embed.description:
            embed.description = f"**This account has been SOLD!**\n\n{embed.description}"
            
        button.disabled = True
        button.label = "Account Sold"
        
        await interaction.response.edit_message(embed=embed, view=self)

class SalesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="post", description="Post an account for sale")
    @app_commands.describe(
        title="The title of the account listing",
        price="The price of the account (e.g., $50 or 50 TF2 Keys)",
        description="A detailed description of the account",
        steam_linked="Is the account linked to Steam?",
        exp_hacked="Was the account's EXP hacked/botted?",
        image="Optional screenshot or image of the account"
    )
    @app_commands.choices(
        steam_linked=[
            app_commands.Choice(name="Yes", value="Yes"),
            app_commands.Choice(name="No", value="No")
        ],
        exp_hacked=[
            app_commands.Choice(name="Yes", value="Yes"),
            app_commands.Choice(name="No", value="No")
        ],
        device=[
            app_commands.Choice(name="Android", value="Android"),
            app_commands.Choice(name="iOS", value="iOS")
        ]
    )
    async def post_account(
        self, 
        interaction: discord.Interaction, 
        title: str, 
        price: str | None = None, 
        description: str | None = None, 
        steam_linked: app_commands.Choice[str] | None = None, 
        exp_hacked: app_commands.Choice[str] | None = None, 
        device: app_commands.Choice[str] | None = None,
        image: discord.Attachment | None = None
    ):
        # Build the dynamic description
        desc_parts: list[str] = []
        if description:
            desc_parts.append(description)
            desc_parts.append("") # For the double newline
            
        tags: list[str] = []
        if steam_linked:
            tags.append(f"**🎮 Steam Linked:** {steam_linked.value}")
        if exp_hacked:
            tags.append(f"**⚠️ EXP Hacked:** {exp_hacked.value}")
        if device:
            tags.append(f"**📱 Device:** {device.value}")
            
        if tags:
            desc_parts.append("\n".join(tags))
            
        full_description = "\n".join(desc_parts)
        
        # Create a professional-looking embed
        embed = discord.Embed(
            title=f"🛒 {title}",
            description=full_description if full_description else None,
            color=discord.Color.blue()
        )
        
        # Add fields
        if price:
            embed.add_field(name="💰 Price", value=f"**{price}**", inline=False)
        
        # Set footer and author
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None)
        embed.set_footer(text="Open a ticket to purchase this account!")
        
        # Add image if provided
        if image:
            embed.set_image(url=image.url)

        view = SoldButtonView(author_id=interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="vouch", description="Log a successful sale and vouch for a user")
    @app_commands.describe(
        buyer="The user who bought the account",
        description="What was sold to the user (e.g. 'Stacked OG Account')",
        vouch_number="Optional vouch counter (e.g. '#24' or '24')",
        device="The device used (Android/iOS)",
        image="Optional screenshot of the transaction or account"
    )
    @app_commands.choices(
        device=[
            app_commands.Choice(name="Android", value="Android"),
            app_commands.Choice(name="iOS", value="iOS")
        ]
    )
    async def vouch(
        self, 
        interaction: discord.Interaction, 
        buyer: discord.Member, 
        description: str, 
        vouch_number: str | None = None,
        device: app_commands.Choice[str] | None = None,
        image: discord.Attachment | None = None
    ):
        # Create a success-themed embed
        vouch_title = f"✅ Successful Sale! {vouch_number if vouch_number else ''}".strip()
        embed = discord.Embed(
            title=vouch_title,
            description=f"**Seller:** {interaction.user.mention}\n**Buyer:** {buyer.mention}\n" + (f"**Device:** {device.value}\n" if device else "") + f"\n**Item Sold:**\n{description}",
            color=discord.Color.green()
        )
        
        # Add image if provided
        if image:
            embed.set_image(url=image.url)
            
        embed.set_footer(text="Thank you for your purchase!")

        # We ping the buyer in the message content so they get a notification, 
        # but the main info is in the embed.
        await interaction.response.send_message(content=f"Hey {buyer.mention}, thanks for dealing with us!", embed=embed)

    @app_commands.command(name="payment_methods", description="Show available payment methods")
    async def payment_methods(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="💳 Available Payment Methods",
            description="Here are the currently accepted payment methods for purchases:",
            color=discord.Color.gold()
        )
        
        # Add fields for payment methods
        embed.add_field(name="🟡 Binance", value="Accepted for direct crypto transfers.", inline=False)
        embed.add_field(name="🪙 Crypto", value="Most major cryptocurrencies accepted (BTC, ETH, LTC, etc.).", inline=False)
        embed.add_field(name="🏛️ UPI / Google Pay", value="Accepted for Indian users.", inline=False)
        embed.add_field(name="🦉 Wise", value="Accepted for international bank transfers.", inline=False)
        
        # Add contact info
        embed.add_field(
            name="❓ Other Methods", 
            value="If you need to use another method, please ask in a DM.", 
            inline=False
        )
        
        embed.description += "\n\n**To proceed with a payment, please DM:**\n<@1125015674557829140>"
        embed.set_footer(text="Always verify you are speaking to the correct person before sending funds!")
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="add_stock", description="Admin only: Announce new stock to a channel")
    @app_commands.describe(
        channel="The channel to post the stock announcement in",
        title="The title of the new stock",
        amount="The price or amount (optional)",
        description="Details about the stock (optional)",
        quantity="How many are available (optional)",
        image="An image of the stock (optional)"
    )
    @app_commands.default_permissions(administrator=True)
    async def add_stock(
        self, 
        interaction: discord.Interaction, 
        channel: discord.TextChannel,
        title: str,
        amount: str | None = None,
        description: str | None = None,
        quantity: int | None = None,
        image: discord.Attachment | None = None
    ):
        # Create the stock announcement embed
        embed = discord.Embed(
            title=f"📦 RESTOCK: {title}",
            description=description or "New stock has just arrived!",
            color=discord.Color.purple()
        )
        
        if amount:
            embed.add_field(name="💰 Price/Amount", value=f"**{amount}**", inline=True)
        if quantity is not None:
            embed.add_field(name="🔢 Quantity Available", value=f"**{quantity}**", inline=True)
            
        embed.set_footer(text="Grab it before it's gone! Open a ticket to purchase.")
        
        if image:
            embed.set_image(url=image.url)

        try:
            # Send to the target channel
            await channel.send(embed=embed)
            # Confirm to the admin
            await interaction.response.send_message(f"✅ Stock announcement successfully posted in {channel.mention}!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(f"❌ I don't have permission to send messages in {channel.mention}.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ An error occurred: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(SalesCog(bot))
