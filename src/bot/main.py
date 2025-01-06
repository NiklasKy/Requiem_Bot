"""Main Discord bot module."""
import os
import logging
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from sqlalchemy.orm import aliased
from sqlalchemy import and_, or_

from src.database.connection import get_db_session, init_db
from src.database.models import AFKEntry
from src.database.operations import (delete_afk_entries, get_active_afk,
                                   get_afk_statistics, get_clan_members,
                                   get_or_create_user, get_user_afk_history,
                                   set_afk, track_raid_signup, update_afk_status,
                                   update_afk_active_status)
from src.utils.time_parser import parse_date, parse_time

# Create logs directory if it doesn't exist
os.makedirs("logs", exist_ok=True)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)

# Load environment variables
load_dotenv()

# Get configuration from environment
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0"))
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "0"))
OFFICER_ROLE_ID = int(os.getenv("OFFICER_ROLE_ID", "0"))
CLAN1_ROLE_ID = int(os.getenv("CLAN1_ROLE_ID", "0"))  # Requiem Sun
CLAN2_ROLE_ID = int(os.getenv("CLAN2_ROLE_ID", "0"))  # Requiem Moon

class RequiemBot(commands.Bot):
    """Main bot class."""
    def __init__(self):
        logging.info("Initializing RequiemBot...")
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        """Set up the bot."""
        logging.info(f"Bot is logged in as {self.user}")
        try:
            logging.info("Starting to sync commands...")
            guild = discord.Object(id=GUILD_ID)
            
            # First, clear all commands everywhere
            self.tree.clear_commands(guild=None)
            await self.tree.sync()  # Sync to clear global commands
            
            # Then clear guild-specific commands
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)  # Sync to clear guild commands
            
            # Copy global commands to guild
            self.tree.copy_global_to(guild=guild)
            
            # Final sync to add all commands
            synced = await self.tree.sync(guild=guild)
            
            logging.info(f"Successfully synced {len(synced)} command(s) to guild {GUILD_ID}")
            for command in synced:
                logging.info(f"Synced command: {command.name}")
                
        except Exception as e:
            logging.error(f"Error syncing commands: {e}")
            raise

    async def on_ready(self):
        """Called when the bot is ready."""
        logging.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logging.info(f"Connected to guild ID: {GUILD_ID}")
        logging.info("------")

# Create bot instance
bot = RequiemBot()

def has_required_role():
    """Check if user has required role."""
    async def predicate(interaction: discord.Interaction):
        return any(role.id in [ADMIN_ROLE_ID, OFFICER_ROLE_ID] for role in interaction.user.roles)
    return app_commands.check(predicate)

@bot.tree.command(name="afk", description="Set your AFK status")
@app_commands.describe(
    start_date="Start date (DDMM, DD/MM or DD.MM)",
    start_time="Start time (HHMM or HH:MM)",
    end_date="End date (DDMM, DD/MM or DD.MM)",
    end_time="End time (HHMM or HH:MM)",
    reason="Reason for being AFK"
)
async def afk(
    interaction: discord.Interaction,
    start_date: str,
    start_time: str,
    end_date: str,
    end_time: str,
    reason: str
):
    """Set AFK status command."""
    try:
        # Parse dates
        start_datetime = parse_date(start_date, start_time)
        end_datetime = parse_date(end_date, end_time)
        current_time = datetime.utcnow()

        # Check if dates are in the past and adjust year if needed
        two_weeks_ago = current_time - timedelta(days=14)
        
        # If start date is in the past but within 14 days, reject it
        if start_datetime < current_time and start_datetime > two_weeks_ago:
            await interaction.response.send_message(
                "❌ The start date/time cannot be in the past!",
                ephemeral=True
            )
            return
            
        # If start date is more than 14 days in the past, assume next year
        if start_datetime < two_weeks_ago:
            start_datetime = start_datetime.replace(year=current_time.year + 1)
            end_datetime = end_datetime.replace(year=current_time.year + 1)

        # Validations
        if end_datetime <= start_datetime:
            await interaction.response.send_message(
                "❌ The end date/time must be after the start date/time!",
                ephemeral=True
            )
            return

        # Check clan role
        clan_role_id = None
        for role in interaction.user.roles:
            if role.id in [CLAN1_ROLE_ID, CLAN2_ROLE_ID]:
                clan_role_id = str(role.id)
                break

        if not clan_role_id:
            await interaction.response.send_message(
                "❌ You must be a member of a clan to use this command!",
                ephemeral=True
            )
            return

        # Store in database
        with get_db_session() as db:
            user = get_or_create_user(
                db,
                str(interaction.user.id),
                interaction.user.name,
                interaction.user.display_name,
                clan_role_id
            )
            afk_entry = set_afk(db, user, start_datetime, end_datetime, reason)

        await interaction.response.send_message(
            f"✅ Set AFK status for {interaction.user.display_name}\n"
            f"From: <t:{int(start_datetime.timestamp())}:f>\n"
            f"Until: <t:{int(end_datetime.timestamp())}:f>\n"
            f"Reason: {reason}"
        )

    except ValueError as e:
        await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )

@bot.tree.command(name="afkdelete", description="Delete AFK entries (Admin only)")
@app_commands.describe(
    user="The user whose AFK entries you want to delete",
    all_entries="Delete all entries for this user? If false, only deletes active entries"
)
@has_required_role()
async def afkdelete(
    interaction: discord.Interaction,
    user: discord.Member,
    all_entries: bool = False
):
    """Delete AFK entries command."""
    try:
        with get_db_session() as db:
            target_user = get_or_create_user(
                db,
                str(user.id),
                user.name,
                user.display_name
            )
            deleted_count = delete_afk_entries(db, target_user, all_entries)

        if deleted_count > 0:
            message = f"✅ Successfully deleted {deleted_count} AFK "
            message += f"{'entries' if deleted_count > 1 else 'entry'} for {user.display_name}"
            if not all_entries:
                message += " (active entries only)"
        else:
            message = f"❌ No {'active ' if not all_entries else ''}AFK entries found for {user.display_name}"

        await interaction.response.send_message(message)

    except Exception as e:
        await interaction.response.send_message(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )

@bot.tree.command(name="afkhistory", description="Show AFK history for a user")
@app_commands.describe(user="The user to check history for")
@has_required_role()
async def afkhistory(interaction: discord.Interaction, user: discord.Member):
    """Show AFK history command."""
    try:
        with get_db_session() as db:
            target_user = get_or_create_user(
                db,
                str(user.id),
                user.name,
                user.display_name
            )
            history = get_user_afk_history(db, target_user)

        if not history:
            await interaction.response.send_message(
                f"No AFK history found for {user.display_name}",
                ephemeral=True
            )
            return

        message = f"**AFK History for {user.display_name}:**\n\n"
        current_time = datetime.utcnow()

        for entry in history:
            status = "🟢"  # Current
            if entry.end_date < current_time:
                status = "🔴"  # Expired
            elif entry.start_date > current_time:
                status = "⚪"  # Future

            message += f"{status} From: <t:{int(entry.start_date.timestamp())}:f>\n"
            message += f"Until: <t:{int(entry.end_date.timestamp())}:f>\n"
            message += f"Reason: {entry.reason}\n"
            
            if entry.ended_at:
                message += f"Ended early: <t:{int(entry.ended_at.timestamp())}:f>\n"
            
            message += "─────────────\n"

        await interaction.response.send_message(message)

    except Exception as e:
        await interaction.response.send_message(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )

@bot.tree.command(name="afkstats", description="Show AFK statistics")
@has_required_role()
async def afkstats(interaction: discord.Interaction):
    """Show AFK statistics command."""
    try:
        message = "**AFK Statistics:**\n\n"

        with get_db_session() as db:
            # Get stats for each clan
            for clan_id, clan_name in [
                (CLAN1_ROLE_ID, "Requiem Sun"),
                (CLAN2_ROLE_ID, "Requiem Moon")
            ]:
                stats = get_afk_statistics(db, str(clan_id))
                if stats:
                    total_afk, unique_users, active_now, scheduled_future, avg_duration = stats
                    
                    message += f"__**{clan_name}:**__\n"
                    message += f"Total AFK entries: {total_afk}\n"
                    message += f"Unique users: {unique_users}\n"
                    message += f"Currently AFK: {active_now}\n"
                    message += f"Scheduled for future: {scheduled_future}\n"
                    if avg_duration:
                        message += f"Average AFK duration: {avg_duration:.1f} days\n"
                    message += "\n"

        await interaction.response.send_message(message)

    except Exception as e:
        await interaction.response.send_message(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )

@bot.tree.command(name="afklist", description="List all AFK users")
async def afklist(interaction: discord.Interaction):
    """List AFK users command."""
    try:
        # Check if user is admin/officer
        is_admin = any(role.id in [ADMIN_ROLE_ID, OFFICER_ROLE_ID] for role in interaction.user.roles)
        
        # For regular users, check clan membership
        user_clan_role_id = None
        for role in interaction.user.roles:
            if role.id in [CLAN1_ROLE_ID, CLAN2_ROLE_ID]:
                user_clan_role_id = str(role.id)
                break
            
        if not is_admin and not user_clan_role_id:
            await interaction.response.send_message(
                "❌ You must be a member of a clan to use this command!",
                ephemeral=True
            )
            return

        current_time = datetime.utcnow()
        found_entries = False

        with get_db_session() as db:
            message = "**Currently AFK Users:**\n\n"
            
            if is_admin:
                # Show all clans for admins
                for clan_id, clan_name in [
                    (CLAN1_ROLE_ID, "Requiem Sun"),
                    (CLAN2_ROLE_ID, "Requiem Moon")
                ]:
                    afk_users = get_active_afk(db, clan_role_id=str(clan_id))
                    if afk_users:
                        found_entries = True
                        message += f"__**{clan_name}:**__\n"
                        for user, entry in afk_users:
                            status = "🟢"  # Current
                            if entry.end_date < current_time:
                                status = "🔴"  # Expired
                            elif entry.start_date > current_time:
                                status = "⚪"  # Future
                                
                            message += f"{status} **{user.display_name or user.username}**\n"
                            message += f"From: <t:{int(entry.start_date.timestamp())}:f>\n"
                            message += f"Until: <t:{int(entry.end_date.timestamp())}:f>\n"
                            message += f"Reason: {entry.reason}\n\n"
                        message += "─────────────\n"
                
                if not found_entries:
                    message += "No users are currently AFK in any clan."
            else:
                # Show only user's clan
                clan_name = "Requiem Sun" if user_clan_role_id == str(CLAN1_ROLE_ID) else "Requiem Moon"
                afk_users = get_active_afk(db, clan_role_id=user_clan_role_id)
                
                if not afk_users:
                    message += f"No users from {clan_name} are currently AFK!"
                else:
                    found_entries = True
                    message += f"__**{clan_name}:**__\n"
                    for user, entry in afk_users:
                        status = "🟢"  # Current
                        if entry.end_date < current_time:
                            status = "🔴"  # Expired
                        elif entry.start_date > current_time:
                            status = "⚪"  # Future
                            
                        message += f"{status} **{user.display_name or user.username}**\n"
                        message += f"From: <t:{int(entry.start_date.timestamp())}:f>\n"
                        message += f"Until: <t:{int(entry.end_date.timestamp())}:f>\n"
                        message += f"Reason: {entry.reason}\n\n"

        await interaction.response.send_message(message)

    except Exception as e:
        logging.error(f"Error in afklist command: {e}")
        await interaction.response.send_message(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )

@bot.tree.command(name="afkreturn", description="Return from AFK status")
async def afkreturn(interaction: discord.Interaction):
    """Return from AFK command."""
    try:
        with get_db_session() as db:
            user = get_or_create_user(
                db,
                str(interaction.user.id),
                interaction.user.name,
                interaction.user.display_name
            )
            updated = update_afk_status(db, user, all_entries=False)

        if updated > 0:
            await interaction.response.send_message(
                f"✅ Welcome back, {interaction.user.display_name}! Your AFK status has been updated."
            )
        else:
            await interaction.response.send_message(
                "❌ You're not marked as AFK!",
                ephemeral=True
            )

    except Exception as e:
        await interaction.response.send_message(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )

@bot.tree.command(name="afkquick", description="Quickly set AFK status until end of day")
@app_commands.describe(
    reason="Reason for being AFK",
    days="Optional: Number of days to be AFK (default: until end of today)"
)
async def afkquick(
    interaction: discord.Interaction,
    reason: str,
    days: int = None
):
    """Quick AFK command."""
    try:
        # Get current time as start
        start_datetime = datetime.utcnow()
        
        # Calculate end time
        if days is None:
            # Set to end of current day
            end_datetime = start_datetime.replace(hour=23, minute=59, second=59)
        else:
            if days <= 0:
                await interaction.response.send_message(
                    "❌ Number of days must be positive!",
                    ephemeral=True
                )
                return
                
            # Add specified days and set to end of that day
            end_datetime = (start_datetime + timedelta(days=days)).replace(
                hour=23, minute=59, second=59
            )

        # Check clan role
        clan_role_id = None
        for role in interaction.user.roles:
            if role.id in [CLAN1_ROLE_ID, CLAN2_ROLE_ID]:
                clan_role_id = str(role.id)
                break

        if not clan_role_id:
            await interaction.response.send_message(
                "❌ You must be a member of a clan to use this command!",
                ephemeral=True
            )
            return

        # Store in database
        with get_db_session() as db:
            user = get_or_create_user(
                db,
                str(interaction.user.id),
                interaction.user.name,
                interaction.user.display_name,
                clan_role_id
            )
            afk_entry = set_afk(db, user, start_datetime, end_datetime, reason)

        await interaction.response.send_message(
            f"✅ Quick AFK set for {interaction.user.display_name}\n"
            f"From: <t:{int(start_datetime.timestamp())}:f>\n"
            f"Until: <t:{int(end_datetime.timestamp())}:f>\n"
            f"Reason: {reason}"
        )

    except Exception as e:
        await interaction.response.send_message(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )

@bot.tree.command(name="getmembers", description="List all members with a specific role")
@app_commands.describe(role="The role to check members for")
@has_required_role()
async def getmembers(interaction: discord.Interaction, role: discord.Role):
    """Get members command."""
    try:
        await interaction.response.defer()

        with get_db_session() as db:
            # Update database with current members
            for member in role.members:
                clan_role_id = None
                for member_role in member.roles:
                    if member_role.id in [CLAN1_ROLE_ID, CLAN2_ROLE_ID]:
                        clan_role_id = str(member_role.id)
                        break

                get_or_create_user(
                    db,
                    str(member.id),
                    member.name,
                    member.display_name,
                    clan_role_id
                )

            # Get members from database
            if role.id in [CLAN1_ROLE_ID, CLAN2_ROLE_ID]:
                members = get_clan_members(db, str(role.id))
            else:
                members = [
                    get_or_create_user(
                        db,
                        str(member.id),
                        member.name,
                        member.display_name
                    )
                    for member in role.members
                ]

            # Create message within the session
            message = f"**Members with role {role.name} ({len(members)}):**\n\n"
            for member in sorted(members, key=lambda x: x.username.lower()):
                if member.display_name:
                    message += f"{member.display_name} ({member.username})\n"
                else:
                    message += f"{member.username}\n"

        # Send message (split if too long)
        if len(message) > 2000:
            chunks = [message[i:i+1900] for i in range(0, len(message), 1900)]
            for i, chunk in enumerate(chunks):
                if i == 0:
                    await interaction.followup.send(chunk)
                else:
                    await interaction.followup.send(chunk)
        else:
            await interaction.followup.send(message)

    except Exception as e:
        logging.error(f"Error in getmembers command: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )

@bot.tree.command(name="afkmy", description="Show your personal AFK entries")
@app_commands.guild_only()
async def afkmy(interaction: discord.Interaction):
    """Show personal AFK entries for the user."""
    try:
        with get_db_session() as db:
            # Get user from database
            user = get_or_create_user(
                db,
                str(interaction.user.id),
                interaction.user.name,
                interaction.user.display_name
            )
            
            # Get all user's AFK entries
            afk_entries = get_user_afk_history(db, user, limit=10)  # Show last 10 entries
            
            if not afk_entries:
                await interaction.response.send_message(
                    "📝 You don't have any AFK entries.",
                    ephemeral=True
                )
                return
                
            # Create embed
            embed = discord.Embed(
                title="🕒 Your AFK Entries",
                description="Showing your last 10 AFK entries",
                color=discord.Color.blue()
            )
            
            current_time = datetime.utcnow()
            
            # Add fields for each AFK entry
            for afk in afk_entries:
                # Determine status
                if afk.is_active:
                    if current_time < afk.start_date:
                        status = "⚪ Scheduled"  # Future
                    elif current_time > afk.end_date:
                        status = "🔴 Expired"  # Expired
                    else:
                        status = "🟢 Active"  # Current
                else:
                    status = "⚫ Inactive"  # Inactive
                
                embed.add_field(
                    name=f"{status}",
                    value=(
                        f"From: <t:{int(afk.start_date.timestamp())}:f>\n"
                        f"Until: <t:{int(afk.end_date.timestamp())}:f>\n"
                        f"Reason: {afk.reason if afk.reason else 'No reason provided'}"
                        + (f"\nEnded early: <t:{int(afk.ended_at.timestamp())}:f>" if afk.ended_at else "")
                    ),
                    inline=False
                )
                
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
    except Exception as e:
        logging.error(f"Error in afkmy command: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )

def run_bot():
    """Run the bot."""
    logging.info("Starting bot initialization...")
    try:
        # Initialize database
        logging.info("Initializing database...")
        init_db()
        logging.info("Database initialized successfully")
        
        # Update AFK statuses
        with get_db_session() as db:
            updated = update_afk_active_status(db)
            if updated > 0:
                logging.info(f"Updated {updated} AFK entries' active status")
        
        # Start bot
        logging.info("Starting bot...")
        bot.run(TOKEN)
    except Exception as e:
        logging.error(f"Error during bot startup: {e}")
        raise

if __name__ == "__main__":
    run_bot() 