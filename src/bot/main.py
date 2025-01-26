"""Main Discord bot module."""
import os
import logging
from datetime import datetime, timedelta
import time
import asyncio
import aiohttp
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from sqlalchemy.orm import aliased
from sqlalchemy import and_, or_, create_engine

from src.database.connection import get_db_session, init_db
from src.database.models import Base, User, AFKEntry, RaidHelperEvent, RaidHelperSignup, ClanMembership, GuildWelcomeMessage, ProcessedEvent
from src.database.operations import (delete_afk_entries, get_active_afk,
                                   get_afk_statistics, get_clan_members,
                                   get_or_create_user, get_user_afk_history,
                                   set_afk, track_raid_signup, update_afk_status,
                                   update_afk_active_status, get_user_active_and_future_afk,
                                   get_clan_active_and_future_afk, remove_future_afk,
                                   sync_clan_memberships, get_clan_membership_history,
                                   extend_afk, set_guild_welcome_message, get_guild_welcome_message,
                                   add_user_to_guild, get_all_welcome_messages, remove_user_from_guild,
                                   get_user_event_history, mark_event_as_processed)
from src.utils.time_parser import parse_date, parse_time, parse_datetime
from src.services.raidhelper import RaidHelperService
from src.services.googlesheets import GoogleSheetsService

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
CLAN1_ROLE_ID = int(os.getenv("CLAN1_ROLE_ID", "0"))  # Clan 1
CLAN2_ROLE_ID = int(os.getenv("CLAN2_ROLE_ID", "0"))  # Clan 2
BOT_NAME = os.getenv("BOT_NAME", "Requiem Bot")

# Additional role IDs for clans
CLAN1_ADDITIONAL_ROLES = [int(role_id.strip()) for role_id in os.getenv("CLAN1_ADDITIONAL_ROLES", "").split(",") if role_id.strip()]
CLAN2_ADDITIONAL_ROLES = [int(role_id.strip()) for role_id in os.getenv("CLAN2_ADDITIONAL_ROLES", "").split(",") if role_id.strip()]

# Clan Names and Aliases
CLAN1_NAME = os.getenv("CLAN1_NAME", "Clan 1")
CLAN2_NAME = os.getenv("CLAN2_NAME", "Clan 2")
CLAN1_ALIASES = [alias.strip().lower() for alias in os.getenv("CLAN1_ALIASES", "clan1,c1").split(",")]
CLAN2_ALIASES = [alias.strip().lower() for alias in os.getenv("CLAN2_ALIASES", "clan2,c2").split(",")]

# Initialize database engine
DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "requiem_bot")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL)

class RequiemBot(commands.Bot):
    """Main bot class."""
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(command_prefix="!", intents=intents)
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.raidhelper = RaidHelperService()

    async def setup_hook(self):
        """Initialize the bot and set up commands."""
        logging.info("Initializing database...")
        Base.metadata.create_all(engine)
        logging.info("Database initialized successfully")

        # Update AFK entries' active status
        with get_db_session() as db:
            update_afk_active_status(db)
        logging.info("Updated AFK entries' active status")

        # Start background tasks
        self.sync_clan_memberships.start()
        self.update_afk_status_task.start()

        # Start to sync commands
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

        @self.tree.command(name="afkdelete", description="Delete AFK entries (Admin only, use /afkhistory to get the ID)", guild=guild)
        @app_commands.describe(
            user="The user whose AFK entries you want to delete",
            all_entries="Delete all entries for this user? If false, only deletes active entries",
            afk_id="Optional: Specific AFK entry ID to delete (overrides all_entries)"
        )
        @has_required_role()
        async def afkdelete_command(interaction, user: discord.Member, all_entries: bool = False, afk_id: Optional[int] = None):
            await afkdelete(interaction, user, all_entries, afk_id)

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

        @self.tree.command(name="afkextend", description="Extend an existing AFK entry (use /afkmy to get the ID)", guild=guild)
        @app_commands.describe(
            afk_id="The ID of the AFK entry to extend (use /afkmy to see your entries)",
            hours="Number of hours to extend by"
        )
        async def afkextend_command(interaction: discord.Interaction, afk_id: int, hours: int):
            await afkextend(interaction, afk_id, hours)

        @self.tree.command(
            name="clanhistory",
            description="Show clan membership history for a user (Admin/Officer only)",
            guild=guild
        )
        @app_commands.describe(
            user="The user to check history for (optional, defaults to yourself)",
            include_inactive="Include past memberships (default: false)"
        )
        @has_required_role()
        async def clanhistory_command(
            interaction: discord.Interaction,
            user: Optional[discord.Member] = None,
            include_inactive: bool = False
        ):
            await clan_history(interaction, user, include_inactive)

        @self.tree.command(
            name="clanchanges",
            description="Show recent clan membership changes (Admin/Officer only)",
            guild=guild
        )
        @app_commands.describe(
            clan="The clan to check changes for (optional, shows all clans if not specified)",
            days="Number of days to look back (default: 7)"
        )
        @has_required_role()
        async def clanchanges_command(
            interaction: discord.Interaction,
            clan: Optional[str] = None,
            days: int = 7
        ):
            await clan_changes(interaction, clan, days)

        @self.tree.command(
            name="guildadd",
            description="Add a user to a guild (Admin/Officer only)",
            guild=guild
        )
        @app_commands.describe(
            user="The user to add to the guild",
            guild="The guild to add the user to",
            send_welcome="Send welcome message to user (default: True)"
        )
        @has_required_role()
        async def guildadd_command(
            interaction: discord.Interaction,
            user: discord.Member,
            guild: str,
            send_welcome: bool = True
        ):
            await guildadd(interaction, user, guild, send_welcome)

        @self.tree.command(
            name="welcomeset",
            description="Set welcome message for a guild (Admin only)",
            guild=guild
        )
        @app_commands.describe(
            guild="The guild to set the welcome message for",
            message="The welcome message to send to new members"
        )
        @has_admin_role()
        async def welcomeset_command(
            interaction: discord.Interaction,
            guild: str,
            message: str
        ):
            await setwelcome(interaction, guild, message)

        @self.tree.command(
            name="welcomeshow",
            description="Show welcome messages for all guilds (Admin/Officer only)",
            guild=guild
        )
        @app_commands.describe(
            guild="Optional: Show message for specific guild only"
        )
        @has_required_role()
        async def welcomeshow_command(
            interaction: discord.Interaction,
            guild: Optional[str] = None
        ):
            await welcomeshow(interaction, guild)

        @self.tree.command(
            name="guildremove",
            description="Remove a user from a guild (Admin/Officer only)",
            guild=guild
        )
        @app_commands.describe(
            user="The user to remove from the guild",
            guild="The guild to remove the user from",
            kick_from_discord="Also kick the user from Discord (default: False)"
        )
        @has_required_role()
        async def guildremove_command(
            interaction: discord.Interaction,
            user: discord.Member,
            guild: str,
            kick_from_discord: bool = False
        ):
            await guildremove(interaction, user, guild, kick_from_discord)

        @self.tree.command(
            name="eventhistory",
            description="Show event history for a user",
            guild=guild
        )
        @app_commands.describe(
            user="The user whose history should be shown",
            limit="Number of events to show (default: 10)"
        )
        async def eventhistory_command(interaction: discord.Interaction, user: discord.Member, limit: int = 10):
            await eventhistory(interaction, user, limit)

        @self.tree.command(
            name="activityedit",
            description="Edit a user's activity status for an event (Admin/Officer only)",
            guild=guild
        )
        @app_commands.describe(
            event_id="The event ID",
            user="The user whose status should be changed",
            status="The new status (Present, Absent, No Show)"
        )
        @app_commands.choices(status=[
            app_commands.Choice(name="Present", value="Present"),
            app_commands.Choice(name="Absent", value="Absent"),
            app_commands.Choice(name="No Show", value="No Show")
        ])
        @has_required_role()
        async def activityedit_command(
            interaction: discord.Interaction,
            event_id: str,
            user: discord.Member,
            status: str
        ):
            """Edit a user's activity status for a specific event."""
            await interaction.response.defer()

            try:
                with get_db_session() as session:
                    # Check if event exists
                    event = session.query(RaidHelperEvent).filter(
                        RaidHelperEvent.id == event_id
                    ).first()

                    if not event:
                        await interaction.followup.send(
                            f"❌ Event with ID {event_id} not found.",
                            ephemeral=True
                        )
                        return

                    # Find user's signup entry
                    signup = session.query(RaidHelperSignup).filter(
                        RaidHelperSignup.event_id == event_id,
                        RaidHelperSignup.user_id == str(user.id)
                    ).first()

                    if not signup:
                        await interaction.followup.send(
                            f"❌ No signup found for {user.display_name} in this event.",
                            ephemeral=True
                        )
                        return

                    # Store old status for message
                    old_status = signup.class_name or "No signup"

                    # Update status in database
                    signup.class_name = status
                    signup.updated_at = datetime.utcnow()
                    session.commit()

                    # Update status in Google Sheet
                    sheets_service = GoogleSheetsService()
                    sheet_updated = sheets_service.update_status_in_sheet(event_id, str(user.id), status)

                    # Create embed message for confirmation
                    embed = discord.Embed(
                        title="Activity Status Updated",
                        color=discord.Color.green() if sheet_updated else discord.Color.orange(),
                        timestamp=datetime.utcnow()
                    )
                    embed.add_field(name="Event", value=event.title, inline=False)
                    embed.add_field(name="User", value=user.mention, inline=True)
                    embed.add_field(name="Old Status", value=old_status, inline=True)
                    embed.add_field(name="New Status", value=status, inline=True)
                    
                    if not sheet_updated:
                        embed.add_field(
                            name="⚠️ Warning",
                            value="Status was updated in database but could not be updated in the Google Sheet. The sheet will be updated on next sync.",
                            inline=False
                        )
                    
                    embed.set_footer(text=f"Event ID: {event_id}")
                    await interaction.followup.send(embed=embed)

            except Exception as e:
                logging.error(f"Error in activityedit command: {e}")
                await interaction.followup.send(
                    "❌ An error occurred while updating the activity status.",
                    ephemeral=True
                )

        # Sync the commands
        synced = await self.tree.sync(guild=guild)
        
        logging.info(f"Successfully synced {len(synced)} command(s) to guild {GUILD_ID}")
        for command in synced:
            logging.info(f"Synced command: {command.name}")

    @tasks.loop(minutes=1)
    async def sync_clan_memberships(self):
        """Sync clan memberships periodically."""
        try:
            if not self.is_ready():
                logging.warning("Bot not ready yet, skipping clan sync")
                return
            
            guild = self.get_guild(GUILD_ID)
            if not guild:
                logging.error(f"Could not fetch guild with ID {GUILD_ID}")
                return
            
            with get_db_session() as db:
                # Sync Clan 1
                clan1_role = guild.get_role(CLAN1_ROLE_ID)
                if clan1_role:
                    current_members = []
                    for member in clan1_role.members:
                        current_members.append(str(member.id))
                        # Update user data
                        get_or_create_user(
                            db,
                            str(member.id),
                            member.name,
                            member.display_name,
                            str(CLAN1_ROLE_ID)
                        )
                    
                    joined, left = sync_clan_memberships(db, str(CLAN1_ROLE_ID), current_members)
                    
                    if joined:
                        logging.info(f"New {CLAN1_NAME} members: {', '.join(joined)}")
                    if left:
                        logging.info(f"Left {CLAN1_NAME} members: {', '.join(left)}")
                
                # Sync Clan 2
                clan2_role = guild.get_role(CLAN2_ROLE_ID)
                if clan2_role:
                    current_members = []
                    for member in clan2_role.members:
                        current_members.append(str(member.id))
                        # Update user data
                        get_or_create_user(
                            db,
                            str(member.id),
                            member.name,
                            member.display_name,
                            str(CLAN2_ROLE_ID)
                        )
                    
                    joined, left = sync_clan_memberships(db, str(CLAN2_ROLE_ID), current_members)
                    
                    if joined:
                        logging.info(f"New {CLAN2_NAME} members: {', '.join(joined)}")
                    if left:
                        logging.info(f"Left {CLAN2_NAME} members: {', '.join(left)}")
        
        except Exception as e:
            logging.error(f"Error syncing clan memberships: {e}")

    @tasks.loop(minutes=1)
    async def update_afk_status_task(self):
        """Update AFK status periodically."""
        try:
            if not self.is_ready():
                return
            
            with get_db_session() as db:
                update_afk_active_status(db)
        
        except Exception as e:
            logging.error(f"Error updating AFK status: {e}")

    @sync_clan_memberships.before_loop
    async def before_sync_clan_memberships(self):
        """Wait for the bot to be ready before starting the sync task."""
        await self.wait_until_ready()

    @update_afk_status_task.before_loop
    async def before_update_afk_status(self):
        """Wait for the bot to be ready before starting the update task."""
        await self.wait_until_ready()

    async def on_ready(self):
        """Called when the bot is ready."""
        logging.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logging.info(f"Connected to guild ID: {GUILD_ID}")
        
        # Update bot name if needed
        try:
            if self.user.name != BOT_NAME:
                await self.user.edit(username=BOT_NAME)
                logging.info(f"Updated bot name to: {BOT_NAME}")
        except Exception as e:
            logging.error(f"Error updating bot name: {e}")
            
        logging.info("------")

def has_required_role():
    """Check if user has required role."""
    async def predicate(interaction: discord.Interaction):
        return any(role.id in [ADMIN_ROLE_ID, OFFICER_ROLE_ID] for role in interaction.user.roles)
    return app_commands.check(predicate)

def has_admin_role():
    """Check if user has admin role."""
    async def predicate(interaction: discord.Interaction):
        return any(role.id == ADMIN_ROLE_ID for role in interaction.user.roles)
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

        await interaction.response.defer()

        with get_db_session() as db:
            current_time = datetime.utcnow()
            found_entries = False
            embeds = []
            current_embed = None
            field_count = 0

            if is_admin:
                # Show all clans for admins
                for clan_id, clan_name in [
                    (CLAN1_ROLE_ID, CLAN1_NAME),
                    (CLAN2_ROLE_ID, CLAN2_NAME)
                ]:
                    entries = get_clan_active_and_future_afk(db, str(clan_id))
                    if entries:
                        found_entries = True
                        
                        # Create new embed if needed
                        if current_embed is None or field_count >= 24:
                            current_embed = discord.Embed(
                                title="🕒 AFK Entries",
                                description="Active and scheduled AFK entries (all times in UTC)",
                                color=discord.Color.blue()
                            )
                            embeds.append(current_embed)
                            field_count = 0

                        current_embed.add_field(
                            name=f"__**{clan_name}**__",
                            value="⎯" * 20,  # Divider line
                            inline=False
                        )
                        field_count += 1

                        for user, afk in entries:
                            # Create new embed if needed
                            if field_count >= 24:
                                current_embed = discord.Embed(
                                    title="🕒 AFK Entries (Continued)",
                                    description="Active and scheduled AFK entries (all times in UTC)",
                                    color=discord.Color.blue()
                                )
                                embeds.append(current_embed)
                                field_count = 0

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

                            current_embed.add_field(
                                name=f"{status} - {user_name}",
                                value=(
                                    f"From: <t:{int(afk.start_date.timestamp())}:f>\n"
                                    f"Until: <t:{int(afk.end_date.timestamp())}:f>\n"
                                    f"Reason: {afk.reason if afk.reason else 'No reason provided'}"
                                ),
                                inline=False
                            )
                            field_count += 1
            else:
                # Show only user's clan
                clan_name = CLAN1_NAME if user_clan_role_id == str(CLAN1_ROLE_ID) else CLAN2_NAME
                entries = get_clan_active_and_future_afk(db, user_clan_role_id)
                
                if entries:
                    found_entries = True
                    current_embed = discord.Embed(
                        title="🕒 AFK Entries",
                        description="Active and scheduled AFK entries (all times in UTC)",
                        color=discord.Color.blue()
                    )
                    embeds.append(current_embed)
                    field_count = 0

                    current_embed.add_field(
                        name=f"__**{clan_name}**__",
                        value="⎯" * 20,  # Divider line
                        inline=False
                    )
                    field_count += 1

                    for user, afk in entries:
                        # Create new embed if needed
                        if field_count >= 24:
                            current_embed = discord.Embed(
                                title="🕒 AFK Entries (Continued)",
                                description="Active and scheduled AFK entries (all times in UTC)",
                                color=discord.Color.blue()
                            )
                            embeds.append(current_embed)
                            field_count = 0

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

                        current_embed.add_field(
                            name=f"{status} - {user_name}",
                            value=(
                                f"From: <t:{int(afk.start_date.timestamp())}:f>\n"
                                f"Until: <t:{int(afk.end_date.timestamp())}:f>\n"
                                f"Reason: {afk.reason if afk.reason else 'No reason provided'}"
                            ),
                            inline=False
                        )
                        field_count += 1

            if not found_entries:
                await interaction.followup.send(
                    "📝 No active or scheduled AFK entries found.",
                    ephemeral=True
                )
                return

            # Send all embeds
            for i, embed in enumerate(embeds):
                if i == 0:
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send(embed=embed)
            
    except Exception as e:
        logging.error(f"Error in afklist command: {e}")
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
                    name=f"{status} - ID: {afk.id}",
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

async def afkdelete(interaction: discord.Interaction, user: discord.Member, all_entries: bool = False, afk_id: Optional[int] = None):
    """Delete AFK entries for a user."""
    try:
        # Check if user has required role
        if not any(role.id in [ADMIN_ROLE_ID, OFFICER_ROLE_ID] for role in interaction.user.roles):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command!",
                ephemeral=True
            )
            return

        # Check if at least one optional parameter is provided
        if not all_entries and afk_id is None:
            await interaction.response.send_message(
                "❌ Please specify either `all_entries:true` to delete all entries, or provide a specific `afk_id` to delete.\n"
                "You can find the AFK ID using the `/afkhistory` command.",
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
            deleted = delete_afk_entries(db, db_user, all_entries, afk_id)
            
            if deleted > 0:
                if afk_id:
                    await interaction.response.send_message(
                        f"✅ Successfully deleted AFK entry {afk_id} for {user.display_name}.",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        f"✅ Deleted {deleted} AFK {'entries' if deleted > 1 else 'entry'} for {user.display_name}.",
                        ephemeral=True
                    )
            else:
                if afk_id:
                    await interaction.response.send_message(
                        f"❌ No AFK entry found with ID {afk_id} for {user.display_name}.",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        f"❌ No AFK entries found for {user.display_name}.",
                        ephemeral=True
                    )
                
    except ValueError as e:
        await interaction.response.send_message(
            f"❌ {str(e)}",
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

async def clan_history(
    interaction: discord.Interaction,
    user: Optional[discord.Member] = None,
    include_inactive: bool = False
):
    """Show clan membership history for a user."""
    try:
        with get_db_session() as db:
            # If no user specified, use the command invoker
            target_user = user or interaction.user
            
            # Get membership history
            history = get_clan_membership_history(
                db,
                discord_id=str(target_user.id),
                include_inactive=include_inactive
            )
            
            if not history:
                await interaction.response.send_message(
                    f"{target_user.display_name} has no clan membership history.",
                    ephemeral=True
                )
                return
            
            # Create embed
            embed = discord.Embed(
                title=f"Clan History for {target_user.display_name}",
                color=discord.Color.blue()
            )
            
            for user_obj, membership in history:
                clan_name = (
                    CLAN1_NAME if membership.clan_role_id == str(CLAN1_ROLE_ID) else
                    CLAN2_NAME if membership.clan_role_id == str(CLAN2_ROLE_ID) else
                    membership.clan_role_id
                )
                
                status = "Active" if membership.is_active else "⚫ Inactive"
                joined = f"<t:{int(membership.joined_at.timestamp())}:f>"
                
                # Only show left date for inactive memberships
                value = f"Joined: {joined}"
                if not membership.is_active and membership.left_at:
                    value += f"\nLeft: <t:{int(membership.left_at.timestamp())}:f>"
                
                embed.add_field(
                    name=f"{clan_name} ({status})",
                    value=value,
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed)
    
    except Exception as e:
        logging.error(f"Error showing clan history: {e}")
        await interaction.response.send_message(
            "An error occurred. Please try again later.",
            ephemeral=True
        )

async def clan_changes(
    interaction: discord.Interaction,
    clan: Optional[str] = None,
    days: int = 7
):
    """Show recent clan membership changes."""
    try:
        with get_db_session() as db:
            # Convert clan name to role ID
            clan_role_id = None
            if clan:
                clan = clan.lower()
                if clan in CLAN1_ALIASES:
                    clan_role_id = str(CLAN1_ROLE_ID)
                elif clan in CLAN2_ALIASES:
                    clan_role_id = str(CLAN2_ROLE_ID)
            
            # Calculate date range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            # Get changes
            changes = get_clan_membership_history(
                db,
                clan_role_id=clan_role_id,
                start_date=start_date,
                end_date=end_date,
                include_inactive=True
            )
            
            if not changes:
                await interaction.response.send_message(
                    f"No changes in the last {days} days.",
                    ephemeral=True
                )
                return
            
            # Create embed
            embed = discord.Embed(
                title=f"Clan Changes in the Last {days} Days",
                color=discord.Color.blue()
            )
            
            for user_obj, membership in changes:
                clan_name = (
                    CLAN1_NAME if membership.clan_role_id == str(CLAN1_ROLE_ID) else
                    CLAN2_NAME if membership.clan_role_id == str(CLAN2_ROLE_ID) else
                    membership.clan_role_id
                )
                
                member = interaction.guild.get_member(int(user_obj.discord_id))
                user_name = member.display_name if member else user_obj.display_name
                
                if membership.left_at and membership.left_at >= start_date:
                    # Member left during the period
                    embed.add_field(
                        name=f"🔴 {user_name} left {clan_name}",
                        value=f"<t:{int(membership.left_at.timestamp())}:f>",
                        inline=False
                    )
                
                if membership.joined_at >= start_date:
                    # Member joined during the period
                    embed.add_field(
                        name=f"🟢 {user_name} joined {clan_name}",
                        value=f"<t:{int(membership.joined_at.timestamp())}:f>",
                        inline=False
                    )
            
            await interaction.response.send_message(embed=embed)
    
    except Exception as e:
        logging.error(f"Error showing clan changes: {e}")
        await interaction.response.send_message(
            "An error occurred. Please try again later.",
            ephemeral=True
        )

async def afkextend(interaction: discord.Interaction, afk_id: int, hours: int):
    """Extend an existing AFK entry."""
    try:
        if hours <= 0:
            await interaction.response.send_message(
                "❌ Number of hours must be positive!",
                ephemeral=True
            )
            return
            
        with get_db_session() as db:
            # Get user from database
            user = get_or_create_user(
                db,
                str(interaction.user.id),
                interaction.user.name,
                interaction.user.display_name
            )
            
            # Try to extend the AFK entry
            afk_entry = extend_afk(db, user, afk_id, hours)
            
            await interaction.response.send_message(
                f"✅ Successfully extended your AFK entry! (all times in UTC)\n"
                f"New end time: <t:{int(afk_entry.end_date.timestamp())}:f>",
                ephemeral=True
            )
            
    except ValueError as e:
        await interaction.response.send_message(
            f"❌ {str(e)}",
            ephemeral=True
        )
    except Exception as e:
        logging.error(f"Error in afkextend command: {e}")
        await interaction.response.send_message(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )

async def guildadd(
    interaction: discord.Interaction,
    user: discord.Member,
    guild: str,
    send_welcome: bool = True
):
    """Add a user to a guild."""
    try:
        # Convert guild name to role ID
        guild = guild.lower()
        if guild in CLAN1_ALIASES:
            guild_role_id = str(CLAN1_ROLE_ID)
            guild_name = CLAN1_NAME
            guild_role = interaction.guild.get_role(CLAN1_ROLE_ID)
            additional_role_ids = CLAN1_ADDITIONAL_ROLES
        elif guild in CLAN2_ALIASES:
            guild_role_id = str(CLAN2_ROLE_ID)
            guild_name = CLAN2_NAME
            guild_role = interaction.guild.get_role(CLAN2_ROLE_ID)
            additional_role_ids = CLAN2_ADDITIONAL_ROLES
        else:
            await interaction.response.send_message(
                f"❌ Invalid guild name. Please use one of: {', '.join(CLAN1_ALIASES + CLAN2_ALIASES)}",
                ephemeral=True
            )
            return

        with get_db_session() as db:
            # Get or create user in database
            db_user = get_or_create_user(
                db,
                str(user.id),
                user.name,
                user.display_name
            )
            
            try:
                # Add user to guild in database
                add_user_to_guild(db, db_user, guild_role_id)
                
                # Add main Discord role
                await user.add_roles(guild_role)
                
                # Add additional roles
                roles_added = [guild_role]
                for role_id in additional_role_ids:
                    role = interaction.guild.get_role(role_id)
                    if role and role not in user.roles:
                        await user.add_roles(role)
                        roles_added.append(role)
                
                # Send welcome message if enabled
                if send_welcome:
                    welcome_msg = get_guild_welcome_message(db, guild_role_id)
                    if welcome_msg:
                        try:
                            await user.send(welcome_msg)
                        except discord.Forbidden:
                            await interaction.followup.send(
                                "⚠️ Could not send welcome message to user (DMs might be disabled)",
                                ephemeral=True
                            )
                
                # Create success message with added roles
                roles_text = ", ".join(role.name for role in roles_added)
                await interaction.response.send_message(
                    f"✅ Successfully added {user.mention} to {guild_name}!\n"
                    f"Added roles: {roles_text}",
                    ephemeral=False
                )
                
            except ValueError as e:
                await interaction.response.send_message(
                    f"❌ {str(e)}",
                    ephemeral=True
                )
            
    except Exception as e:
        logging.error(f"Error in guildadd command: {e}")
        await interaction.response.send_message(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )

async def setwelcome(
    interaction: discord.Interaction,
    guild: str,
    message: str
):
    """Set welcome message for a guild."""
    try:
        # Convert guild name to role ID
        guild = guild.lower()
        if guild in CLAN1_ALIASES:
            guild_role_id = str(CLAN1_ROLE_ID)
            guild_name = CLAN1_NAME
        elif guild in CLAN2_ALIASES:
            guild_role_id = str(CLAN2_ROLE_ID)
            guild_name = CLAN2_NAME
        else:
            await interaction.response.send_message(
                f"❌ Invalid guild name. Please use one of: {', '.join(CLAN1_ALIASES + CLAN2_ALIASES)}",
                ephemeral=True
            )
            return

        # Preserve line breaks by replacing them with \n
        message = message.replace('\\n', '\n')

        with get_db_session() as db:
            # Set welcome message
            set_guild_welcome_message(db, guild_role_id, message)
            
            # Show preview of the message
            embed = discord.Embed(
                title=f"✅ Welcome Message Set for {guild_name}",
                description="Preview of how the message will appear:",
                color=discord.Color.green()
            )
            
            # Split message if too long
            if len(message) > 4096:
                parts = []
                remaining = message
                while remaining:
                    if len(remaining) > 1024:
                        split_index = remaining[:1024].rfind('\n')
                        if split_index == -1:
                            split_index = 1024
                        
                        parts.append(remaining[:split_index])
                        remaining = remaining[split_index:].strip()
                    else:
                        parts.append(remaining)
                        remaining = ""
                
                for i, part in enumerate(parts):
                    embed.add_field(
                        name="Message Preview" + (" (continued)" if i > 0 else ""),
                        value=part,
                        inline=False
                    )
            else:
                embed.description = message
            
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
            
    except Exception as e:
        logging.error(f"Error in setwelcome command: {e}")
        await interaction.response.send_message(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )

async def welcomeshow(
    interaction: discord.Interaction,
    guild: Optional[str] = None
):
    """Show welcome messages for all or specific guild."""
    try:
        # Convert guild name to role ID if specified
        guild_role_id = None
        if guild:
            guild = guild.lower()
            if guild in CLAN1_ALIASES:
                guild_role_id = str(CLAN1_ROLE_ID)
            elif guild in CLAN2_ALIASES:
                guild_role_id = str(CLAN2_ROLE_ID)
            else:
                await interaction.response.send_message(
                    f"❌ Invalid guild name. Please use one of: {', '.join(CLAN1_ALIASES + CLAN2_ALIASES)}",
                    ephemeral=True
                )
                return

        with get_db_session() as db:
            # Get welcome messages
            welcome_messages = get_all_welcome_messages(db)
            
            if not welcome_messages:
                await interaction.response.send_message(
                    "❌ No welcome messages found.",
                    ephemeral=True
                )
                return
            
            # Filter messages if guild specified
            if guild_role_id:
                welcome_messages = [msg for msg in welcome_messages if msg.guild_role_id == guild_role_id]
                if not welcome_messages:
                    await interaction.response.send_message(
                        f"❌ No welcome message found for specified guild.",
                        ephemeral=True
                    )
                    return

            await interaction.response.defer(ephemeral=True)
            
            for msg in welcome_messages:
                # Convert role ID to guild name
                if msg.guild_role_id == str(CLAN1_ROLE_ID):
                    guild_name = CLAN1_NAME
                elif msg.guild_role_id == str(CLAN2_ROLE_ID):
                    guild_name = CLAN2_NAME
                else:
                    guild_name = f"Unknown Guild (Role ID: {msg.guild_role_id})"
                
                # Create embed for each message
                embed = discord.Embed(
                    title=f"📝 Welcome Message - {guild_name}",
                    color=discord.Color.blue()
                )

                # Split message if too long
                message = msg.message
                parts = []
                
                # Split message into parts at line breaks or when too long
                remaining = message
                while remaining:
                    if len(remaining) > 1024:
                        # Try to split at a line break first
                        split_index = remaining[:1024].rfind('\n')
                        if split_index == -1:
                            # If no line break found, split at the last space
                            split_index = remaining[:1024].rfind(' ')
                            if split_index == -1:
                                split_index = 1024
                        
                        parts.append(remaining[:split_index])
                        remaining = remaining[split_index:].strip()
                    else:
                        parts.append(remaining)
                        remaining = ""
                
                # Add parts to embed with correct naming
                for i, part in enumerate(parts):
                    embed.add_field(
                        name=f"{guild_name} - Message{' (continued)' if i > 0 else ''}",
                        value=part,
                        inline=False
                    )
                
                # Add last updated timestamp
                embed.add_field(
                    name="Last Updated",
                    value=f"<t:{int(msg.updated_at.timestamp())}:f>",
                    inline=False
                )
                
                # Send embed
                if interaction.response.is_done():
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            
    except Exception as e:
        logging.error(f"Error in welcomeshow command: {e}")
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

async def guildremove(
    interaction: discord.Interaction,
    user: discord.Member,
    guild: str,
    kick_from_discord: bool = False
):
    """Remove a user from a guild."""
    try:
        # Convert guild name to role ID
        guild = guild.lower()
        if guild in CLAN1_ALIASES:
            guild_role_id = str(CLAN1_ROLE_ID)
            guild_name = CLAN1_NAME
            guild_role = interaction.guild.get_role(CLAN1_ROLE_ID)
            additional_role_ids = CLAN1_ADDITIONAL_ROLES
        elif guild in CLAN2_ALIASES:
            guild_role_id = str(CLAN2_ROLE_ID)
            guild_name = CLAN2_NAME
            guild_role = interaction.guild.get_role(CLAN2_ROLE_ID)
            additional_role_ids = CLAN2_ADDITIONAL_ROLES
        else:
            await interaction.response.send_message(
                f"❌ Invalid guild name. Please use one of: {', '.join(CLAN1_ALIASES + CLAN2_ALIASES)}",
                ephemeral=True
            )
            return

        with get_db_session() as db:
            # Get or create user in database
            db_user = get_or_create_user(
                db,
                str(user.id),
                user.name,
                user.display_name
            )
            
            try:
                # Remove user from guild in database
                remove_user_from_guild(db, db_user, guild_role_id)
                
                # Remove Discord roles
                roles_removed = []
                
                # Remove main guild role
                if guild_role in user.roles:
                    await user.remove_roles(guild_role)
                    roles_removed.append(guild_role)
                
                # Remove additional roles
                for role_id in additional_role_ids:
                    role = interaction.guild.get_role(role_id)
                    if role and role in user.roles:
                        await user.remove_roles(role)
                        roles_removed.append(role)
                
                # Create success message with removed roles
                roles_text = ", ".join(role.name for role in roles_removed)
                message = f"✅ Successfully removed {user.mention} from {guild_name}!\nRemoved roles: {roles_text}"
                
                # Kick user if requested
                if kick_from_discord:
                    try:
                        await user.kick(reason=f"Removed from {guild_name}")
                        message += "\nUser was kicked from the Discord server."
                    except discord.Forbidden:
                        message += "\n⚠️ Could not kick user (insufficient permissions)"
                    except Exception as e:
                        message += f"\n⚠️ Could not kick user: {str(e)}"
                
                await interaction.response.send_message(
                    message,
                    ephemeral=False
                )
                
            except ValueError as e:
                await interaction.response.send_message(
                    f"❌ {str(e)}",
                    ephemeral=True
                )
            
    except Exception as e:
        logging.error(f"Error in guildremove command: {e}")
        await interaction.response.send_message(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )

async def eventhistory(interaction: discord.Interaction, user: discord.Member, limit: int = 10):
    """Show event history for a user."""
    await interaction.response.defer()

    with get_db_session() as db:
        history = get_user_event_history(db, str(user.id), limit)
        
        if not history:
            await interaction.followup.send(f"{user.display_name} hat noch an keinen Events teilgenommen.")
            return
        
        # Create embed
        embed = discord.Embed(
            title=f"Event Historie für {user.display_name}",
            color=discord.Color.blue()
        )
        
        for signup in history:
            event = signup.event
            value = f"Status: {signup.status}\n"
            value += f"Klasse: {signup.class_name or 'N/A'}\n"
            value += f"Spec: {signup.spec_name or 'N/A'}\n"
            value += f"Position: {signup.position or 'N/A'}"
            
            embed.add_field(
                name=f"{event.title} ({event.start_time.strftime('%d.%m.%Y %H:%M')})",
                value=value,
                inline=False
            )
        
        await interaction.followup.send(embed=embed)

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
        
        # Create and run bot
        bot = RequiemBot()
        bot.run(TOKEN, reconnect=True)
        
    except Exception as e:
        logging.error(f"Error during bot startup: {e}")
        # Wait for a moment before attempting to restart
        time.sleep(5)
        run_bot()  # Recursive restart

if __name__ == "__main__":
    run_bot() 