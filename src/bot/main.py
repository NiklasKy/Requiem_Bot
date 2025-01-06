"""Main Discord bot module."""
import os
import logging
from datetime import datetime, timedelta
import time
import asyncio
import aiohttp

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
                                   update_afk_active_status, get_user_active_and_future_afk,
                                   get_clan_active_and_future_afk, remove_future_afk)
from src.utils.time_parser import parse_date, parse_time, parse_datetime

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
    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix=command_prefix, intents=intents)
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.update_afk_task = None

    async def setup_hook(self):
        """Set up the bot."""
        try:
            # Initialize database
            logging.info("Initializing database...")
            init_db()
            logging.info("Database initialized successfully")
            
            # Update AFK statuses
            with get_db_session() as db:
                try:
                    update_afk_active_status(db)
                    logging.info("Updated AFK entries' active status")
                except Exception as e:
                    logging.error(f"Error updating AFK statuses: {e}")

            # Start periodic AFK status update task
            self.update_afk_task = self.loop.create_task(self.update_afk_status_periodically())
            logging.info("Started periodic AFK status update task")

            logging.info("Starting to sync commands...")
            
            # Get the guild
            guild = discord.Object(id=GUILD_ID)
            logging.info(f"Target guild ID: {GUILD_ID}")
            
            # First, remove all commands globally and from the guild
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)
            
            logging.info("Cleared all existing commands")
            
            # Add commands manually
            @self.tree.command(name="afk", description="Set your AFK status", guild=guild)
            @app_commands.describe(
                start_date="Start date (DDMM, DD/MM or DD.MM)",
                start_time="Start time (HHMM or HH:MM)",
                end_date="End date (DDMM, DD/MM or DD.MM)",
                end_time="End time (HHMM or HH:MM)",
                reason="Reason for being AFK"
            )
            async def afk_command(interaction, start_date: str, start_time: str, end_date: str, end_time: str, reason: str):
                await afk(interaction, start_date, start_time, end_date, end_time, reason)

            @self.tree.command(name="afkquick", description="Quickly set AFK status until end of day", guild=guild)
            @app_commands.describe(
                reason="Reason for being AFK",
                days="Optional: Number of days to be AFK (default: until end of today)"
            )
            async def afkquick_command(interaction, reason: str, days: int = None):
                await afkquick(interaction, reason, days)

            @self.tree.command(name="afkreturn", description="Return from AFK status", guild=guild)
            async def afkreturn_command(interaction):
                await afkreturn(interaction)

            @self.tree.command(name="afklist", description="List all AFK users", guild=guild)
            async def afklist_command(interaction):
                await afklist(interaction)

            @self.tree.command(name="afkmy", description="Show your active and scheduled AFK entries", guild=guild)
            async def afkmy_command(interaction):
                await afkmy(interaction)

            @self.tree.command(name="afkhistory", description="Show AFK history for a user", guild=guild)
            @app_commands.describe(user="The user to check history for")
            async def afkhistory_command(interaction, user: discord.Member):
                await afkhistory(interaction, user)

            @self.tree.command(name="afkdelete", description="Delete AFK entries (Admin only)", guild=guild)
            @app_commands.describe(
                user="The user whose AFK entries you want to delete",
                all_entries="Delete all entries for this user? If false, only deletes active entries"
            )
            @has_required_role()
            async def afkdelete_command(interaction, user: discord.Member, all_entries: bool = False):
                await afkdelete(interaction, user, all_entries)

            @self.tree.command(name="afkstats", description="Show AFK statistics", guild=guild)
            async def afkstats_command(interaction):
                await afkstats(interaction)

            @self.tree.command(name="getmembers", description="List all members with a specific role", guild=guild)
            @app_commands.describe(role="The role to check members for")
            async def getmembers_command(interaction, role: discord.Role):
                await getmembers(interaction, role)

            @self.tree.command(name="afkremove", description="Remove one of your future AFK entries", guild=guild)
            @app_commands.describe(afk_id="The ID of the AFK entry to remove (use /afkmy to see your entries)")
            async def afkremove_command(interaction, afk_id: int):
                await afkremove(interaction, afk_id)

            @self.tree.command(name="checksignups", description="Compares role members with Raid-Helper signups", guild=guild)
            @app_commands.describe(
                role="The role to check members for",
                event_id="The Raid-Helper event ID"
            )
            @has_required_role()
            async def checksignups_command(interaction, role: discord.Role, event_id: str):
                await checksignups(interaction, role, event_id)

            # Test command to verify command syncing
            @self.tree.command(name="rqping", description="Test command - responds with Pong!", guild=guild)
            async def rqping_command(interaction):
                await interaction.response.send_message("Pong!")

            # Sync the commands
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

    async def update_afk_status_periodically(self):
        """Update AFK statuses every minute."""
        await self.wait_until_ready()  # Wait until bot is ready
        while not self.is_closed():
            try:
                with get_db_session() as db:
                    update_afk_active_status(db)
                    logging.debug("Updated AFK statuses")
            except Exception as e:
                logging.error(f"Error in periodic AFK status update: {e}")
            
            await asyncio.sleep(60)  # Wait for 60 seconds

    async def close(self):
        """Clean up when bot is shutting down."""
        if self.update_afk_task:
            self.update_afk_task.cancel()
        await super().close()

def has_required_role():
    """Check if user has required role."""
    async def predicate(interaction: discord.Interaction):
        return any(role.id in [ADMIN_ROLE_ID, OFFICER_ROLE_ID] for role in interaction.user.roles)
    return app_commands.check(predicate)

async def afk(interaction, start_date, start_time, end_date, end_time, reason):
    """Set AFK status."""
    try:
        # Parse dates and times
        start_datetime = parse_datetime(start_date, start_time)
        end_datetime = parse_datetime(end_date, end_time)
        current_time = datetime.utcnow()

        # If start date is in the past
        if start_datetime < current_time:
            # Calculate how many days in the past
            days_in_past = (current_time - start_datetime).days
            
            # If within last 14 days or would be scheduled for next year, reject it
            if days_in_past <= 14:
                await interaction.response.send_message(
                    "❌ The start date/time cannot be in the past! Please check your date/time input.",
                    ephemeral=True
                )
                return
            else:
                await interaction.response.send_message(
                    "❌ The date you entered was in the past. Please enter a future date.\n"
                    "Tip: If you meant to schedule for today or upcoming days, make sure to use the correct year.",
                    ephemeral=True
                )
                return

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
            f"✅ Set AFK status for {interaction.user.display_name} (all times in UTC)\n"
            f"From: <t:{int(start_datetime.timestamp())}:f>\n"
            f"Until: <t:{int(end_datetime.timestamp())}:f>\n"
            f"Reason: {reason}"
        )

    except ValueError as e:
        await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)
    except Exception as e:
        logging.error(f"Error in afk command: {e}")
        await interaction.response.send_message(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )

async def afkreturn(interaction: discord.Interaction):
    """Return from AFK status."""
    try:
        with get_db_session() as db:
            # Get user from database
            user = get_or_create_user(
                db,
                str(interaction.user.id),
                interaction.user.name,
                interaction.user.display_name
            )
            
            # Update AFK entries
            updated = update_afk_status(db, user)
            
            if updated > 0:
                await interaction.response.send_message(
                    "✅ Welcome back! Your AFK status has been cleared.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ You don't have any active AFK entries.",
                    ephemeral=True
                )
                
    except Exception as e:
        logging.error(f"Error in afkreturn command: {e}")
        await interaction.response.send_message(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )

async def afklist(interaction: discord.Interaction):
    """List all AFK users."""
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

        with get_db_session() as db:
            # Create embed
            embed = discord.Embed(
                title="🕒 AFK Entries",
                description="Active and scheduled AFK entries (all times in UTC)",
                color=discord.Color.blue()
            )
            
            current_time = datetime.utcnow()
            found_entries = False

            if is_admin:
                # Show all clans for admins
                for clan_id, clan_name in [
                    (CLAN1_ROLE_ID, "Requiem Sun"),
                    (CLAN2_ROLE_ID, "Requiem Moon")
                ]:
                    entries = get_clan_active_and_future_afk(db, str(clan_id))
                    if entries:
                        found_entries = True
                        embed.add_field(
                            name=f"__**{clan_name}**__",
                            value="⎯" * 20,  # Divider line
                            inline=False
                        )
                        for user, afk in entries:
                            # Determine status
                            if current_time < afk.start_date:
                                status = "⚪ Scheduled"  # Future
                            elif current_time > afk.end_date:
                                status = "🔴 Expired"  # Expired
                            else:
                                status = "🟢 Active"  # Current

                            # Get user from Discord for display name
                            try:
                                member = await interaction.guild.fetch_member(int(user.discord_id))
                                user_name = member.display_name
                            except:
                                user_name = user.username

                            embed.add_field(
                                name=f"{status} - {user_name}",
                                value=(
                                    f"From: <t:{int(afk.start_date.timestamp())}:f>\n"
                                    f"Until: <t:{int(afk.end_date.timestamp())}:f>\n"
                                    f"Reason: {afk.reason if afk.reason else 'No reason provided'}"
                                ),
                                inline=False
                            )
            else:
                # Show only user's clan
                clan_name = "Requiem Sun" if user_clan_role_id == str(CLAN1_ROLE_ID) else "Requiem Moon"
                entries = get_clan_active_and_future_afk(db, user_clan_role_id)
                
                if entries:
                    found_entries = True
                    embed.add_field(
                        name=f"__**{clan_name}**__",
                        value="⎯" * 20,  # Divider line
                        inline=False
                    )
                    for user, afk in entries:
                        # Determine status
                        if current_time < afk.start_date:
                            status = "⚪ Scheduled"  # Future
                        elif current_time > afk.end_date:
                            status = "🔴 Expired"  # Expired
                        else:
                            status = "🟢 Active"  # Current

                        # Get user from Discord for display name
                        try:
                            member = await interaction.guild.fetch_member(int(user.discord_id))
                            user_name = member.display_name
                        except:
                            user_name = user.username

                        embed.add_field(
                            name=f"{status} - {user_name}",
                            value=(
                                f"From: <t:{int(afk.start_date.timestamp())}:f>\n"
                                f"Until: <t:{int(afk.end_date.timestamp())}:f>\n"
                                f"Reason: {afk.reason if afk.reason else 'No reason provided'}"
                            ),
                            inline=False
                        )

            if not found_entries:
                await interaction.response.send_message(
                    "📝 No active or scheduled AFK entries found.",
                    ephemeral=True
                )
                return

            await interaction.response.send_message(embed=embed)
            
    except Exception as e:
        logging.error(f"Error in afklist command: {e}")
        await interaction.response.send_message(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )

async def afkhistory(interaction: discord.Interaction, user: discord.Member):
    """Show AFK history for a user."""
    try:
        with get_db_session() as db:
            # Get user from database
            db_user = get_or_create_user(
                db,
                str(user.id),
                user.name,
                user.display_name
            )
            
            # Get user's AFK history
            afk_entries = get_user_afk_history(db, db_user, limit=10)
            
            if not afk_entries:
                await interaction.response.send_message(
                    f"📝 No AFK history found for {user.display_name}.",
                    ephemeral=True
                )
                return
                
            # Create embed
            embed = discord.Embed(
                title=f"🕒 AFK History - {user.display_name}",
                description="Showing last 10 AFK entries (all times in UTC)",
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
                
            await interaction.response.send_message(embed=embed)
            
    except Exception as e:
        logging.error(f"Error in afkhistory command: {e}")
        await interaction.response.send_message(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )

async def afkdelete(interaction: discord.Interaction, user: discord.Member, all_entries: bool = False):
    """Delete AFK entries for a user."""
    try:
        # Check if user has required role
        if not any(role.id in [ADMIN_ROLE_ID, OFFICER_ROLE_ID] for role in interaction.user.roles):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command!",
                ephemeral=True
            )
            return
            
        with get_db_session() as db:
            # Get user from database
            db_user = get_or_create_user(
                db,
                str(user.id),
                user.name,
                user.display_name
            )
            
            # Delete AFK entries
            deleted = delete_afk_entries(db, db_user, all_entries)
            
            if deleted > 0:
                await interaction.response.send_message(
                    f"✅ Deleted {deleted} AFK {'entries' if deleted > 1 else 'entry'} for {user.display_name}.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"❌ No {'AFK entries' if all_entries else 'active AFK entries'} found for {user.display_name}.",
                    ephemeral=True
                )
                
    except Exception as e:
        logging.error(f"Error in afkdelete command: {e}")
        await interaction.response.send_message(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )

async def afkstats(interaction: discord.Interaction):
    """Show AFK statistics."""
    try:
        with get_db_session() as db:
            # Get statistics
            stats = get_afk_statistics(db)
            
            if not stats:
                await interaction.response.send_message(
                    "📝 No AFK statistics available.",
                    ephemeral=True
                )
                return
                
            # Create embed
            embed = discord.Embed(
                title="📊 AFK Statistics",
                description="Global AFK statistics",
                color=discord.Color.blue()
            )
            
            # Add fields
            embed.add_field(
                name="Total Entries",
                value=str(stats["total_entries"]),
                inline=True
            )
            embed.add_field(
                name="Active Entries",
                value=str(stats["active_entries"]),
                inline=True
            )
            embed.add_field(
                name="Total Users",
                value=str(stats["total_users"]),
                inline=True
            )
            
            # Add average duration if available
            if stats["average_duration"]:
                hours = stats["average_duration"].total_seconds() / 3600
                embed.add_field(
                    name="Average Duration",
                    value=f"{hours:.1f} hours",
                    inline=True
                )
            
            await interaction.response.send_message(embed=embed)
            
    except Exception as e:
        logging.error(f"Error in afkstats command: {e}")
        await interaction.response.send_message(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )

async def afkmy(interaction: discord.Interaction):
    """Show personal AFK entries."""
    try:
        with get_db_session() as db:
            # Get user's AFK entries
            user = get_or_create_user(
                db,
                str(interaction.user.id),
                interaction.user.name,
                interaction.user.display_name
            )
            afk_entries = get_user_active_and_future_afk(db, user.id)

            if not afk_entries:
                await interaction.response.send_message("You have no active or scheduled AFK entries.", ephemeral=True)
                return
                
            # Create embed
            embed = discord.Embed(
                title="🕒 Your AFK Entries",
                description="Your active and scheduled AFK entries (all times in UTC)\nUse `/afkremove <ID>` to remove a future entry",
                color=discord.Color.blue()
            )
            
            current_time = datetime.utcnow()
            
            # Add fields for each AFK entry
            for afk in afk_entries:
                # Determine status
                if current_time < afk.start_date:
                    status = "⚪ Scheduled"  # Future
                elif current_time > afk.end_date:
                    status = "🔴 Expired"  # Expired
                else:
                    status = "🟢 Active"  # Current
                
                embed.add_field(
                    name=f"{status} - ID: {afk.id}",
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

async def getmembers(interaction: discord.Interaction, role: discord.Role):
    """List all members with a specific role."""
    try:
        logging.info(f"Getting members for role {role.name} (ID: {role.id})")
        
        # Get Discord members with this role
        discord_members = role.members
        logging.info(f"Found {len(discord_members)} members in Discord with role {role.name}")
        
        if not discord_members:
            await interaction.response.send_message(
                f"No members found with role {role.name}",
                ephemeral=True
            )
            return

        # Create message
        message = f"**Members with role {role.name} ({len(discord_members)}):**\n\n"
        for member in sorted(discord_members, key=lambda x: x.display_name.lower()):
            if member.display_name != member.name:
                message += f"{member.display_name} ({member.name})\n"
            else:
                message += f"{member.name}\n"

        # Send message (split if too long)
        if len(message) > 2000:
            chunks = [message[i:i+1900] for i in range(0, len(message), 1900)]
            for i, chunk in enumerate(chunks):
                if i == 0:
                    await interaction.response.send_message(chunk)
                else:
                    await interaction.followup.send(chunk)
        else:
            await interaction.response.send_message(message)

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

async def afkquick(interaction: discord.Interaction, reason: str, days: int = None):
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
            f"✅ Quick AFK set for {interaction.user.display_name} (all times in UTC)\n"
            f"From: <t:{int(start_datetime.timestamp())}:f>\n"
            f"Until: <t:{int(end_datetime.timestamp())}:f>\n"
            f"Reason: {reason}"
        )

    except Exception as e:
        await interaction.response.send_message(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )

async def afkremove(interaction: discord.Interaction, afk_id: int):
    """Remove a future AFK entry."""
    try:
        with get_db_session() as db:
            # Get user from database
            user = get_or_create_user(
                db,
                str(interaction.user.id),
                interaction.user.name,
                interaction.user.display_name
            )
            
            # Try to remove the AFK entry
            remove_future_afk(db, user, afk_id)
            
            await interaction.response.send_message(
                "✅ Successfully removed your future AFK entry!",
                ephemeral=True
            )
            
    except ValueError as e:
        await interaction.response.send_message(
            f"❌ {str(e)}",
            ephemeral=True
        )
    except Exception as e:
        logging.error(f"Error in afkremove command: {e}")
        await interaction.response.send_message(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )

async def checksignups(interaction: discord.Interaction, role: discord.Role, event_id: str):
    """Compare role members with Raid-Helper signups."""
    try:
        await interaction.response.defer()

        # Get all members with their IDs from the role
        role_members = {}
        for member in role.members:
            display_name = member.nick if member.nick else (member.global_name if member.global_name else member.name)
            role_members[str(member.id)] = display_name

        # Construct Raid-Helper API URL
        api_url = f"https://raid-helper.dev/api/v2/events/{event_id}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as response:
                    if response.status == 200:
                        event_data = await response.json()
                        
                        # Get signed up player IDs from Raid-Helper
                        signed_up_ids = set()
                        if 'signUps' in event_data:
                            for signup in event_data['signUps']:
                                if 'userId' in signup:
                                    signed_up_ids.add(str(signup['userId']))

                        # Find members who haven't signed up by comparing IDs
                        not_signed_up = []
                        for user_id, display_name in role_members.items():
                            if user_id not in signed_up_ids:
                                not_signed_up.append(display_name)

                        # Sort names alphabetically
                        not_signed_up.sort()

                        # Create message
                        message = f"**Raid-Helper Comparison Results for '{role.name}':**\n"
                        message += f"Event ID: {event_id}\n\n"
                        
                        if not_signed_up:
                            message += "**Not Signed Up Players:**\n"
                            for name in not_signed_up:
                                message += f"{name}\n"
                        else:
                            message += "All players are signed up! 🎉\n"

                        message += f"\n**Statistics:**\n"
                        message += f"Signed up: {len(signed_up_ids)}\n"
                        message += f"Not signed up: {len(not_signed_up)}\n"
                        message += f"Total Discord members: {len(role_members)}\n"

                    else:
                        message = f"Error loading Raid-Helper data: HTTP {response.status}"
        except Exception as e:
            message = f"Error processing Raid-Helper data: {str(e)}"

        # Send message (split if too long)
        if len(message) > 2000:
            chunks = [message[i:i+1900] for i in range(0, len(message), 1900)]
            for chunk in chunks:
                await interaction.followup.send(chunk)
        else:
            await interaction.followup.send(message)

    except Exception as e:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"An error occurred: {str(e)}")
        else:
            await interaction.followup.send(f"An error occurred: {str(e)}")

def run_bot():
    """Run the bot."""
    try:
        # Initialize database
        logging.info("Initializing database...")
        init_db()
        logging.info("Database initialized successfully")
        
        # Update AFK statuses
        with get_db_session() as db:
            try:
                update_afk_active_status(db)
                logging.info("Updated AFK entries' active status")
            except Exception as e:
                logging.error(f"Error updating AFK statuses: {e}")
        
        # Create bot instance
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        bot = RequiemBot(command_prefix="!", intents=intents)
        
        # Run the bot with auto-reconnect enabled
        bot.run(TOKEN, reconnect=True)
    except Exception as e:
        logging.error(f"Error during bot startup: {e}")
        # Wait for a moment before attempting to restart
        time.sleep(5)
        run_bot()  # Recursive restart

if __name__ == "__main__":
    run_bot() 