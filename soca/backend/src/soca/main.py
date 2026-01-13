"""SoCa FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from soca.config import settings
from soca.routes import (
    auth_router,
    criteria_router,
    evaluations_router,
    submissions_router,
)

app = FastAPI(title="SoCa API", version="0.1.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(submissions_router)
app.include_router(criteria_router)
app.include_router(evaluations_router)


# Health check
@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)
