"""Script to migrate data from SQLite to PostgreSQL."""
import sqlite3
from datetime import datetime

from src.database.models import User, AFKEntry
from src.database.connection import get_db_session

def migrate_from_sqlite(sqlite_path: str):
    """Migrate data from SQLite to PostgreSQL."""
    print(f"Starting migration from {sqlite_path}")
    
    # Connect to SQLite database
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_cursor = sqlite_conn.cursor()
    
    # Get all unique users from afk_users
    sqlite_cursor.execute("""
        SELECT DISTINCT user_id, display_name, clan_role_id 
        FROM afk_users
    """)
    users_data = sqlite_cursor.fetchall()
    
    # Get all AFK entries
    sqlite_cursor.execute("SELECT * FROM afk_users")
    afk_data = sqlite_cursor.fetchall()
    
    # Migrate to PostgreSQL
    with get_db_session() as db:
        # Migrate users
        print(f"Migrating {len(users_data)} users...")
        user_map = {}  # Map Discord user IDs to PostgreSQL user IDs
        
        for user_row in users_data:
            discord_id = str(user_row[0])  # user_id from SQLite
            display_name = user_row[1]
            clan_role_id = str(user_row[2])
            
            # Create or get user in PostgreSQL
            user = db.query(User).filter(User.discord_id == discord_id).first()
            if not user:
                user = User(
                    discord_id=discord_id,
                    username=display_name.split()[0],  # Use first part of display_name as username
                    display_name=display_name,
                    clan_role_id=clan_role_id
                )
                db.add(user)
                db.flush()
            
            user_map[int(discord_id)] = user.id
        
        # Migrate AFK entries
        print(f"Migrating {len(afk_data)} AFK entries...")
        for afk_row in afk_data:
            # SQLite columns: id, user_id, display_name, start_date, end_date, reason, 
            #                clan_role_id, created_at, ended_at, is_active
            discord_user_id = afk_row[1]
            start_date = datetime.fromisoformat(afk_row[3])
            end_date = datetime.fromisoformat(afk_row[4])
            reason = afk_row[5]
            created_at = datetime.fromisoformat(afk_row[7])
            ended_at = datetime.fromisoformat(afk_row[8]) if afk_row[8] else None
            is_active = bool(afk_row[9])
            
            # Create new AFK entry in PostgreSQL
            new_afk = AFKEntry(
                user_id=user_map[discord_user_id],
                start_date=start_date,
                end_date=end_date,
                reason=reason,
                is_active=is_active,
                created_at=created_at,
                ended_at=ended_at
            )
            db.add(new_afk)
        
        # Commit all changes
        db.commit()
        print("Migration completed successfully!")
        
        # Print statistics
        user_count = db.query(User).count()
        afk_count = db.query(AFKEntry).count()
        print(f"\nMigration Statistics:")
        print(f"Users migrated: {user_count}")
        print(f"AFK entries migrated: {afk_count}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python -m src.database.migrate <path_to_sqlite_db>")
        sys.exit(1)
    
    migrate_from_sqlite(sys.argv[1]) 