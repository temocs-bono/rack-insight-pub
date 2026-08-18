"""Device template CRUD (hardware models). Read: any authenticated user;
write: admin only. Powers the Device Management (Templates) page."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import RequirePermission
from database import get_db
from models import Device, DeviceTemplate, User
from schemas.compliance import TemplateComplianceReport
from schemas.device_template import (
    DeviceTemplateCreate,
    DeviceTemplateResponse,
    DeviceTemplateSummary,
    DeviceTemplateUpdate,
)
from services.compliance_service import get_template_compliance
from services.audit_service import (
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_UPDATE,
    record_audit,
    snapshot_entity,
)
from utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(
    prefix="/device-templates",
    tags=["device-templates"],
    dependencies=[Depends(RequirePermission("template.view"))],
)


async def _get_template(db: AsyncSession, template_id: uuid.UUID) -> DeviceTemplate:
    result = await db.execute(select(DeviceTemplate).where(DeviceTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Device template not found"
        )
    return template


@router.get("", response_model=list[DeviceTemplateSummary])
async def list_templates(db: AsyncSession = Depends(get_db)) -> list[DeviceTemplateSummary]:
    result = await db.execute(select(DeviceTemplate).order_by(DeviceTemplate.name))
    templates = list(result.scalars().all())
    counts = dict(
        (
            await db.execute(
                select(Device.template_id, func.count())
                .where(Device.template_id.is_not(None))
                .group_by(Device.template_id)
            )
        ).all()
    )
    summaries: list[DeviceTemplateSummary] = []
    for template in templates:
        summary = DeviceTemplateSummary.model_validate(template)
        summary.instance_count = counts.get(template.id, 0)
        summaries.append(summary)
    return summaries


@router.get("/{template_id}", response_model=DeviceTemplateResponse)
async def get_template(
    template_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> DeviceTemplate:
    return await _get_template(db, template_id)


@router.get("/{template_id}/compliance", response_model=TemplateComplianceReport)
async def template_compliance(
    template_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> TemplateComplianceReport:
    """Firmware compliance across all devices using this template (F6)."""
    await _get_template(db, template_id)
    return await get_template_compliance(db, template_id)


@router.post("", response_model=DeviceTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: DeviceTemplateCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(RequirePermission("template.create")),
) -> DeviceTemplate:
    try:
        existing = await db.execute(
            select(DeviceTemplate).where(DeviceTemplate.name == payload.name)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Template name already exists"
            )
        template = DeviceTemplate(**payload.model_dump())
        db.add(template)
        await db.flush()
        record_audit(
            db, admin, ACTION_CREATE, "device_template", template.name, template.id,
            new_value=snapshot_entity(template),
        )
        await db.commit()
        await db.refresh(template)
        return template
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Template creation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Template creation failed"
        ) from exc


@router.patch("/{template_id}", response_model=DeviceTemplateResponse)
async def update_template(
    template_id: uuid.UUID,
    payload: DeviceTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(RequirePermission("template.update")),
) -> DeviceTemplate:
    template = await _get_template(db, template_id)
    old = snapshot_entity(template)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(template, key, value)
    record_audit(
        db, admin, ACTION_UPDATE, "device_template", template.name, template.id,
        old_value=old, new_value=snapshot_entity(template),
    )
    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(RequirePermission("template.delete")),
) -> None:
    template = await _get_template(db, template_id)
    in_use = (
        await db.execute(
            select(func.count()).select_from(Device).where(Device.template_id == template_id)
        )
    ).scalar_one()
    if in_use:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Template is used by {in_use} installed device(s)",
        )
    record_audit(
        db, admin, ACTION_DELETE, "device_template", template.name, template.id,
        old_value=snapshot_entity(template),
    )
    await db.delete(template)
    await db.commit()
