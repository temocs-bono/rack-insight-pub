"""Credential store: named Redfish / SSH / SNMP credentials that devices
reference. Passwords are Fernet-encrypted and never returned by the API."""
import enum

from sqlalchemy import Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import TimestampedModel


class CredentialType(str, enum.Enum):
    REDFISH = "REDFISH"
    SSH = "SSH"
    SNMP = "SNMP"


class Credential(TimestampedModel):
    __tablename__ = "credentials"

    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    credential_type: Mapped[CredentialType] = mapped_column(
        Enum(CredentialType, name="credential_type"), nullable=False
    )
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    password_encrypted: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
