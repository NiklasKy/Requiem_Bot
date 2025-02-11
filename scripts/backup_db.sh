#!/bin/bash

# Setze Fehlererkennung
set -e

# Backup-Verzeichnis
BACKUP_DIR="/backups"

# Aktuelles Datum für den Dateinamen
DATE=$(date +%Y%m%d_%H%M%S)

# Erstelle Backup-Verzeichnis falls es nicht existiert
mkdir -p $BACKUP_DIR

# Erstelle Backup
echo "Creating database backup..."
pg_dump -U postgres ${POSTGRES_DB} | gzip > "$BACKUP_DIR/db_backup_${DATE}.sql.gz"

# Lösche alte Backups (älter als 7 Tage)
echo "Cleaning up old backups..."
find $BACKUP_DIR -name "db_backup_*.sql.gz" -type f -mtime +7 -delete

echo "Backup completed: db_backup_${DATE}.sql.gz" 