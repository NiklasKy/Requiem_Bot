# Stop API container
docker compose stop api

# Re-export certificates with correct names
wacs --source manual --host requiem-api.niklasky.com --store pemfiles --pemfilespath ssl

# Restart API container
docker compose start api 