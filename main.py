from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apps.core.config import settings
import uvicorn

app = FastAPI(
    title=settings.app_name,
    version="0.1.0"
)

# Add CORS middleware; origins from settings (env CORS_ORIGINS, comma-separated)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Root endpoint to check if the API is running."""
    return {"message": "Insurance Doc Chatbot API is running!"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)