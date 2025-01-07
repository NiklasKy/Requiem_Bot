"""Script to run the FastAPI server."""
import os
import uvicorn
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

if __name__ == "__main__":
    # Get port from environment variable, default to 3000
    port = int(os.getenv("API_PORT", 3000))
    ssl_keyfile = os.getenv("SSL_KEYFILE", "ssl/privkey.pem")
    ssl_certfile = os.getenv("SSL_CERTFILE", "ssl/fullchain.pem")
    
    # Check if SSL certificates exist
    use_ssl = os.path.exists(ssl_keyfile) and os.path.exists(ssl_certfile)
    
    if use_ssl:
        uvicorn.run(
            "src.api.main:app",
            host="0.0.0.0",
            port=port,
            ssl_keyfile=ssl_keyfile,
            ssl_certfile=ssl_certfile,
            reload=True
        )
    else:
        print("Warning: SSL certificates not found, running in HTTP mode")
        uvicorn.run(
            "src.api.main:app",
            host="0.0.0.0",
            port=port,
            reload=True
        ) 