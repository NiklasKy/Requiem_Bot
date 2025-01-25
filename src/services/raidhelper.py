"""RaidHelper API integration service."""
import os
import logging
from typing import Dict, List, Optional
import aiohttp
from datetime import datetime
import asyncio

from src.database.connection import get_db_session, SessionLocal
from src.database.operations import create_or_update_raidhelper_event, update_raidhelper_signups, get_active_raidhelper_events, mark_event_as_processed, is_event_processed
from src.database.models import RaidHelperEvent, RaidHelperSignup, User, GuildInfo, ClanMembership
from src.services.google_sheets import GoogleSheetsService

class RaidHelperService:
    """Service for interacting with the RaidHelper API."""
    
    def __init__(self):
        """Initialize the RaidHelper service."""
        self.server_id = os.getenv("RAIDHELPER_SERVER_ID")
        self.api_key = os.getenv("RAIDHELPER_API_KEY")
        self.base_url = "https://raid-helper.dev/api"
        self.headers = {
            "API Key": self.api_key,
            "Authorization": self.api_key,
            "Content-Type": "application/json"
        }
        self.sheets_service = GoogleSheetsService()
        self.session_lock = asyncio.Lock()  # Initialize the session lock
        self.processed_events = set()  # Speichert bereits verarbeitete Event-IDs
        self.guild_names = {
            os.getenv("CLAN1_ROLE_ID"): os.getenv("CLAN1_NAME", "Gruppe 9"),
            os.getenv("CLAN2_ROLE_ID"): os.getenv("CLAN2_NAME", "Requiem Moon")
        }
        logging.info(f"RaidHelper Service initialized with server ID: {self.server_id}")
        logging.debug(f"Using headers: {self.headers}")
        
    async def fetch_server_events(self) -> List[Dict]:
        """Fetch all events for the server."""
        url = f"{self.base_url}/v3/servers/{self.server_id}/events"
        logging.info(f"Fetching events from: {url}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as response:
                if response.status == 200:
                    response_data = await response.json()
                    # Die Events sind im 'postedEvents' Array
                    if isinstance(response_data, dict) and "postedEvents" in response_data:
                        events = response_data["postedEvents"]
                        logging.info(f"Successfully fetched {len(events)} events")
                        logging.debug(f"First event structure: {events[0] if events else 'No events'}")
                        return events
                    else:
                        logging.error(f"Unexpected response format: {response_data}")
                        return []
                else:
                    logging.error(f"Failed to fetch server events: {response.status}")
                    try:
                        error_text = await response.text()
                        logging.error(f"Error response: {error_text}")
                    except:
                        pass
                    return []

    async def fetch_event_details(self, event_id: str) -> Optional[Dict]:
        """Fetch details for a specific event."""
        url = f"{self.base_url}/v2/events/{event_id}"
        max_retries = 3
        base_delay = 0.5  # 500ms base delay between requests
        
        for attempt in range(max_retries):
            try:
                # Add delay between requests to respect rate limits
                await asyncio.sleep(base_delay * (attempt + 1))
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=self.headers) as response:
                        if response.status == 200:
                            event_details = await response.json()
                            logging.info(f"Successfully fetched details for event {event_id}")
                            return event_details
                        elif response.status == 429:  # Rate limit hit
                            error_data = await response.json()
                            retry_after = int(error_data.get("reason", "").split("Try again in ")[1].split(" ")[0])
                            logging.warning(f"Rate limit hit, waiting {retry_after} seconds")
                            await asyncio.sleep(retry_after)
                            continue
                        else:
                            logging.error(f"Failed to fetch event details: {response.status}")
                            try:
                                error_text = await response.text()
                                logging.error(f"Error response: {error_text}")
                            except:
                                pass
                            if attempt < max_retries - 1:
                                continue
                            return None
                            
            except Exception as e:
                logging.error(f"Error fetching event details: {e}")
                if attempt < max_retries - 1:
                    continue
                return None
        
        return None

    async def create_default_signups(self, event: RaidHelperEvent, session) -> None:
        """Create default 'No Info' signups for guild members when event starts."""
        try:
            # Extract guild name from event title
            event_title_lower = event.title.lower()
            current_time = datetime.utcnow()
            
            # Get existing signups for this event once
            existing_signups = {
                signup.user_id 
                for signup in session.query(RaidHelperSignup).filter(
                    RaidHelperSignup.event_id == str(event.id)
                ).all()
            }
            
            for guild in session.query(GuildInfo).all():
                guild_name_parts = guild.name.lower().split()
                
                # Check if any part of the guild name is in the event title
                if any(part in event_title_lower for part in guild_name_parts):
                    logging.info(f"Found guild {guild.name} in event title {event.title} (partial match)")
                    
                    # Get all active clan memberships for this guild at event time
                    active_memberships = (
                        session.query(ClanMembership)
                        .join(User)
                        .filter(
                            ClanMembership.clan_role_id == guild.role_id,
                            ClanMembership.is_active == True,
                            ClanMembership.joined_at <= event.start_time,
                            ClanMembership.left_at.is_(None) | (ClanMembership.left_at >= event.start_time)
                        )
                        .all()
                    )
                    
                    logging.info(f"Found {len(active_memberships)} active members in guild {guild.name}")
                    
                    # Create default signups for active members without existing signup
                    for membership in active_memberships:
                        user = membership.user
                        if str(user.discord_id) not in existing_signups:
                            try:
                                signup = RaidHelperSignup(
                                    event_id=str(event.id),
                                    user_id=str(user.discord_id),
                                    user_name=user.username or "Unknown",
                                    entry_time=current_time,
                                    class_name="No Info",
                                    spec_name="",
                                    status="",
                                    position=0
                                )
                                session.add(signup)
                                existing_signups.add(str(user.discord_id))  # Add to existing signups to prevent duplicates
                                logging.info(f"Created default signup for user {user.username}")
                            except Exception as e:
                                logging.error(f"Error creating signup for user {user.username}: {e}")
                                continue
                    
        except Exception as e:
            logging.error(f"Error in create_default_signups: {e}")
            raise

    async def process_closed_event(self, event: RaidHelperEvent, signups: List[Dict]) -> None:
        """Process a single closed event and send its data to Google Sheets."""
        logging.info(f"Processing closed event: {event.title} (ID: {event.id})")
        
        session = SessionLocal()
        try:
            # Get all signups for this event from the database
            db_signups = session.query(RaidHelperSignup).filter(
                RaidHelperSignup.event_id == str(event.id)
            ).all()
            
            if db_signups:
                # Format the data for Google Sheets
                rows = self.sheets_service.format_event_data(event, db_signups)
                
                # Send the data to Google Sheets
                self.sheets_service.append_rows("Sheet1!A:H", rows)
                logging.info(f"Successfully sent {len(rows)} entries to Google Sheets for event {event.id}")
            else:
                logging.warning(f"No signups found for closed event {event.id}")
                
        except Exception as e:
            logging.error(f"Error processing closed event {event.id}: {str(e)}")
            raise
        finally:
            session.close()

    async def sync_active_events(self) -> None:
        """Synchronize active events from RaidHelper."""
        try:
            events = await self.fetch_server_events()
            if not events:
                return

            # Process only the most recent events first (last 10)
            recent_events = sorted(events, key=lambda x: x.get("startTime", 0), reverse=True)[:10]
            
            async with self.session_lock:
                session = SessionLocal()
                try:
                    for event_data in recent_events:
                        event_id = event_data.get("id")
                        if not event_id:
                            continue

                        # Get event details
                        event_details = await self.fetch_event_details(event_id)
                        if not event_details:
                            continue

                        # Create or update event
                        event = create_or_update_raidhelper_event(session, event_data)
                        
                        # First update existing signups from RaidHelper
                        signups_data = event_details.get("signups", [])
                        logging.info(f"Updating {len(signups_data)} signups for event {event_id}")
                        
                        # Get existing signups for this event
                        existing_signups = {
                            signup.user_id: signup 
                            for signup in session.query(RaidHelperSignup).filter(
                                RaidHelperSignup.event_id == str(event_id)
                            ).all()
                        }
                        
                        # Track processed user IDs
                        processed_user_ids = set()
                        
                        # Update or create signups
                        for signup_data in signups_data:
                            user_id = signup_data["userId"]
                            processed_user_ids.add(user_id)
                            
                            if user_id in existing_signups:
                                # Update existing signup
                                signup = existing_signups[user_id]
                                signup.user_name = signup_data["name"]
                                signup.entry_time = datetime.fromtimestamp(int(signup_data["entryTime"]))
                                signup.status = signup_data["status"]
                                signup.class_name = signup_data.get("className", "")
                                signup.spec_name = signup_data.get("specName", "")
                                signup.position = signup_data.get("position", 0)
                                signup.updated_at = datetime.utcnow()
                                logging.info(f"Updated signup for user {user_id} in event {event_id}")
                            else:
                                # Create new signup
                                new_signup = RaidHelperSignup(
                                    event_id=str(event_id),
                                    user_id=user_id,
                                    user_name=signup_data["name"],
                                    entry_time=datetime.fromtimestamp(int(signup_data["entryTime"])),
                                    status=signup_data["status"],
                                    class_name=signup_data.get("className", ""),
                                    spec_name=signup_data.get("specName", ""),
                                    position=signup_data.get("position", 0)
                                )
                                session.add(new_signup)
                                logging.info(f"Created new signup for user {user_id} in event {event_id}")
                        
                        # Remove signups that no longer exist in RaidHelper
                        for user_id, signup in existing_signups.items():
                            if user_id not in processed_user_ids and signup.class_name != "No Info":
                                session.delete(signup)
                                logging.info(f"Removed signup for user {user_id} from event {event_id}")
                        
                        session.flush()  # Ensure all updates are visible
                        
                        # Then create default signups for members without existing signup
                        await self.create_default_signups(event, session)

                        # Process closed events
                        if self.is_event_closed(event):
                            try:
                                # Remove from processed_events to allow reprocessing
                                processed_event = session.query(ProcessedEvent).filter(
                                    ProcessedEvent.event_id == str(event_id)
                                ).first()
                                if processed_event:
                                    session.delete(processed_event)
                                
                                await self.process_closed_event(event, event_details.get("signups", []))
                                mark_event_as_processed(session, str(event.id))
                            except Exception as e:
                                logging.error(f"Error processing closed event {event.id}: {e}")

                    session.commit()
                except Exception as e:
                    logging.error(f"Error in sync_active_events: {e}")
                    session.rollback()
                finally:
                    session.close()

        except Exception as e:
            logging.error(f"Error in sync_active_events: {e}")

    def is_event_closed(self, event: RaidHelperEvent) -> bool:
        """Check if an event is closed."""
        if not event.close_time:
            return False
        return event.close_time.timestamp() <= datetime.utcnow().timestamp()

    async def process_closed_events(self):
        """Process closed events and send their data to Google Sheets."""
        logging.info("Processing closed events")
        current_time = datetime.utcnow().timestamp()
        
        session = SessionLocal()
        try:
            # Hole alle Events aus der Datenbank
            events = session.query(RaidHelperEvent).all()
            
            for event in events:
                try:
                    # Überprüfe, ob das Event bereits verarbeitet wurde
                    if is_event_processed(session, str(event.id)):
                        continue
                    
                    # Überprüfe, ob das Event abgeschlossen ist
                    if event.close_time and event.close_time.timestamp() <= current_time:
                        logging.info(f"Processing closed event: {event.title} (ID: {event.id})")
                        
                        # Hole die Anmeldungen für das Event
                        signups = session.query(RaidHelperSignup).filter(
                            RaidHelperSignup.event_id == str(event.id)
                        ).all()
                        
                        if signups:
                            # Formatiere die Daten für Google Sheets
                            rows = self.sheets_service.format_event_data(event, signups)
                            
                            # Sende die Daten an Google Sheets
                            self.sheets_service.append_rows("Sheet1!A:H", rows)
                            logging.info(f"Successfully sent {len(rows)} entries to Google Sheets for event {event.id}")
                            
                            # Markiere das Event als verarbeitet
                            mark_event_as_processed(session, str(event.id))
                        else:
                            logging.warning(f"No signups found for closed event {event.id}")
                            
                except Exception as e:
                    logging.error(f"Error processing closed event {event.id}: {str(e)}")
                    continue
            
            session.commit()
        except Exception as e:
            logging.error(f"Error in process_closed_events: {e}")
            session.rollback()
        finally:
            session.close()
    
    async def start_sync_task(self):
        """Start the background task to sync events."""
        logging.info("Starting RaidHelper sync task")
        while True:
            try:
                await self.sync_active_events()
                await self.process_closed_events()  # Füge Verarbeitung geschlossener Events hinzu
            except Exception as e:
                logging.error(f"Error in sync task: {e}")
            
            # Wait 5 minutes before next sync
            logging.debug("Waiting 5 minutes before next sync")
            await asyncio.sleep(300) 