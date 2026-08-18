"""Cluster CRUD + dashboard summaries."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import RequirePermission
from database import get_db
from models import Cluster, User
from schemas.cluster import ClusterCreate, ClusterResponse, ClusterSummary, ClusterUpdate
from schemas.rack import RackSummary
from services.audit_service import (
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_UPDATE,
    record_audit,
    snapshot_entity,
)
from services.summary_service import cluster_summaries, rack_summaries
from utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(
    prefix="/clusters",
    tags=["clusters"],
    dependencies=[Depends(RequirePermission("cluster.view"))],
)


@router.get("", response_model=list[ClusterSummary])
async def list_clusters(db: AsyncSession = Depends(get_db)) -> list[ClusterSummary]:
    try:
        return await cluster_summaries(db)
    except Exception as exc:
        logger.exception("Cluster listing failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Cluster listing failed"
        ) from exc


@router.get("/{cluster_id}", response_model=ClusterResponse)
async def get_cluster(cluster_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Cluster:
    result = await db.execute(select(Cluster).where(Cluster.id == cluster_id))
    cluster = result.scalar_one_or_none()
    if cluster is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cluster not found")
    return cluster


@router.get("/{cluster_id}/racks", response_model=list[RackSummary])
async def list_cluster_racks(
    cluster_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[RackSummary]:
    return await rack_summaries(db, cluster_id)


@router.post(
    "",
    response_model=ClusterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_cluster(
    payload: ClusterCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(RequirePermission("cluster.create")),
) -> Cluster:
    try:
        existing = await db.execute(select(Cluster).where(Cluster.name == payload.name))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Cluster name already exists"
            )
        cluster = Cluster(**payload.model_dump())
        db.add(cluster)
        await db.flush()
        record_audit(
            db, admin, ACTION_CREATE, "cluster", cluster.name, cluster.id,
            new_value=snapshot_entity(cluster),
        )
        await db.commit()
        await db.refresh(cluster)
        return cluster
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Cluster creation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Cluster creation failed"
        ) from exc


@router.patch("/{cluster_id}", response_model=ClusterResponse)
async def update_cluster(
    cluster_id: uuid.UUID,
    payload: ClusterUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(RequirePermission("cluster.update")),
) -> Cluster:
    result = await db.execute(select(Cluster).where(Cluster.id == cluster_id))
    cluster = result.scalar_one_or_none()
    if cluster is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cluster not found")
    old = snapshot_entity(cluster)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(cluster, key, value)
    record_audit(
        db, admin, ACTION_UPDATE, "cluster", cluster.name, cluster.id,
        old_value=old, new_value=snapshot_entity(cluster),
    )
    await db.commit()
    await db.refresh(cluster)
    return cluster


@router.delete(
    "/{cluster_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_cluster(
    cluster_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(RequirePermission("cluster.delete")),
) -> None:
    result = await db.execute(select(Cluster).where(Cluster.id == cluster_id))
    cluster = result.scalar_one_or_none()
    if cluster is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cluster not found")
    record_audit(
        db, admin, ACTION_DELETE, "cluster", cluster.name, cluster.id,
        old_value=snapshot_entity(cluster),
    )
    await db.delete(cluster)
    await db.commit()
