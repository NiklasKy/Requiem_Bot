# Requiem Bot

Discord bot for managing AFK status and other clan-related functionalities.

## Features

- AFK Management
- Clan Member Management
- Discord Role Integration
- REST API for external integrations
- Automated Database Backups

## Prerequisites

- Docker and Docker Compose
- Windows Server (for production setup)
- Domain name (for HTTPS setup)

## Quick Start

1. Clone the repository
2. Copy `.env.example` to `.env` and fill in your values
3. Run `docker compose up -d`

## Environment Variables

See `.env.example` for all required environment variables.

## API Documentation

The API is available at `http://localhost:8000` in development mode or `https://your-domain` in production mode.

#### Authentication

All API endpoints require authentication using a Bearer token. Include the following header in your requests:
```
Authorization: Bearer your-api-secret-key
```

#### Available Endpoints

##### AFK Status
```http
GET /api/afk
```
Get all active and non-deleted AFK entries.

```http
GET /api/afk/{discord_id}
```
Get AFK history for a specific user (excludes deleted entries).

Example Response:
```json
[
    {
        "id": 1,
        "user_id": 1,
        "start_date": "2025-01-08T18:27:06.796168",
        "end_date": "2025-01-09T18:27:06.796168",
        "reason": "Vacation",
        "is_active": true,
        "is_deleted": false,
        "created_at": "2025-01-08T18:27:06.796168",
        "ended_at": null
    }
]
```

##### Clan Memberships
```http
GET /api/clan/memberships
```
Get all clan memberships with optional filtering.

Query Parameters:
- `clan_role_id` (optional): Filter by specific clan role ID
- `include_inactive` (optional, default: false): Include former members
- `days` (optional): Only show changes in the last X days

Example Response:
```json
[
    {
        "discord_id": "148445299969490944",
        "username": "username",
        "display_name": "Display Name",
        "clan_role_id": "791436960585220097",
        "clan_name": "Clan Name",
        "joined_at": "2025-01-08T18:27:06.796168",
        "left_at": null,
        "is_active": true
    }
]
```

##### Clan Members
```http
GET /api/clan/{clan_role_id}/members
```
Get current members of a specific clan.

Example Response:
```json
[
    {
        "id": 1,
        "discord_id": "148445299969490944",
        "username": "username",
        "display_name": "Display Name",
        "clan_role_id": "791436960585220097",
        "created_at": "2025-01-08T18:27:06.796168",
        "updated_at": "2025-01-08T18:27:06.796168"
    }
]
```

##### Discord Role Members
```http
GET /api/discord/role/{role_id}/members
```
Get all members of a specific Discord role.

Example Response:
```json
[
    {
        "discord_id": "148445299969490944",
        "username": "username",
        "display_name": "Display Name",
        "roles": ["791436960585220097"]
    }
]
```

### Example Usage (PowerShell)

```powershell
$headers = @{ 
    Authorization = "Bearer your-api-secret-key"
}

# Get all clan memberships
Invoke-WebRequest -Uri "http://localhost:8000/api/clan/memberships" -Headers $headers -Method GET

# Get memberships with filters
Invoke-WebRequest -Uri "http://localhost:8000/api/clan/memberships?clan_role_id=791436960585220097&include_inactive=true&days=30" -Headers $headers -Method GET

# Get AFK entries for a specific user
Invoke-WebRequest -Uri "http://localhost:8000/api/afk/148445299969490944" -Headers $headers -Method GET
```

## HTTPS Setup (Production)

### Prerequisites
- A domain pointing to your server (e.g., requiem-api.yourdomain.com)
- Windows Server with administrator access
- Docker and Docker Compose installed

### Installation Steps

1. **Install Win-ACME**
   ```powershell
   # Install Chocolatey (if not already installed)
   Set-ExecutionPolicy Bypass -Scope Process -Force
   [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
   iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

   # Install Win-ACME
   choco install win-acme
   ```

2. **Configure Firewall**
   ```powershell
   # Allow HTTPS traffic
   New-NetFirewallRule -DisplayName "HTTPS-Requiem-API" -Direction Inbound -LocalPort 443 -Protocol TCP -Action Allow
   
   # Allow HTTP traffic for certificate validation
   New-NetFirewallRule -DisplayName "HTTP-ACME-Challenge" -Direction Inbound -LocalPort 80 -Protocol TCP -Action Allow
   ```

3. **Create SSL Directory**
   ```powershell
   # Create directory for certificates
   mkdir ssl
   ```

4. **Generate and Export Certificate**
   ```powershell
   # Stop API container
   docker compose stop api

   # Generate certificate (replace with your domain)
   wacs --source manual --host requiem-api.yourdomain.com --store pemfiles --pemfilespath ssl
   ```

   This will create several files in the ssl directory:
   - `requiem-api.yourdomain.com-key.pem` (Private key)
   - `requiem-api.yourdomain.com-chain.pem` (Certificate chain)
   - `requiem-api.yourdomain.com-chain-only.pem` (Intermediate certificates)
   - `requiem-api.yourdomain.com-crt.pem` (Server certificate)

5. **Update Environment Variables**
   ```env
   # In your .env file
   API_PORT=443
   SSL_KEYFILE=ssl/requiem-api.yourdomain.com-key.pem
   SSL_CERTFILE=ssl/requiem-api.yourdomain.com-chain.pem
   ```

6. **Restart Services**
   ```powershell
   docker compose down
   docker compose up -d
   ```

### Certificate Auto-Renewal

Win-ACME automatically creates a scheduled task for certificate renewal. The certificates will be renewed automatically when they are about to expire (typically around 30 days before expiration).

The renewal script `scripts/renew-cert.ps1` handles the certificate re-export after automatic renewal:
```powershell
# Stop API container
docker compose stop api

# Re-export certificates with correct names
wacs --source manual --host requiem-api.yourdomain.com --store pemfiles --pemfilespath ssl

# Restart API container
docker compose start api
```

To set up automatic re-export after renewal:
1. Open Task Scheduler:
   - Press Windows + R
   - Enter `taskschd.msc`
   - Click OK

2. Create new task:
   - Right-click "Task Scheduler Library"
   - Select "Create Task..."

3. General Tab:
   - Name: "Requiem Bot - Export SSL Certificates"
   - Description: "Re-exports SSL certificates after Win-ACME renewal"
   - Run with highest privileges: ✓
   - "Run whether user is logged on or not": ✓
   - Configure for: Windows Server 2022

4. Triggers Tab:
   - Click "New..."
   - Begin the task: "On an event"
   - Log: "Microsoft-Windows-TaskScheduler/Operational"
   - Source: "Task Scheduler"
   - Event ID: 102
   - Custom: ✓
   - XML Filter:
     ```xml
     <QueryList>
       <Query Id="0" Path="Microsoft-Windows-TaskScheduler/Operational">
         <Select Path="Microsoft-Windows-TaskScheduler/Operational">
           *[EventData[Data[@Name='TaskName']='\win-acme renew (acme-v02.api.letsencrypt.org)']]
         </Select>
       </Query>
     </QueryList>
     ```

5. Actions Tab:
   - Click "New..."
   - Action: "Start a program"
   - Program/script: `powershell.exe`
   - Add arguments: `-ExecutionPolicy Bypass -File "C:\#Requiem\Requiem_Bot\scripts\renew-cert.ps1"`
   - Start in: `C:\#Requiem\Requiem_Bot`

6. Conditions Tab:
   - Uncheck "Start the task only if the computer is on AC power"
   - Leave other settings at default

7. Settings Tab:
   - "Allow task to be run on demand": ✓
   - "Run task as soon as possible after a scheduled start is missed": ✓
   - "If the task fails, restart every": 1 minute
   - "Attempt to restart up to": 3 times
   - "Stop the task if it runs longer than": 1 hour

### Security Notes

1. SSL certificates and private keys are sensitive data. They are automatically added to `.gitignore`:
   ```gitignore
   # SSL certificates
   /ssl/
   *.pem
   ```

2. Make sure to:
   - Keep your private keys secure
   - Don't commit SSL certificates to version control
   - Regularly backup your certificates
   - Monitor certificate expiration dates

### Verification

After setup, your API will be available at:
```
https://requiem-api.yourdomain.com/api/discord/role/{role_id}/members
```

## Database Backups

### Automatic Backups
- Created when the container shuts down
- Storage location: `./backups/`
- Format: `db_backup_YYYYMMDD_HHMMSS.sql.gz`
- Retention: 7 days

### Manual Backup Methods

#### Create Compressed SQL Backup
```powershell
docker compose exec db /scripts/backup_db.sh
```

#### Create Dump File Backup
```powershell
# Create a dump file backup
docker compose exec db pg_dump -U postgres -Fc postgres > backups/backup.dump
```

### Restore Methods

#### Restore from SQL.GZ Backup
```powershell
# Unpack and restore .sql.gz backup
docker compose exec db bash -c "gunzip -c /backups/db_backup_YYYYMMDD_HHMMSS.sql.gz | psql -U postgres postgres"
```

#### Restore from Dump File
```powershell
# First, drop and recreate the database
docker compose exec db psql -U postgres -c "DROP DATABASE postgres WITH (FORCE);" -c "CREATE DATABASE postgres;"

# Then restore from dump file
docker compose exec db pg_restore -U postgres -v -d postgres /backups/backup.dump
```

**Note**: When restoring from a dump file, make sure to:
1. Stop any applications accessing the database
2. Drop and recreate the database before restoring
3. Restart your applications after the restore is complete

## Discord Commands

### Available Commands

#### Activity Tracking
- `/activityedit <event_id> <user> <status>`: Edit a user's activity status for an event (Admin/Officer only)
  - `event_id`: The Raid-Helper event ID
  - `user`: The user whose status should be changed
  - `status`: New status (Present, Absent, No Show)

#### AFK Management
- `/afk <start_date> <start_time> <end_date> <end_time> <reason>`: Set AFK status with specific dates
- `/afkquick <reason> [days]`: Quick AFK until end of day (or specified number of days)
- `/afkreturn`: End AFK status
- `/afklist`: Show all active AFK users
- `/afkmy`: Show your personal AFK entries
- `/afkhistory <user>`: Show AFK history for a user (includes AFK IDs for admin commands)
- `/afkdelete <user> <all_entries|afk_id>`: Mark AFK entries as deleted (Admin only)
- `/afkstats`: Show AFK statistics
- `/afkremove <afk_id>`: Remove a future AFK entry
- `/afkextend <afk_id> <hours>`: Extend an existing AFK entry by specified hours

#### Guild Management
- `/guildadd <user> <guild> [send_welcome]`: Add a user to a guild (Admin/Officer only)
- `/guildremove <user> <guild> [kick_from_discord]`: Remove a user from a guild (Admin/Officer only)
- `/welcomeset <guild> <message>`: Set welcome message for a guild (Admin only)
- `/welcomeshow [guild]`: Show welcome messages for all guilds (Admin/Officer only)

#### Utility Commands
- `/getmembers <role>`: List all members with a specific role
- `/checksignups <role> <event_id>`: Compare role members with Raid-Helper signups (Admin/Officer only)
- `/clanhistory [user] [include_inactive]`: Show clan membership history (Admin/Officer only)
- `/clanchanges [clan] [days]`: Show recent clan membership changes (Admin/Officer only)

### Command Parameters

#### /activityedit
- `event_id`: The Raid-Helper event ID to edit
- `user`: The user whose status should be changed
- `status`: The new status (choices: Present, Absent, No Show)

#### /afk
- `start_date`: Start date (DDMM, DD/MM or DD.MM)
- `start_time`: Start time (HHMM or HH:MM)
- `end_date`: End date (DDMM, DD/MM or DD.MM)
- `end_time`: End time (HHMM or HH:MM)
- `reason`: Reason for being AFK

## Clan Tracking Features

The bot automatically tracks clan membership changes:
- Monitors joins and leaves for configured clan roles
- Records timestamps for all membership changes
- Updates every minute
- Accessible via API and Discord commands
- Historical data available for analysis

### API Endpoints for Clan Data
- `/api/clan/{clan_role_id}/members` - Get current clan members
- `/api/clan/{clan_role_id}/history` - Get clan membership history
- `/api/clan/changes` - Get recent clan membership changes

### API Endpoints

#### Get Clan Memberships
```http
GET /api/clan/memberships
```

Query parameters:
- `clan_role_id` (optional): Filter by specific clan
- `include_inactive` (optional): Include past memberships
- `days` (optional): Look back specific number of days

Response:
```json
[
  {
    "discord_id": "string",
    "username": "string",
    "display_name": "string",
    "clan_role_id": "string",
    "joined_at": "datetime",
    "left_at": "datetime",
    "is_active": boolean
  }
]
```

#### Get Current Clan Members
```http
GET /api/clan/{clan_role_id}/current
```

Response format is the same as above.

Authentication:
All API endpoints require a Bearer token in the Authorization header:
```http
Authorization: Bearer your_api_secret_key
```

## Development

### Prerequisites
- Python 3.9+
- Docker & Docker Compose
- PostgreSQL (provided via Docker)

### Developer Setup
1. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
.\venv\Scripts\activate   # Windows
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Start development server:
```bash
docker compose up -d
```

### Database Migration
To migrate data from SQLite to PostgreSQL:
```bash
python migrate_db.py
```

### Command Parameters

#### /afk
- `start_date`: Start date (DDMM, DD/MM or DD.MM)
- `start_time`: Start time (HHMM or HH:MM)
- `end_date`: End date (DDMM, DD/MM or DD.MM)
- `end_time`: End time (HHMM or HH:MM)
- `reason`: Reason for being AFK

#### /afkquick
- `reason`: Reason for being AFK
- `days` (optional): Number of days to be AFK (default: until end of today)

#### /afkdelete
- `user`: The user whose AFK entries you want to delete
- `all_entries`: Set to true to delete all entries for this user (required if no afk_id provided)
- `afk_id`: Specific AFK entry ID to delete (required if all_entries is false, use /afkhistory to get the ID)

Note: Either `all_entries:true` or a specific `afk_id` must be provided.

#### /getmembers
- `role`: The role to check members for 

#### /afkextend
- `afk_id`: The ID of the AFK entry to extend (use /afkmy to see your entries)
- `hours`: Number of hours to extend the AFK entry by

# API Documentation

## Authentication
All API endpoints require a Bearer token for authentication. Add the following header to your requests:
```
Authorization: Bearer your_api_secret_key
```

## Endpoints

### Clan Memberships

#### Get Clan Memberships
```http
GET /api/clan/memberships
```

Query Parameters:
- `clan_role_id` (optional): Filter by specific clan role ID
- `include_inactive` (optional): Include past memberships (default: false)
- `days` (optional): Only show changes in the last X days

Response:
```json
[
  {
    "discord_id": "123456789",
    "username": "username",
    "display_name": "display name",
    "clan_role_id": "791436960585220097",
    "clan_name": "Gruppe 9",
    "joined_at": "2025-01-08T18:27:06.796168",
    "left_at": null,
    "is_active": true
  }
]
```

#### Get Current Clan Members
```http
GET /api/clan/{clan_role_id}/current
```

Path Parameters:
- `clan_role_id`: The Discord role ID of the clan

Response format is the same as above.

### Environment Variables

The following environment variables are used for clan configuration:

```env
# Clan Names
CLAN1_NAME=name1          # Display name for first clan
CLAN2_NAME=name2          # Display name for second clan
CLAN1_ALIASES=alias1,alias2  # Comma-separated list of aliases for first clan
CLAN2_ALIASES=alias3,alias4  # Comma-separated list of aliases for second clan
```

These variables are used to customize the clan names and their aliases in both the Discord bot commands and API responses. 

### AFK Management Features

The bot provides comprehensive AFK (Away From Keyboard) management with the following features:
- Set AFK status with specific start and end dates/times
- Quick AFK setting until end of day
- View active and scheduled AFK entries
- View AFK history
- Extend existing AFK entries
- Remove future AFK entries
- Soft deletion of AFK entries (entries are marked as deleted but preserved in the database)
- Automatic status updates
- AFK statistics

### AFK Management Commands
- `/afk <start_date> <start_time> <end_date> <end_time> <reason>`: Set AFK status with specific dates
- `/afkquick <reason> [days]`: Quick AFK until end of day (or specified number of days)
- `/afkreturn`: End AFK status
- `/afklist`: Show all active AFK users
- `/afkmy`: Show your personal AFK entries
- `/afkhistory <user>`: Show AFK history for a user (includes AFK IDs for admin commands)
- `/afkdelete <user> <all_entries|afk_id>`: Mark AFK entries as deleted (Admin only)
- `/afkstats`: Show AFK statistics
- `/afkremove <afk_id>`: Remove a future AFK entry
- `/afkextend <afk_id> <hours>`: Extend an existing AFK entry by specified hours (use /afkmy to get the ID)

### Database Management

#### AFK Entry States
AFK entries can have the following states:
- **Active**: Current and valid AFK entries
- **Inactive**: Past or manually ended AFK entries
- **Deleted**: Entries marked as deleted (but preserved in database)
- **Scheduled**: Future AFK entries

When an AFK entry is "deleted" using the `/afkdelete` command, it is not actually removed from the database. Instead:
- The entry is marked as deleted (`is_deleted = true`)
- The entry is set to inactive (`is_active = false`)
- The `ended_at` timestamp is set to the deletion time
- The entry remains in the database for historical tracking

This soft deletion approach provides several benefits:
- Maintains a complete history of AFK entries
- Allows for potential recovery of accidentally deleted entries
- Enables better tracking and statistics
- Preserves data integrity and relationships 

### Guild Management Commands

#### `/guildadd`
Add a user to a guild (Admin/Officer only)
- `user`: The user to add to the guild
- `guild`: The guild to add the user to
- `send_welcome`: Send welcome message to user (default: True)

#### `/guildremove`
Remove a user from a guild (Admin/Officer only)
- `user`: The user to remove from the guild
- `guild`: The guild to remove the user from
- `kick_from_discord`: Also kick the user from Discord (default: False)

#### `/welcomeset`
Set welcome message for a guild (Admin only)
- `guild`: The guild to set the welcome message for
- `message`: The welcome message to send to new members

#### `/welcomeshow`
Show welcome messages for all guilds (Admin/Officer only)
- `guild`: Optional: Show message for specific guild only 

## Recent Updates

### Activity Tracking Improvements
- Enhanced status handling in Google Sheets:
  - Direct status updates in the sheet when using `/activityedit`
  - Improved AFK status display with reason
  - Better sorting of entries by guild (Requiem Main first, then Requiem North)
  - Changed "No Info" to "No signup" for better clarity
  - Status is now set to "Present" for Tank/DPS/Healer roles
  - AFK status is displayed when applicable and user is not marked as "Present"

### Command Improvements
- `/activityedit` command now:
  - Updates the database entry
  - Directly modifies the corresponding row in the Google Sheet
  - Provides visual feedback with color-coded embeds
  - Shows warnings if sheet update fails
  - Preserves AFK status information

### Bug Fixes
- Fixed interaction timeout issues in guild management commands
- Improved error handling for Discord API interactions
- Corrected module import paths
- Enhanced response handling for long-running commands 

## Bot Permissions

When inviting the bot to a new Discord server, ensure it has the following permissions:

### Required Permissions
- **General Permissions**
  - View Channels
  - Manage Roles (for guild management)
  - Read Message History
  - Add Reactions

- **Text Channel Permissions**
  - Send Messages
  - Send Messages in Threads
  - Create Public Threads
  - Create Private Threads
  - Embed Links
  - Attach Files
  - Read Message History
  - Use Slash Commands

- **Member Permissions**
  - Kick Members (optional, only if using kick functionality with /guildremove)
  - View Member Insights
  - Manage Nicknames

### Permission Integer
You can use the following permission integer when creating an invite link:
```
412317240384
```

### Invite Link Setup
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your bot application
3. Navigate to "OAuth2" → "URL Generator"
4. Select the following scopes:
   - `bot`
   - `applications.commands`
5. Select the permissions listed above
6. Use the generated URL to invite the bot

### Post-Invite Setup
After inviting the bot:
1. Ensure the bot's role is positioned above any roles it needs to manage
2. Configure the required environment variables (ADMIN_ROLE_ID, OFFICER_ROLE_ID, etc.)
3. Set up the clan roles and their IDs in the environment configuration 