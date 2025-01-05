"""Script to run the FastAPI server."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",  # Macht den Server von außen erreichbar
        port=8000,
        reload=True  # Automatisches Neuladen bei Änderungen
    ) 