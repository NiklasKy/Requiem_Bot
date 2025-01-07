# Stop API container
docker compose stop api

# Export certificates using Win-ACME
wacs --export --certificatestore --file ..\ssl\fullchain.pem --pemkey ..\ssl\privkey.pem

# Restart API container
docker compose start api 