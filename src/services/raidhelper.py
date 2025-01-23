"""RaidHelper API integration service."""
import os
import logging
from typing import Dict, List, Optional
import aiohttp
from datetime import datetime
import asyncio

from src.database.connection import get_db_session
from src.database.operations import create_or_update_raidhelper_event, update_raidhelper_signups, get_active_raidhelper_events
from src.database.models import RaidHelperEvent, RaidHelperSignup
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
        logging.info(f"Fetching event details from: {url}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as response:
                if response.status == 200:
                    event_details = await response.json()
                    logging.info(f"Successfully fetched details for event {event_id}")
                    return event_details
                else:
                    logging.error(f"Failed to fetch event details: {response.status}")
                    try:
                        error_text = await response.text()
                        logging.error(f"Error response: {error_text}")
                    except:
                        pass
                    return None

    async def sync_active_events(self):
        """Sync all active events and their signups to the database."""
        logging.info("Starting event sync")
        events = await self.fetch_server_events()
        current_time = datetime.utcnow().timestamp()
        
        if not events:
            logging.warning("No events fetched from API")
            return
            
        logging.info(f"Processing {len(events)} events")
        with get_db_session() as db:
            for event_data in events:
                try:
                    # Debug-Log für event_data
                    logging.debug(f"Processing event data: {event_data}")
                    
                    # Sicherstellen, dass event_data ein Dictionary ist
                    if isinstance(event_data, str):
                        event_data = {"id": event_data}  # Minimales Dict erstellen
                        logging.warning(f"Event data was string, converted to dict: {event_data}")
                        continue  # Dieses Event überspringen
                    
                    # Sicheres Abrufen der closeTime mit Fallback
                    close_time = event_data.get("closeTime", 0)
                    if isinstance(close_time, str):
                        try:
                            close_time = int(close_time)
                        except ValueError:
                            close_time = 0
                            logging.warning(f"Could not convert closeTime to int: {event_data.get('closeTime')}")
                    
                    if close_time < current_time:
                        logging.debug(f"Skipping closed event {event_data.get('id')}")
                        continue
                    
                    logging.info(f"Processing event: {event_data.get('title', 'No title')} (ID: {event_data.get('id', 'No ID')})")
                    
                    try:
                        # Create or update the event
                        event = create_or_update_raidhelper_event(db, event_data)
                        logging.info(f"Successfully created/updated event {event.id}: {event.title}")
                        
                        # Fetch and update signups
                        event_details = await self.fetch_event_details(event.id)
                        if event_details and "signUps" in event_details:
                            signups = update_raidhelper_signups(db, event.id, event_details["signUps"])
                            logging.info(f"Updated {len(signups)} signups for event {event.id}")
                        else:
                            logging.warning(f"No signup data found for event {event.id}")
                    except Exception as e:
                        logging.error(f"Database error for event {event_data.get('id')}: {str(e)}")
                        continue
                        
                except Exception as e:
                    logging.error(f"Error processing event: {str(e)}")
                    logging.error(f"Event data that caused error: {event_data}")
                    continue  # Mit dem nächsten Event fortfahren
            
            logging.info("Event sync completed")

    async def process_closed_events(self):
        """Process closed events and send their data to Google Sheets."""
        logging.info("Processing closed events")
        current_time = datetime.utcnow().timestamp()
        
        with get_db_session() as db:
            # Hole alle Events aus der Datenbank
            events = db.query(RaidHelperEvent).all()
            
            for event in events:
                try:
                    # Überspringe bereits verarbeitete Events
                    if event.id in self.processed_events:
                        continue
                    
                    # Überprüfe, ob das Event abgeschlossen ist
                    if event.close_time and event.close_time.timestamp() <= current_time:
                        logging.info(f"Processing closed event: {event.title} (ID: {event.id})")
                        
                        # Hole die Anmeldungen für das Event
                        signups = db.query(RaidHelperSignup).filter(
                            RaidHelperSignup.event_id == event.id
                        ).all()
                        
                        if signups:
                            # Konvertiere Event und Signups in das richtige Format
                            event_data = {
                                "id": event.id,
                                "title": event.title,
                                "closeTime": int(event.close_time.timestamp())
                            }
                            
                            signup_data = [{
                                "user_id": signup.user_id,
                                "user_name": signup.user_name,
                                "status": signup.status
                            } for signup in signups]
                            
                            # Formatiere die Daten für Google Sheets
                            rows = self.sheets_service.format_event_data(
                                event_data,
                                signup_data,
                                self.guild_names
                            )
                            
                            # Sende die Daten an Google Sheets
                            self.sheets_service.append_rows("Sheet1!A:G", rows)
                            logging.info(f"Successfully sent {len(rows)} entries to Google Sheets for event {event.id}")
                            
                            # Markiere das Event als verarbeitet
                            self.processed_events.add(event.id)
                        else:
                            logging.warning(f"No signups found for closed event {event.id}")
                            
                except Exception as e:
                    logging.error(f"Error processing closed event {event.id}: {str(e)}")
                    continue
    
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