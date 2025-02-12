"""Google Sheets integration service."""
import os
import logging
from typing import List, Dict, Any
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.database.connection import get_db_session
from src.database.models import User, GuildInfo, AFKEntry

class GoogleSheetsService:
    """Service for interacting with Google Sheets."""
    
    def __init__(self):
        """Initialize the Google Sheets service."""
        self.spreadsheet_id = os.getenv("GOOGLE_SHEET_ID")
        self.sheet_name = "Activity Check"
        self.headers = [
            "Date", "Time", "Event ID", "Title", "Guild", 
            "User Name", "Discord ID", "Status", "AFK Status"  # Added AFK Status column
        ]
        credentials_path = "credentials.json"
        
        # Setup Google Sheets API
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        
        try:
            credentials = Credentials.from_service_account_file(credentials_path, scopes=scopes)
            self.service = build('sheets', 'v4', credentials=credentials)
            logging.info("Google Sheets Service initialized successfully")
            
            # Überprüfe und erstelle das Sheet beim Start
            self.ensure_sheet_exists()
        except Exception as e:
            logging.error(f"Failed to initialize Google Sheets service: {e}")
            raise
    
    def ensure_sheet_exists(self):
        """Check if the sheet exists and create it if it doesn't."""
        try:
            # Try to get the sheet to check if it exists
            sheet = self.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            
            # Check if our sheet name exists
            sheet_exists = any(s['properties']['title'] == self.sheet_name for s in sheet['sheets'])
            
            if not sheet_exists:
                # Create new sheet
                body = {
                    'requests': [{
                        'addSheet': {
                            'properties': {
                                'title': self.sheet_name
                            }
                        }
                    }]
                }
                self.service.spreadsheets().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body=body
                ).execute()
                logging.info(f"Sheet '{self.sheet_name}' created")
                
                # Add headers
                range_name = f"{self.sheet_name}!A1:I1"
                body = {
                    'values': [self.headers]
                }
                # Make headers bold
                format_request = {
                    'requests': [{
                        'repeatCell': {
                            'range': {
                                'sheetId': self._get_sheet_id(),
                                'startRowIndex': 0,
                                'endRowIndex': 1,
                                'startColumnIndex': 0,
                                'endColumnIndex': len(self.headers)
                            },
                            'cell': {
                                'userEnteredFormat': {
                                    'textFormat': {
                                        'bold': True
                                    }
                                }
                            },
                            'fields': 'userEnteredFormat.textFormat.bold'
                        }
                    }]
                }
                
                # Update values and format
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=range_name,
                    valueInputOption='RAW',
                    body=body
                ).execute()
                self.service.spreadsheets().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body=format_request
                ).execute()
            else:
                logging.info(f"Sheet '{self.sheet_name}' already exists")
                
        except HttpError as error:
            logging.error(f"Failed to ensure sheet exists: {error}")
            raise
    
    def _get_sheet_id(self) -> int:
        """Holt die Sheet ID für das aktuelle Sheet."""
        spreadsheet = self.service.spreadsheets().get(
            spreadsheetId=self.spreadsheet_id
        ).execute()
        
        for sheet in spreadsheet.get('sheets', []):
            if sheet.get('properties', {}).get('title') == self.sheet_name:
                return sheet.get('properties', {}).get('sheetId')
        return 0
    
    def append_rows(self, range_name: str, values: List[List[Any]]) -> int:
        """Append rows to the specified range in the spreadsheet."""
        try:
            body = {
                'values': values
            }
            
            # Aktualisiere den range_name, um das korrekte Sheet zu verwenden
            range_name = f"{self.sheet_name}!A:I"
            
            result = self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='USER_ENTERED',  # Changed from 'RAW' to 'USER_ENTERED'
                insertDataOption='INSERT_ROWS',
                body=body
            ).execute()

            # Get the range of the newly inserted rows
            updated_range = result.get('updates', {}).get('updatedRange', '')
            if updated_range:
                # Extract the row numbers from the range (e.g., "Sheet1!A2:H5" -> 2,5)
                start_row = int(''.join(filter(str.isdigit, updated_range.split(':')[0])))
                end_row = int(''.join(filter(str.isdigit, updated_range.split(':')[1])))

                # Apply normal (non-bold) formatting to the inserted rows
                format_request = {
                    'requests': [{
                        'repeatCell': {
                            'range': {
                                'sheetId': self._get_sheet_id(),
                                'startRowIndex': start_row - 1,  # Convert to 0-based index
                                'endRowIndex': end_row,
                                'startColumnIndex': 0,
                                'endColumnIndex': len(self.headers)
                            },
                            'cell': {
                                'userEnteredFormat': {
                                    'textFormat': {
                                        'bold': False
                                    }
                                }
                            },
                            'fields': 'userEnteredFormat.textFormat.bold'
                        }
                    }]
                }

                # Apply the formatting
                self.service.spreadsheets().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body=format_request
                ).execute()
            
            rows_appended = result.get('updates', {}).get('updatedRows', 0)
            logging.info(f"Successfully appended {rows_appended} rows to Google Sheet")
            return rows_appended
            
        except HttpError as e:
            logging.error(f"Error appending to Google Sheet: {e}")
            raise
            
    def format_event_data(self, event, signups):
        """Format event and signup data for Google Sheets."""
        # Temporäre Liste für die Sortierung
        temp_rows = []
        
        with get_db_session() as session:
            # Create a dictionary of guild_role_id to guild name for faster lookups
            guild_info_map = {
                info.role_id: info.name 
                for info in session.query(GuildInfo).all()
            }
            logging.debug(f"Loaded guild info map: {guild_info_map}")
            
            for signup in signups:
                # Get user from database
                user = session.query(User).filter(User.discord_id == str(signup.user_id)).first()
                logging.debug(f"Looking up user {signup.user_name} (ID: {signup.user_id})")
                logging.debug(f"Found user in DB: {user.username if user else 'Not found'}")
                if user:
                    logging.debug(f"User clan_role_id: {user.clan_role_id}")
                
                # Get guild name from map, or "Unknown" if not found
                guild_name = "Unknown"
                if user and user.clan_role_id:
                    guild_name = guild_info_map.get(user.clan_role_id, "Unknown")
                    logging.debug(f"Found guild name: {guild_name} for role_id: {user.clan_role_id}")
                
                # Convert specific class_names and status to "Present"
                status = signup.class_name
                if signup.class_name in ["DPS", "Tank", "Healer", "Dps"]:
                    status = "Present"
                elif signup.class_name == "No signup":
                    status = "No signup"
                elif signup.class_name == "":
                    status = signup.class_name or "No signup"
                else:
                    # Behalte den originalen Status bei (z.B. "Absence", "Bench", etc.)
                    status = signup.class_name
                
                # Check for AFK status
                afk_status = "-"
                if user:
                    afk_entry = (
                        session.query(AFKEntry)
                        .filter(
                            AFKEntry.user_id == user.id,
                            AFKEntry.start_date <= event.end_time,
                            AFKEntry.end_date >= event.end_time,
                            AFKEntry.is_active == True
                        )
                        .first()
                    )
                    if afk_entry:
                        afk_status = f"AFK: {afk_entry.reason}"
                        # Setze Status auf AFK wenn nicht "Present"
                        if status != "Present":
                            status = "AFK"
                
                # Format date and time in German format
                event_date = event.end_time.strftime("%d.%m.%Y")
                event_time = event.end_time.strftime("%H:%M")
                
                row = [
                    event_date,                            # Date in German format
                    event_time,                           # Time in 24h format
                    str(event.id),                        # Event ID
                    event.title,                          # Title
                    guild_name,                           # Guild
                    signup.user_name,                     # User Name
                    str(signup.user_id),                  # Discord ID
                    status,                               # Status
                    afk_status                           # AFK Status
                ]
                # Füge die Zeile mit Gildennamen zur temporären Liste hinzu
                temp_rows.append((guild_name, row))
        
        # Sortiere die Zeilen nach Gildennamen
        # Requiem Main zuerst, dann Requiem North, dann Unknown
        def guild_sort_key(item):
            guild = item[0]
            if guild == "Requiem Main":
                return 0
            elif guild == "Requiem North":
                return 1
            elif guild == "Unknown":
                return 3
            else:
                return 2

        temp_rows.sort(key=guild_sort_key)
        
        # Extrahiere nur die Zeilen ohne Gildennamen für die Rückgabe
        rows = [row for _, row in temp_rows]
        
        return rows 

    def update_status_in_sheet(self, event_id: str, user_id: str, new_status: str) -> bool:
        """Update the status for a specific event and user in the sheet.
        
        Args:
            event_id: The event ID to look for
            user_id: The Discord user ID to look for
            new_status: The new status to set
            
        Returns:
            bool: True if the update was successful, False otherwise
        """
        try:
            # Get all values from the sheet
            range_name = f"{self.sheet_name}!A:H"
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name
            ).execute()
            values = result.get('values', [])
            
            if not values:
                logging.error("No data found in sheet")
                return False
            
            # Find the row with matching event_id and user_id
            # Event ID is in column C (index 2), User ID is in column G (index 6)
            # Status is in column H (index 7)
            row_index = None
            for i, row in enumerate(values):
                if len(row) >= 8 and row[2] == event_id and row[6] == user_id:
                    row_index = i
                    break
            
            if row_index is None:
                logging.error(f"No matching entry found for event {event_id} and user {user_id}")
                return False
            
            # Update only the status column (H) for the found row
            update_range = f"{self.sheet_name}!H{row_index + 1}"
            body = {
                'values': [[new_status]]
            }
            
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=update_range,
                valueInputOption='RAW',
                body=body
            ).execute()
            
            logging.info(f"Successfully updated status to {new_status} for event {event_id} and user {user_id}")
            return True
            
        except Exception as e:
            logging.error(f"Error updating status in sheet: {e}")
            return False 