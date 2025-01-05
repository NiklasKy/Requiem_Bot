"""FastAPI server for the Requiem Bot API."""
import asyncio
import os
from datetime import datetime
from typing import List, Optional

import discord
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.database.connection import get_db_session
from src.database.operations import (get_active_afk, get_user_afk_history,
                                   get_or_create_user, set_afk, get_clan_members)

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0"))

# Create Discord client
class DiscordBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(intents=intents)
        self.guild = None
        self.ready = asyncio.Event()

    async def on_ready(self):
        self.guild = self.get_guild(GUILD_ID)
        self.ready.set()
        print(f"Logged in as {self.user}")

discord_client = DiscordBot()
loop = asyncio.get_event_loop()
loop.create_task(discord_client.start(TOKEN))

app = FastAPI(title="Requiem Bot API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_event():
    """Close Discord client on API shutdown."""
    if discord_client:
        await discord_client.close()

class DiscordUserResponse(BaseModel):
    """Schema for Discord user response."""
    discord_id: str
    username: str
    display_name: Optional[str] = None
    roles: List[str]

class UserResponse(BaseModel):
    """Schema for user response."""
    id: int
    discord_id: str
    username: str
    display_name: Optional[str] = None
    clan_role_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class AFKCreate(BaseModel):
    """Schema for creating an AFK entry."""
    discord_id: str
    start_date: datetime
    end_date: datetime
    reason: str
    username: str
    display_name: Optional[str] = None

class AFKResponse(BaseModel):
    """Schema for AFK response."""
    id: int
    user_id: int
    start_date: datetime
    end_date: datetime
    reason: str
    is_active: bool
    created_at: datetime
    ended_at: Optional[datetime] = None

@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Welcome to Requiem Bot API"}

@app.get("/api/clan/{clan_role_id}/members", response_model=List[UserResponse])
async def get_clan_members_list(clan_role_id: str):
    """Get all members of a specific clan."""
    with get_db_session() as db:
        members = get_clan_members(db, clan_role_id)
        if not members:
            raise HTTPException(
                status_code=404,
                detail=f"No members found for clan with role ID {clan_role_id}"
            )
        return members

@app.get("/api/afk", response_model=List[AFKResponse])
async def get_afk_list():
    """Get all active AFK entries."""
    with get_db_session() as db:
        afk_entries = []
        for user, entry in get_active_afk(db):
            afk_entries.append(entry)
        return afk_entries

@app.get("/api/afk/{discord_id}", response_model=List[AFKResponse])
async def get_user_afk(discord_id: str):
    """Get AFK entries for a specific user."""
    with get_db_session() as db:
        user = get_or_create_user(db, discord_id, "Unknown")
        entries = get_user_afk_history(db, user, limit=10)
        return entries

@app.post("/api/afk", response_model=AFKResponse)
async def create_afk(afk: AFKCreate):
    """Create a new AFK entry."""
    with get_db_session() as db:
        user = get_or_create_user(
            db,
            afk.discord_id,
            afk.username,
            afk.display_name
        )
        
        entry = set_afk(
            db,
            user,
            afk.start_date,
            afk.end_date,
            afk.reason
        )
        return entry 

@app.get("/api/discord/role/{role_id}/members", response_model=List[DiscordUserResponse])
async def get_discord_role_members(role_id: str):
    """Get all members of a Discord role."""
    try:
        # Wait for Discord client to be ready
        await discord_client.ready.wait()
        
        # Convert role_id to int
        role_id_int = int(role_id)
        
        # Get the guild
        guild = discord_client.guild
        if not guild:
            raise HTTPException(
                status_code=404,
                detail="Discord guild not found"
            )
            
        # Get the role
        role = guild.get_role(role_id_int)
        if not role:
            raise HTTPException(
                status_code=404,
                detail=f"Role with ID {role_id} not found"
            )
            
        # Get members with this role
        members = []
        for member in role.members:
            members.append(DiscordUserResponse(
                discord_id=str(member.id),
                username=member.name,
                display_name=member.display_name,
                roles=[str(r.id) for r in member.roles]
            ))
            
        return members
            
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid role ID format"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting role members: {str(e)}"
        ) 