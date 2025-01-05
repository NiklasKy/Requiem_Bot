# Requiem Bot

A Discord bot for managing AFK status and clan members.

## Features

- AFK status management
- Clan member management
- REST API for external access
- Automatic database backups

## Installation

1. Clone repository
2. Create `.env` file (see `.env.example`)
3. Install Docker and Docker Compose
4. Start with:
```bash
docker-compose up -d
```

## Database Backups

The bot automatically creates backups of the PostgreSQL database:

### Automatic Backups
- Created when the container shuts down
- Storage location: `./backups/`
- Format: `db_backup_YYYYMMDD_HHMMSS.sql.gz`
- Retention: 7 days

### Create Manual Backup
```bash
docker-compose exec db /scripts/backup_db.sh
```

### Restore Backup
```bash
# Unzip backup
gunzip db_backup_YYYYMMDD_HHMMSS.sql.gz

# Import into database
docker-compose exec -T db psql -U ${DB_USER} ${DB_NAME} < db_backup_YYYYMMDD_HHMMSS.sql
```

### Backup Configuration
The backup settings can be adjusted in the following files:
- `docker-compose.yml`: Container configuration
- `scripts/backup_db.sh`: Backup script

## API Endpoints

- `GET /api/afk`: List all active AFK entries
- `GET /api/afk/{discord_id}`: Get AFK entries for a specific user
- `POST /api/afk`: Create new AFK entry
- `GET /api/clan/{clan_role_id}/members`: List all members of a clan
- `GET /api/discord/role/{role_id}/members`: List all Discord members of a role

## Discord Commands

### AFK Management
- `/afk <start_date> <start_time> <end_date> <end_time> <reason>`: Set AFK status with specific dates
- `/afkquick <reason> [days]`: Quick AFK until end of day (or specified number of days)
- `/afkreturn`: End AFK status
- `/afklist`: Show all active AFK users
- `/afkmy`: Show your personal AFK entries
- `/afkhistory <user>`: Show AFK history for a user (admin only)
- `/afkdelete <user> [all_entries]`: Delete AFK entries (admin only)
- `/afkstats`: Show AFK statistics (admin only)

### Member Management
- `/getmembers <role>`: List members with a specific role (admin only)

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
docker-compose up -d
```

### Database Migration
To migrate data from a SQLite database to PostgreSQL:
```bash
# Copy SQLite DB to container
docker cp path/to/sqlite.db requiem_bot-api-1:/app/data/

# Run migration
docker-compose exec api python -m src.database.migrate /app/data/sqlite.db
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