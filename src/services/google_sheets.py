"""Google Sheets integration service."""
import os
import logging
from typing import List, Dict, Any
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.database.connection import get_db_session
from src.database.models import User, GuildInfo

class GoogleSheetsService:
    """Service for interacting with Google Sheets."""
    
    def __init__(self):
        """Initialize the Google Sheets service."""
        self.spreadsheet_id = os.getenv("GOOGLE_SHEET_ID")
        self.sheet_name = "Activity Check"
        self.headers = ["Date", "Time", "Event ID", "Title", "Guild", "User Name", "Discord ID", "Status"]
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
        """Überprüft, ob das Sheet existiert und erstellt es bei Bedarf."""
        try:
            # Hole alle Sheets im Spreadsheet
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            
            # Überprüfe, ob unser Sheet bereits existiert
            sheet_exists = False
            for sheet in spreadsheet.get('sheets', []):
                if sheet.get('properties', {}).get('title') == self.sheet_name:
                    sheet_exists = True
                    break
            
            if not sheet_exists:
                # Erstelle ein neues Sheet
                requests = [{
                    'addSheet': {
                        'properties': {
                            'title': self.sheet_name
                        }
                    }
                }]
                
                self.service.spreadsheets().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={'requests': requests}
                ).execute()
                
                # Füge die Spaltenüberschriften hinzu
                range_name = f"{self.sheet_name}!A1:H1"
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=range_name,
                    valueInputOption='RAW',
                    body={'values': [self.headers]}
                ).execute()
                
                # Formatiere die Überschriften (fett)
                requests = [{
                    'repeatCell': {
                        'range': {
                            'sheetId': self._get_sheet_id(),
                            'startRowIndex': 0,
                            'endRowIndex': 1
                        },
                        'cell': {
                            'userEnteredFormat': {
                                'textFormat': {'bold': True}
                            }
                        },
                        'fields': 'userEnteredFormat.textFormat.bold'
                    }
                }]
                
                self.service.spreadsheets().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={'requests': requests}
                ).execute()
                
                logging.info(f"Created new sheet '{self.sheet_name}' with headers")
            else:
                logging.info(f"Sheet '{self.sheet_name}' already exists")
                
        except Exception as e:
            logging.error(f"Error ensuring sheet exists: {e}")
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
            range_name = f"{self.sheet_name}!A:H"
            
            result = self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body=body
            ).execute()
            
            rows_appended = result.get('updates', {}).get('updatedRows', 0)
            logging.info(f"Successfully appended {rows_appended} rows to Google Sheet")
            return rows_appended
            
        except HttpError as e:
            logging.error(f"Error appending to Google Sheet: {e}")
            raise
            
    def format_event_data(self, event, signups):
        """Format event and signup data for Google Sheets."""
        rows = []
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
                
                row = [
                    event.end_time.strftime("%Y-%m-%d"),   # Date
                    event.end_time.strftime("%H:%M"),      # Time
                    str(event.id),                         # Event ID
                    event.title,                           # Title
                    guild_name,                            # Guild
                    signup.user_name,                      # User Name
                    str(signup.user_id),                   # Discord ID
                    signup.class_name                      # Status (Class Name)
                ]
                rows.append(row)
                logging.debug(f"Added row for {signup.user_name}: {row}")
        
        return rows 