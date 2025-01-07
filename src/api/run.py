"""Script to run the FastAPI server."""
import os
import uvicorn
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

if __name__ == "__main__":
    # Get port from environment variable, default to 3000
    port = int(os.getenv("API_PORT", 3000))
    
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",  # Macht den Server von außen erreichbar
        port=port,
        reload=True  # Automatisches Neuladen bei Änderungen
    ) 