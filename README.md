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

The API is available at `http://your-server:3000` (or `https://` if SSL is configured)

Available endpoints:
- `/api/discord/role/{role_id}/members` - Get all members of a Discord role
- `/api/afk` - Get all active AFK entries
- `/api/afk/{discord_id}` - Get AFK entries for a specific user
- `/api/clan/{clan_role_id}/members` - Get all members of a specific clan

## HTTPS Setup (Production)

### Prerequisites
- A domain pointing to your server
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

2. **Generate SSL Certificate**
   ```powershell
   # Stop API container temporarily
   docker compose stop api

   # Generate certificate (replace with your domain)
   # Open Command Prompt as Administrator and run:
   wacs --target manual --host api.yourdomain.com --installation certificate --store certificatestore
   ```

3. **Export Certificates**
   ```powershell
   # Create SSL directory
   mkdir ssl

   # Export certificates using Win-ACME
   wacs --export --certificatestore --file ssl\fullchain.pem --pemkey ssl\privkey.pem
   ```

4. **Update Environment Variables**
   ```env
   # In your .env file
   API_PORT=443
   SSL_KEYFILE=ssl/privkey.pem
   SSL_CERTFILE=ssl/fullchain.pem
   ```

5. **Configure Firewall**
   ```powershell
   # Allow HTTPS traffic
   New-NetFirewallRule -DisplayName "HTTPS-Requiem-API" -Direction Inbound -LocalPort 443 -Protocol TCP -Action Allow
   
   # Allow HTTP traffic for certificate validation
   New-NetFirewallRule -DisplayName "HTTP-ACME-Challenge" -Direction Inbound -LocalPort 80 -Protocol TCP -Action Allow
   ```

6. **Restart Services**
   ```powershell
   docker compose down
   docker compose up -d
   ```

### Certificate Auto-Renewal

1. The `scripts/renew-cert.ps1` script handles certificate renewal:
   ```powershell
   # Stop API container
   docker compose stop api

   # Renew certificate
   wacs --renew

   # Export renewed certificates
   wacs --export --certificatestore --file ssl\fullchain.pem --pemkey ssl\privkey.pem

   # Restart API container
   docker compose start api
   ```

2. **Set up Automatic Renewal**
   - Win-ACME automatically creates a scheduled task for renewal
   - To add certificate export after renewal:
     - Open Windows Task Scheduler
     - Create new task:
       - Name: "Export SSL Certificates"
       - Trigger: After Win-ACME renewal task
       - Action: Run PowerShell script
       - Command: `powershell.exe -ExecutionPolicy Bypass -File "C:\path\to\scripts\renew-cert.ps1"`

### Verification

After setup, your API will be available at:
```
https://api.yourdomain.com/api/discord/role/{role_id}/members
```

## Database Backups

### Automatic Backups
- Created when the container shuts down
- Storage location: `./backups/`
- Format: `db_backup_YYYYMMDD_HHMMSS.sql.gz`
- Retention: 7 days

### Create Manual Backup
```powershell
docker compose exec db /scripts/backup_db.sh
```

### Restore Backup
```powershell
# Restore from .sql.gz backup
docker compose exec db bash -c "gunzip -c /backups/db_backup_YYYYMMDD_HHMMSS.sql.gz | psql -U postgres postgres"

# Or restore from .dump file
docker compose exec db pg_restore -U postgres -d postgres -c -v /backups/backup.dump
```

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
- `/getmembers <role>`: List members with a specific role
- `/checksignups <role> <event_id>`: Compare role members with Raid-Helper signups (admin only)

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