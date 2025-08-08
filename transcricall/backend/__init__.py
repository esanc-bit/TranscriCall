from .app import app
from .static_mount import router as static_router

app.include_router(static_router)