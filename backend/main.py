"""Rack Insight backend entrypoint (FastAPI)."""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from api.routes import access as access_routes
from api.routes import alerts as alert_routes
from api.routes import audit as audit_routes
from api.routes import auth as auth_routes
from api.routes import clusters as cluster_routes
from api.routes import collector as collector_routes
from api.routes import credentials as credential_routes
from api.routes import dashboard as dashboard_routes
from api.routes import discovery as discovery_routes
from api.routes import lifecycle as lifecycle_routes
from api.routes import device_templates as device_template_routes
from api.routes import devices as device_routes
from api.routes import export as export_routes
from api.routes import plugins as plugin_routes
from api.routes import racks as rack_routes
from api.routes import users as user_routes
from auth.security import hash_password
from cache.redis_cache import close_redis
from config import get_settings
from database import async_session_factory, engine
from database.migrations import run_migrations
from models import User, UserRole
from scheduler.background import start_scheduler, stop_scheduler
from scheduler.plugin_monitor import start_plugin_monitor, stop_plugin_monitor
from services.lifecycle_service import ensure_default_policies
from services.plugin_registry import seed_plugins_from_config
from services.rbac_service import ensure_rbac_seed
from utils.logging import configure_logging, get_logger

settings = get_settings()
configure_logging(settings.debug)
logger = get_logger(__name__)


async def _bootstrap_admin() -> None:
    """Create the default admin account on first start, then seed RBAC.

    The RBAC catalog, system roles and the Administrators group are seeded
    idempotently after the admin exists, so the admin is auto-migrated into the
    Administrators group (which carries the Administrator role binding).
    """
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.role == UserRole.ADMIN))
        if result.scalars().first() is None:
            db.add(
                User(
                    username=settings.default_admin_username,
                    password_hash=hash_password(settings.default_admin_password),
                    role=UserRole.ADMIN,
                )
            )
            await db.commit()
            logger.info("Default admin account created")
        await ensure_rbac_seed(db)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Schema is managed exclusively by Alembic migrations (never create_all),
    # so model changes always require a migration — see alembic/versions/.
    await run_migrations()
    await _bootstrap_admin()
    async with async_session_factory() as db:
        await ensure_default_policies(db)
        # Register config-declared plugins (idempotent; failure-isolated).
        await seed_plugins_from_config(db)
    start_scheduler()
    start_plugin_monitor()
    logger.info("%s v%s started", settings.app_name, settings.app_version)
    yield
    stop_plugin_monitor()
    stop_scheduler()
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router, prefix=settings.api_prefix)
app.include_router(user_routes.router, prefix=settings.api_prefix)
app.include_router(access_routes.router, prefix=settings.api_prefix)
app.include_router(cluster_routes.router, prefix=settings.api_prefix)
app.include_router(rack_routes.router, prefix=settings.api_prefix)
app.include_router(device_routes.router, prefix=settings.api_prefix)
app.include_router(device_template_routes.router, prefix=settings.api_prefix)
app.include_router(credential_routes.router, prefix=settings.api_prefix)
app.include_router(collector_routes.router, prefix=settings.api_prefix)
app.include_router(export_routes.router, prefix=settings.api_prefix)
app.include_router(dashboard_routes.router, prefix=settings.api_prefix)
app.include_router(audit_routes.router, prefix=settings.api_prefix)
app.include_router(discovery_routes.router, prefix=settings.api_prefix)
app.include_router(lifecycle_routes.router, prefix=settings.api_prefix)
app.include_router(alert_routes.router, prefix=settings.api_prefix)
app.include_router(plugin_routes.router, prefix=settings.api_prefix)


@app.get("/api/health", tags=["system"])
async def healthcheck() -> dict[str, str]:
    return {"status": "ok", "version": settings.app_version}
