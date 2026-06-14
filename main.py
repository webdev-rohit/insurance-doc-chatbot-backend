from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
import uvicorn

from apps.core.config import settings
from apps.auth.router import router as auth_router

app = FastAPI(
    title=settings.app_name,
    version="0.1.0"
)

# Custom OpenAPI schema to include JWT Bearer authentication
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    schema.setdefault("components", {})["securitySchemes"] = {
        "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    }
    app.openapi_schema = schema
    return schema

app.openapi = custom_openapi

# Import and include auth router
app.include_router(auth_router)

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