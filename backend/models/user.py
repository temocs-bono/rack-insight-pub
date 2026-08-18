"""User account model (ADMIN / USER roles)."""
import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from models.base import TimestampedModel


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    USER = "USER"


# Account status. ``enabled`` remains the authoritative gate for authentication;
# ``status`` mirrors it for display in the Access Management UI.
STATUS_ACTIVE = "ACTIVE"
STATUS_DISABLED = "DISABLED"


class User(TimestampedModel):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Legacy coarse role, retained for backward compatibility and as a
    # break-glass superuser flag (ADMIN bypasses permission checks). Effective
    # authorization is resolved through User Groups -> Role Bindings -> Roles.
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), default=UserRole.USER, nullable=False
    )
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default=STATUS_ACTIVE, server_default=STATUS_ACTIVE, nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
