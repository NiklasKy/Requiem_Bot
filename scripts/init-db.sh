#!/bin/bash

set -e

# Create the database user and database
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Set authentication requirements
    ALTER SYSTEM SET password_encryption = 'scram-sha-256';
    ALTER SYSTEM SET log_connections = 'on';
    ALTER SYSTEM SET log_disconnections = 'on';
    ALTER SYSTEM SET log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h ';
    
    -- Create application role if not exists
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$DB_USER') THEN
            CREATE ROLE $DB_USER WITH LOGIN PASSWORD '$DB_PASSWORD';
        END IF;
    END
    \$\$;
    
    -- Grant privileges
    GRANT ALL PRIVILEGES ON DATABASE $POSTGRES_DB TO $DB_USER;
    
    -- Update pg_hba.conf to only allow specific users
    \c $POSTGRES_DB
    CREATE EXTENSION IF NOT EXISTS pg_auth_mon;
EOSQL

# Reload PostgreSQL configuration
pg_ctl reload 