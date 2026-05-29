import uuid

from sqlalchemy import Column, DateTime, Boolean, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, declared_attr


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SoftDeleteMixin:
    __soft_delete__ = True
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)


class AuditMixin:
    created_by = Column(UUID(as_uuid=True), nullable=True, index=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)
    deleted_by = Column(UUID(as_uuid=True), nullable=True)


class OptimisticLockMixin:
    version_id = Column(Integer, nullable=False, default=1)

    @declared_attr
    def __mapper_args__(cls):
        return {"version_id_col": cls.version_id}


class TenantMixin:
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
