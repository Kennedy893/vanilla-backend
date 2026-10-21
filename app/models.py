"""Modèles SQLAlchemy 2.0 — Vanilla Traceability (version finale de conception.sql).

Lecture : chaque classe = une table, chaque attribut `mapped_column` = une colonne.
"""
from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# --------------------------------------------------------------------------
# 1) Valeurs contrôlées : un CHECK (col IN (...)) en SQL devient une enum Python
# --------------------------------------------------------------------------
class OrganizationType(str, enum.Enum):
    PRODUCER = "producer"
    COLLECTOR = "collector"
    COOPERATIVE = "cooperative"
    PROCESSOR = "processor"
    TRANSPORTER = "transporter"
    EXPORTER = "exporter"
    CERTIFICATION_BODY = "certification_body"
    OTHER = "other"


class MemberRole(str, enum.Enum):
    OWNER = "owner"
    MANAGER = "manager"
    OPERATOR = "operator"
    VIEWER = "viewer"


class LotType(str, enum.Enum):
    HARVEST = "harvest"
    RAW = "raw"
    INTERMEDIATE = "intermediate"
    FINISHED = "finished"


class ProductState(str, enum.Enum):
    FRESH = "fresh"
    FERMENTING = "fermenting"
    DRIED = "dried"
    SORTED = "sorted"
    GRADED = "graded"
    PACKAGED = "packaged"


class LotStatus(str, enum.Enum):
    CREATED = "created"
    AVAILABLE = "available"
    IN_TRANSFER = "in_transfer"
    PROCESSING = "processing"
    BLOCKED = "blocked"
    EXPORTED = "exported"
    ARCHIVED = "archived"


class QualityResult(str, enum.Enum):
    PASSED = "passed"
    FAILED = "failed"
    CONDITIONAL = "conditional"


class ShipmentStatus(str, enum.Enum):
    PLANNED = "planned"
    READY = "ready"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class EventType(str, enum.Enum):
    HARVEST = "harvest"
    COLLECTION = "collection"
    TRANSFER = "transfer"
    PROCESSING = "processing"
    QUALITY_CHECK = "quality_check"
    STORAGE = "storage"
    SHIPMENT = "shipment"
    EXPORT = "export"


class EventStatus(str, enum.Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class EventLotRole(str, enum.Enum):
    INPUT = "input"
    OUTPUT = "output"
    TRANSFERRED = "transferred"
    CHECKED = "checked"


class TransferStatus(str, enum.Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    RECEIVED = "received"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


def enum_col(cls: type[enum.Enum], name: str) -> Enum:
    """Colonne VARCHAR + contrainte CHECK (col IN (...)) générée depuis l'enum."""
    return Enum(
        cls,
        name=name,
        native_enum=False,  # VARCHAR + CHECK, comme dans ton SQL (pas d'enum natif PG)
        create_constraint=True,
        length=50,
        validate_strings=True,
        values_callable=lambda e: [m.value for m in e],
    )


Kg = Numeric(15, 2)


# --------------------------------------------------------------------------
# 2) Utilisateurs et organisations
# --------------------------------------------------------------------------
class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)  # SERIAL PRIMARY KEY
    name: Mapped[str | None] = mapped_column(String(50))
    organization_type: Mapped[OrganizationType] = mapped_column(  # NOT NULL
        enum_col(OrganizationType, "organization_type")
    )
    address: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool | None] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    phone: Mapped[str | None] = mapped_column(String(50))


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str | None] = mapped_column(String(50), unique=True)
    password: Mapped[str] = mapped_column(String(255))  # stocker un HASH, jamais le mot de passe
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())


class OrganizationMember(Base):
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("user_id", "organization_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[MemberRole] = mapped_column(enum_col(MemberRole, "role"))
    joined_at: Mapped[datetime | None] = mapped_column(DateTime)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))


# --------------------------------------------------------------------------
# 3) Lieux et exploitations
# --------------------------------------------------------------------------
class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    location_type: Mapped[str | None] = mapped_column(String(50))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))


class Farm(Base):
    __tablename__ = "farms"
    __table_args__ = (CheckConstraint("area_hectares >= 0", name="area_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str | None] = mapped_column(String(50))
    area_hectares: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    producer_organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))


# --------------------------------------------------------------------------
# 4) Lots
# --------------------------------------------------------------------------
class Lot(Base):
    __tablename__ = "lots"
    __table_args__ = (
        CheckConstraint("quantity_kg >= 0", name="quantity_positive"),
        # Les trois champs d'archivage vont ensemble : tous vides, ou tous remplis
        CheckConstraint(
            "(archived_at IS NULL AND archived_by_id IS NULL AND archive_reason IS NULL) OR "
            "(archived_at IS NOT NULL AND archived_by_id IS NOT NULL AND archive_reason IS NOT NULL)",
            name="archive_fields_together",
        ),
        # Un lot « archived » a forcément une date d'archivage
        CheckConstraint(
            "status <> 'archived' OR archived_at IS NOT NULL",
            name="archived_requires_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lot_code: Mapped[str] = mapped_column(String(50), unique=True)
    lot_type: Mapped[LotType] = mapped_column(enum_col(LotType, "lot_type"))
    product_state: Mapped[ProductState | None] = mapped_column(
        enum_col(ProductState, "product_state")
    )
    quantity_kg: Mapped[Decimal] = mapped_column(Kg)
    status: Mapped[LotStatus | None] = mapped_column(
        enum_col(LotStatus, "status"), default=LotStatus.CREATED
    )
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"))
    holder_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    # Archivage : renseignés ensemble, uniquement quand le lot passe à « archived »
    archived_at: Mapped[datetime | None] = mapped_column(DateTime)
    archived_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    archive_reason: Mapped[str | None] = mapped_column(String(500))
    # Statut du lot juste avant l'archivage, pour le restaurer à l'identique au désarchivage
    archived_from_status: Mapped[str | None] = mapped_column(String(30))


class LotLineage(Base):
    __tablename__ = "lot_lineage"
    __table_args__ = (
        CheckConstraint("quantity_contributed_kg >= 0", name="quantity_positive"),
        CheckConstraint("parent_lot_id <> child_lot_id", name="parent_differs_from_child"),
        UniqueConstraint("parent_lot_id", "child_lot_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    quantity_contributed_kg: Mapped[Decimal | None] = mapped_column(Kg)
    parent_lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"))
    child_lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"))


class QualityCheck(Base):
    __tablename__ = "quality_checks"
    __table_args__ = (
        CheckConstraint("moisture_percentage BETWEEN 0 AND 100", name="moisture_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    moisture_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    grade: Mapped[str | None] = mapped_column(String(50))
    result: Mapped[QualityResult] = mapped_column(enum_col(QualityResult, "result"))
    comments: Mapped[str | None] = mapped_column(Text)
    checked_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"))
    event_id: Mapped[int | None] = mapped_column(ForeignKey("traceability_events.id"))


# --------------------------------------------------------------------------
# 5) Expéditions et QR codes
# --------------------------------------------------------------------------
class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_code: Mapped[str] = mapped_column(String(50), unique=True)
    destination_country: Mapped[str] = mapped_column(String(50))
    planned_departure: Mapped[datetime | None] = mapped_column(DateTime)
    actual_departure: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[ShipmentStatus | None] = mapped_column(
        enum_col(ShipmentStatus, "status"),
        default=ShipmentStatus.PLANNED,
        server_default=ShipmentStatus.PLANNED.value,
    )
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())


class ShipmentLot(Base):
    __tablename__ = "shipment_lots"
    __table_args__ = (
        CheckConstraint("quantity_kg > 0", name="quantity_positive"),
        UniqueConstraint("shipment_id", "lot_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    quantity_kg: Mapped[Decimal | None] = mapped_column(Kg)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"))
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"))


class QrCode(Base):
    __tablename__ = "qr_codes"
    __table_args__ = (
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at", name="revoked_after_created"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_token: Mapped[str] = mapped_column(String(50), unique=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"))


# --------------------------------------------------------------------------
# 6) Événements de traçabilité, transformations, transferts
# --------------------------------------------------------------------------
class TraceabilityEvent(Base):
    __tablename__ = "traceability_events"
    __table_args__ = (
        CheckConstraint(
            "status <> 'validated' OR (validated_at IS NOT NULL AND validated_by_id IS NOT NULL)",
            name="validated_requires_validator",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_code: Mapped[str] = mapped_column(String(50), unique=True)
    event_type: Mapped[EventType | None] = mapped_column(enum_col(EventType, "event_type"))
    event_date: Mapped[datetime | None] = mapped_column(DateTime)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[EventStatus] = mapped_column(
        enum_col(EventStatus, "status"),
        default=EventStatus.PENDING,
        server_default=EventStatus.PENDING.value,
    )
    validated_at: Mapped[datetime | None] = mapped_column(DateTime)
    recorded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    validated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))


class ProcessingRecord(Base):
    __tablename__ = "processing_records"
    __table_args__ = (
        CheckConstraint("input_quantity_kg >= 0", name="input_positive"),
        CheckConstraint("output_quantity_kg >= 0", name="output_positive"),
        CheckConstraint("loss_quantity_kg >= 0", name="loss_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    process_type: Mapped[str] = mapped_column(String(50))
    start_date: Mapped[datetime | None] = mapped_column(DateTime)
    end_date: Mapped[datetime | None] = mapped_column(DateTime)
    input_quantity_kg: Mapped[Decimal] = mapped_column(Kg)
    output_quantity_kg: Mapped[Decimal | None] = mapped_column(Kg)
    loss_quantity_kg: Mapped[Decimal | None] = mapped_column(Kg)
    notes: Mapped[str | None] = mapped_column(Text)
    event_id: Mapped[int] = mapped_column(ForeignKey("traceability_events.id"))


class EventLot(Base):
    __tablename__ = "event_lots"
    __table_args__ = (CheckConstraint("quantity_kg > 0", name="quantity_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[EventLotRole | None] = mapped_column(enum_col(EventLotRole, "role"))
    quantity_kg: Mapped[Decimal | None] = mapped_column(Kg)
    event_id: Mapped[int] = mapped_column(ForeignKey("traceability_events.id"))
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"))


class Transfer(Base):
    __tablename__ = "transfers"
    __table_args__ = (
        CheckConstraint("from_organization_id <> to_organization_id", name="distinct_organizations"),
        CheckConstraint(
            "receipt_date IS NULL OR dispatch_date IS NULL OR receipt_date >= dispatch_date",
            name="receipt_after_dispatch",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dispatch_date: Mapped[datetime | None] = mapped_column(DateTime)
    receipt_date: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[TransferStatus] = mapped_column(
        enum_col(TransferStatus, "status"),
        default=TransferStatus.PENDING,
        server_default=TransferStatus.PENDING.value,
    )
    event_id: Mapped[int] = mapped_column(ForeignKey("traceability_events.id"))
    from_organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    to_organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    origin_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    destination_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))