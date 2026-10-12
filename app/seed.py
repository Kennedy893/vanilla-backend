"""Données de démonstration SIMULÉES — région SAVA.

Usage (depuis backend/) : python seed.py
Le script est idempotent : il ne fait rien si la base contient déjà des organisations.
Toutes les organisations et tous les lots créés ici ont is_demo = True.
Les coordonnées sont approximatives.
"""
import itertools
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from argon2 import PasswordHasher
from sqlalchemy import func, select

from app import models as m
from app.database import SessionLocal

DEMO_PASSWORD = "demo1234"


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def add(session, obj):
    session.add(obj)
    session.flush()  # récupère l'id sans commit
    return obj


def seed(s) -> None:
    pwd_hash = PasswordHasher().hash(DEMO_PASSWORD)

    # ---- Lieux --------------------------------------------------------
    # Les rôles/types de lieu sont stockés sous forme de String(50) dans Alembic
    loc_specs = {
        "sambava": ("Sambava", "CITY", "-14.266700", "50.166700"),
        "antalaha": ("Antalaha", "CITY", "-14.900300", "50.278800"),
        "vohemar": ("Vohémar", "PORT", "-13.355600", "50.005000"),
        "andapa": ("Andapa", "CITY", "-14.650000", "49.650000"),
        "farm_and_n": ("Parcelle Andapa Nord", "FARM", "-14.620000", "49.680000"),
        "farm_and_s": ("Parcelle Andapa Sud", "FARM", "-14.680000", "49.600000"),
        "farm_ant_e": ("Parcelle Antalaha Est", "FARM", "-14.850000", "50.250000"),
    }
    loc = {
        key: add(s, m.Location(name=n, location_type=t, latitude=Decimal(la), longitude=Decimal(lo)))
        for key, (n, t, la, lo) in loc_specs.items()
    }

    # ---- Organisations + un utilisateur par organisation ---------------
    org_specs = {
        "prod_andapa": ("Coopérative Vanille Andapa (démo)", m.OrganizationType.PRODUCER, "Andapa"),
        "prod_antalaha": ("GIE Vanille Antalaha (démo)", m.OrganizationType.PRODUCER, "Antalaha"),
        "collecteur": ("Collecte Vanille Sambava (démo)", m.OrganizationType.COLLECTOR, "Sambava"),
        "transformateur": ("Préparation Vanille Antalaha (démo)", m.OrganizationType.PROCESSOR, "Antalaha"),
        "exportateur": ("Export Vanille Vohémar (démo)", m.OrganizationType.EXPORTER, "Vohémar"),
    }
    org, user = {}, {}
    for key, (name, otype, address) in org_specs.items():
        org[key] = add(
            s, m.Organization(name=name, organization_type=otype, address=address)
        )
        user[key] = add(
            s, m.User(username=key, email=f"{key}@demo.mg", password=pwd_hash, is_active=True)
        )
        add(
            s,
            m.OrganizationMember(
                user_id=user[key].id, organization_id=org[key].id, role=m.MemberRole.OWNER
            ),
        )

    # Un contrôleur qualité rattaché au collecteur
    user["controleur"] = add(
        s, m.User(username="controleur_sambava", email="controleur@demo.mg", password=pwd_hash, is_active=True)
    )
    add(
        s,
        m.OrganizationMember(
            user_id=user["controleur"].id,
            organization_id=org["collecteur"].id,
            role=m.MemberRole.OPERATOR,
        ),
    )

    # ---- Exploitations -------------------------------------------------
    farm_specs = [
        ("FARM-AND-001", "Exploitation Andapa Nord", "2.50", "prod_andapa", "farm_and_n"),
        ("FARM-AND-002", "Exploitation Andapa Sud", "1.80", "prod_andapa", "farm_and_s"),
        ("FARM-ANT-001", "Exploitation Antalaha Est", "3.20", "prod_antalaha", "farm_ant_e"),
    ]
    farms = [
        add(
            s,
            m.Farm(
                farm_code=code,
                name=name,
                area_hectares=Decimal(area),
                producer_organization_id=org[prod].id,
                location_id=loc[lk].id,
            ),
        )
        for code, name, area, prod, lk in farm_specs
    ]

    # ---- Helpers événements -------------------------------------------
    event_seq = itertools.count(1)

    def new_event(event_type, recorded_by, location, organization, description):
        return add(
            s,
            m.TraceabilityEvent(
                event_code=f"EVT-2026-{next(event_seq):04d}",
                event_type=event_type,
                event_date=now(),
                description=description,
                status=m.EventStatus.VALIDATED,
                validated_at=now(),
                recorded_by_id=recorded_by.id,
                validated_by_id=recorded_by.id,
                location_id=location.id,
                organization_id=organization.id,
            ),
        )

    # ---- Lots de récolte (+ événement de création) ---------------------
    harvest_specs = [
        (farms[0], "prod_andapa", "120.00"),
        (farms[1], "prod_andapa", "85.50"),
        (farms[2], "prod_antalaha", "200.00"),
    ]
    lots = []
    for i, (farm, prod_key, qty) in enumerate(harvest_specs, start=1):
        lot = add(
            s,
            m.Lot(
                lot_code=f"VAN-SAVA-2026-{i:04d}",
                lot_type=m.LotType.HARVEST,
                product_state=m.ProductState.FRESH,
                quantity_kg=Decimal(qty),
                status=m.LotStatus.AVAILABLE,
                holder_id=org[prod_key].id,
                farm_id=farm.id,
            ),
        )
        event = new_event(
            m.EventType.HARVEST,
            user[prod_key],
            loc[farm_specs[i - 1][4]],
            org[prod_key],
            f"Récolte enregistrée — {farm.name}",
        )
        add(
            s,
            m.EventLot(
                event_id=event.id, lot_id=lot.id, role=m.EventLotRole.OUTPUT, quantity_kg=Decimal(qty)
            ),
        )
        lots.append(lot)

    # ---- Transfert du lot 1 : Coopérative Andapa -> Collecteur Sambava --
    lot1 = lots[0]
    event = new_event(
        m.EventType.TRANSFER,
        user["prod_andapa"],
        loc["sambava"],
        org["prod_andapa"],
        "Transfert vers le collecteur de Sambava",
    )
    add(
        s,
        m.Transfer(
            event_id=event.id,
            dispatch_date=now() - timedelta(days=2),
            receipt_date=now() - timedelta(days=1),
            status=m.TransferStatus.RECEIVED,
            from_organization_id=org["prod_andapa"].id,
            to_organization_id=org["collecteur"].id,
            origin_location_id=farms[0].location_id,
            destination_location_id=loc["sambava"].id,
        ),
    )
    add(
        s,
        m.EventLot(
            event_id=event.id,
            lot_id=lot1.id,
            role=m.EventLotRole.TRANSFERRED,
            quantity_kg=lot1.quantity_kg,
        ),
    )
    lot1.holder_id = org["collecteur"].id  # Le détenteur change à la réception

    # ---- Contrôle qualité du lot 1 à Sambava ---------------------------
    event = new_event(
        m.EventType.QUALITY_CHECK,
        user["controleur"],
        loc["sambava"],
        org["collecteur"],
        "Contrôle qualité à la réception",
    )
    add(
        s,
        m.EventLot(
            event_id=event.id,
            lot_id=lot1.id,
            role=m.EventLotRole.INPUT,
            quantity_kg=lot1.quantity_kg,
        ),
    )
    add(
        s,
        m.QualityCheck(
            lot_id=lot1.id,
            checked_by_id=user["controleur"].id,
            moisture_percentage=Decimal("68.00"),
            grade="A",
            result=m.QualityResult.PASSED,
            comments="Gousses saines, calibre homogène.",
        ),
    )

    # ---- QR code public du lot 1 --------------------------------------
    add(s, m.QrCode(lot_id=lot1.id, public_token=secrets.token_urlsafe(16)))


def main() -> None:
    with SessionLocal() as s:
        if s.scalar(select(func.count()).select_from(m.Organization)):
            print("La base contient déjà des données : seed ignoré.")
            return
        seed(s)
        s.commit()
    print("Seed terminé (données SIMULÉES).")
    print(f"Comptes de démo : prod_andapa, collecteur, controleur_sambava... / mot de passe : {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()