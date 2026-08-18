"""Dashboard summary schema (F4)."""
from pydantic import BaseModel


class DashboardSummary(BaseModel):
    total_devices: int = 0
    online: int = 0
    warning: int = 0
    critical: int = 0
    offline: int = 0
    unknown: int = 0
