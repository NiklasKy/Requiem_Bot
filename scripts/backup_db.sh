#!/bin/bash

# Get current date for backup file name
BACKUP_DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="/backups/db_backup_${BACKUP_DATE}.sql"

# Create backup directory if it doesn't exist
mkdir -p /backups

# Create backup
echo "Creating database backup: ${BACKUP_FILE}"
pg_dump -h db -U ${POSTGRES_USER} ${POSTGRES_DB} > ${BACKUP_FILE}

# Compress backup
gzip ${BACKUP_FILE}
echo "Backup compressed: ${BACKUP_FILE}.gz"

# Delete old backups (keep last 7 days)
find /backups -name "db_backup_*.sql.gz" -mtime +7 -delete
echo "Old backups cleaned up" 