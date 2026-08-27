from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .orm import PipelineActiveLeaseORM, PipelineRunHistoryORM


@dataclass
class _Lease:
    step_name: str
    scope_key: str
    owner_token: str
    run_id: str
    acquired_at: float
    heartbeat_at: float
    expires_at: float


class InMemoryLeaseStore:
    """Small deterministic lease implementation used by tests and local rehearsal."""

    heartbeat_seconds = 15.0
    ttl_seconds = 60.0

    def __init__(
        self,
        now: float = 0.0,
        *,
        heartbeat_seconds: float = 15.0,
        ttl_seconds: float = 60.0,
    ):
        if ttl_seconds < heartbeat_seconds * 3:
            raise ValueError("lease TTL must be at least three heartbeats")
        self.now = now
        self.heartbeat_seconds = heartbeat_seconds
        self.ttl_seconds = ttl_seconds
        self.leases: dict[tuple[str, str], _Lease] = {}
        self.history: list[dict[str, Any]] = []

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def acquire(
        self, step_name: str, scope_key: str, owner_token: str, run_id: str
    ) -> bool:
        key = (step_name, scope_key)
        current = self.leases.get(key)
        if current is not None:
            if current.expires_at > self.now:
                return False
            self.history.append(
                {
                    "step_name": step_name,
                    "scope_key": scope_key,
                    "run_id": current.run_id,
                    "error_code": "LEASE_EXPIRED",
                }
            )
        self.leases[key] = _Lease(
            step_name,
            scope_key,
            owner_token,
            run_id,
            self.now,
            self.now,
            self.now + self.ttl_seconds,
        )
        return True

    def heartbeat(self, step_name: str, scope_key: str, owner_token: str) -> bool:
        lease = self.leases.get((step_name, scope_key))
        if (
            lease is None
            or lease.owner_token != owner_token
            or lease.expires_at <= self.now
        ):
            return False
        lease.heartbeat_at = self.now
        lease.expires_at = self.now + self.ttl_seconds
        return True

    def release(self, step_name: str, scope_key: str, owner_token: str) -> bool:
        lease = self.leases.get((step_name, scope_key))
        if lease is None or lease.owner_token != owner_token:
            return False
        del self.leases[(step_name, scope_key)]
        return True


class SqlAlchemyLeaseStore:
    """Database-backed lease with UTC expiry and atomic recovery."""

    def __init__(
        self,
        session: Session,
        *,
        heartbeat_seconds: int = 15,
        ttl_seconds: int = 60,
    ):
        if ttl_seconds < heartbeat_seconds * 3:
            raise ValueError("lease TTL must be at least three heartbeats")
        self.session = session
        self.heartbeat_seconds = heartbeat_seconds
        self.ttl_seconds = ttl_seconds

    def _utc_now(self) -> datetime:
        try:
            value = self.session.execute(text("SELECT UTC_TIMESTAMP(6)")).scalar_one()
        except SQLAlchemyError:
            return datetime.now(UTC)
        if isinstance(value, datetime):
            return (
                value.replace(tzinfo=UTC)
                if value.tzinfo is None
                else value.astimezone(UTC)
            )
        return datetime.now(UTC)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return (
            value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        )

    def _record_expiry(self, lease: PipelineActiveLeaseORM, now: datetime) -> None:
        history = self.session.scalar(
            select(PipelineRunHistoryORM).where(
                PipelineRunHistoryORM.run_id == lease.run_id,
                PipelineRunHistoryORM.step_name == lease.step_name,
                PipelineRunHistoryORM.scope_key == lease.scope_key,
            )
        )
        if history is None:
            self.session.add(
                PipelineRunHistoryORM(
                    run_id=lease.run_id,
                    step_name=lease.step_name,
                    scope_key=lease.scope_key,
                    status="FAILED",
                    error_code="LEASE_EXPIRED",
                    started_at=lease.acquired_at,
                    finished_at=now,
                )
            )
        elif history.status != "COMPLETED":
            history.status = "FAILED"
            history.error_code = "LEASE_EXPIRED"
            history.finished_at = now

    def acquire(
        self, step_name: str, scope_key: str, owner_token: str, run_id: str
    ) -> bool:
        now = self._utc_now()
        lease = self.session.scalar(
            select(PipelineActiveLeaseORM)
            .where(
                PipelineActiveLeaseORM.step_name == step_name,
                PipelineActiveLeaseORM.scope_key == scope_key,
            )
            .with_for_update()
        )
        if lease is not None and self._as_utc(lease.expires_at) > now:
            self.session.rollback()
            return False
        if lease is not None:
            self._record_expiry(lease, now)
            self.session.delete(lease)
            self.session.flush()
        self.session.add(
            PipelineActiveLeaseORM(
                step_name=step_name,
                scope_key=scope_key,
                owner_token=owner_token,
                run_id=run_id,
                acquired_at=now,
                heartbeat_at=now,
                expires_at=now + timedelta(seconds=self.ttl_seconds),
            )
        )
        self.session.commit()
        return True

    def heartbeat(self, step_name: str, scope_key: str, owner_token: str) -> bool:
        now = self._utc_now()
        lease = self.session.scalar(
            select(PipelineActiveLeaseORM).where(
                PipelineActiveLeaseORM.step_name == step_name,
                PipelineActiveLeaseORM.scope_key == scope_key,
            )
        )
        if (
            lease is None
            or lease.owner_token != owner_token
            or self._as_utc(lease.expires_at) <= now
        ):
            self.session.rollback()
            return False
        lease.heartbeat_at = now
        lease.expires_at = now + timedelta(seconds=self.ttl_seconds)
        self.session.commit()
        return True

    def release(self, step_name: str, scope_key: str, owner_token: str) -> bool:
        lease = self.session.scalar(
            select(PipelineActiveLeaseORM).where(
                PipelineActiveLeaseORM.step_name == step_name,
                PipelineActiveLeaseORM.scope_key == scope_key,
            )
        )
        if lease is None or lease.owner_token != owner_token:
            self.session.rollback()
            return False
        self.session.delete(lease)
        self.session.commit()
        return True

    def reclaim_expired(self) -> int:
        now = self._utc_now()
        leases = self.session.scalars(
            select(PipelineActiveLeaseORM).where(
                PipelineActiveLeaseORM.expires_at <= now
            )
        ).all()
        for lease in leases:
            self._record_expiry(lease, now)
            self.session.delete(lease)
        self.session.commit()
        return len(leases)
