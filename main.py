from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from apps.core.config import settings
from apps.auth.router import router as auth_router
from apps.ingestion.router import router as ingestion_router
from apps.query.router import router as query_router

app = FastAPI(
    title=settings.app_name,
    version="0.1.0"
)

# Include the imported routers
app.include_router(auth_router)
app.include_router(ingestion_router)
app.include_router(query_router)

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