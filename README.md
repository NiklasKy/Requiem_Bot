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

### Authentication

All API endpoints require authentication using a Bearer token. Include the following header in your requests:
```
Authorization: Bearer your-api-secret-key
```

### Available Endpoints

#### Clan Memberships
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

#### Clan Members
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

#### AFK Status
```http
GET /api/afk
```
Get all active AFK entries.

```http
GET /api/afk/{discord_id}
```
Get AFK history for a specific user.

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
        "created_at": "2025-01-08T18:27:06.796168",
        "ended_at": null
    }
]
```

#### Discord Role Members
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

### AFK Management
- `/afk <start_date> <start_time> <end_date> <end_time> <reason>`: Set AFK status with specific dates
- `/afkquick <reason> [days]`: Quick AFK until end of day (or specified number of days)
- `/afkreturn`: End AFK status
- `/afklist`: Show all active AFK users
- `/afkmy`: Show your personal AFK entries
- `/afkhistory <user>`: Show AFK history for a user
- `/afkdelete <user> [all_entries]`: Delete AFK entries (admin only)
- `/afkstats`: Show AFK statistics
- `/afkremove <afk_id>`: Remove a future AFK entry

### Member Management
- `/getmembers <role>`: List all members with a specific role
- `/checksignups <role> <event_id>`: Compare role members with Raid-Helper signups

### Clan Management
- `/clanhistory [user]`: Show clan membership history for a user (Admin/Officer only)
  - `user`: Optional, defaults to yourself
  - `include_inactive`: Optional, include past memberships (default: false)
- `/clanchanges [clan] [days]`: Show recent clan membership changes (Admin/Officer only)
  - `clan`: Optional, filter by specific clan
  - `days`: Optional, number of days to look back (default: 7)

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

Response: Same as above, but only includes active members.

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
- `all_entries` (optional): Delete all entries for this user? If false, only deletes active entries

#### /getmembers
- `role`: The role to check members for 

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