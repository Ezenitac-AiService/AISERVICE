from __future__ import annotations

import argparse
import json
import os
import signal
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from typing import Any, Protocol, cast

from oliview_core.db.lease import InMemoryLeaseStore

from .pipeline_selection import CANONICAL_STEPS, parse_steps


@dataclass
class PipelineContext:
    run_id: str
    selector: str
    steps: tuple[str, ...]
    cycle_watermark: datetime
    completed: set[str] = field(default_factory=set)
    step_checkpoints: dict[str, datetime] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)


class LeaseBusyError(RuntimeError):
    pass


class ResumeMismatchError(ValueError):
    pass


class StepHandlerNotConfigured(RuntimeError):
    """Raised instead of recording success for an unwired pipeline step."""


class LeaseHeartbeatLostError(RuntimeError):
    """Raised when the runner can no longer prove ownership of its lease."""


class RunStore(Protocol):
    def record_step(
        self,
        *,
        run_id: str,
        step_name: str,
        scope_key: str,
        status: str,
        checkpoint: Mapping[str, object] | None = None,
        error_code: str | None = None,
    ) -> Any: ...

    def complete(self, row: Any, *, checkpoint: Mapping[str, object]) -> None: ...

    def fail(self, row: Any, *, error_code: str) -> None: ...

    def load_run(self, run_id: str) -> dict[str, object] | None: ...


class LeaseStore(Protocol):
    def acquire(
        self, step_name: str, scope_key: str, owner_token: str, run_id: str
    ) -> bool: ...

    def heartbeat(self, step_name: str, scope_key: str, owner_token: str) -> bool: ...

    def release(self, step_name: str, scope_key: str, owner_token: str) -> bool: ...


ProductCodeLookup = Callable[[str], int | None]


def resolve_selector(
    *,
    product_id: int | None = None,
    product_code: str | None = None,
    lookup: ProductCodeLookup | None = None,
) -> str:
    """Resolve the mutually exclusive CLI product selector."""
    if product_id is not None and product_code is not None:
        raise ValueError("product-id and product-code are mutually exclusive")
    if product_id is not None:
        return f"product:{product_id}"
    if product_code is None or not product_code.strip():
        raise ValueError("one product selector is required")
    normalized_code = product_code.strip()
    if lookup is None:
        return f"product_code:{normalized_code}"
    resolved_id = lookup(normalized_code)
    if resolved_id is None:
        raise ValueError(f"product code not found: {normalized_code}")
    return f"product:{resolved_id}"


class PipelineRunner:
    def __init__(
        self,
        *,
        step_handlers: dict[str, Callable[[PipelineContext], None]] | None = None,
        lease_store: LeaseStore | None = None,
        run_store: RunStore | None = None,
        product_ids: Callable[[PipelineContext], Iterable[int]] | None = None,
    ):
        self.step_handlers = step_handlers or {}
        self.lease_store = lease_store or InMemoryLeaseStore()
        self.run_store = run_store
        self.product_ids = product_ids
        self._shutdown = False
        self.runs: dict[str, PipelineContext] = {}

    def stop(self, *_signals: object) -> None:
        self._shutdown = True

    def run_once(
        self,
        *,
        selector: str,
        steps: str | Iterable[str] = "all",
        resume_run_id: str | None = None,
        interval_hours: float = 0,
    ) -> PipelineContext:
        if interval_hours < 0:
            raise ValueError("interval_hours must be non-negative")
        selected = parse_steps(steps)
        previous: PipelineContext | None = None
        if resume_run_id is not None:
            previous = self.runs.get(resume_run_id)
            if previous is None and self.run_store is not None:
                persisted = self.run_store.load_run(resume_run_id)
                if persisted is not None:
                    watermark = persisted.get("cycle_watermark")
                    persisted_steps = cast(Iterable[str], persisted.get("steps", ()))
                    persisted_completed = cast(
                        Iterable[str], persisted.get("completed", set())
                    )
                    persisted_checkpoints = {
                        str(step): datetime.fromisoformat(str(value))
                        for step, value in cast(
                            dict[str, object],
                            persisted.get("step_checkpoints", {}),
                        ).items()
                    }
                    previous = PipelineContext(
                        run_id=resume_run_id,
                        selector=str(persisted.get("selector", "")),
                        steps=tuple(persisted_steps),
                        cycle_watermark=(
                            datetime.fromisoformat(str(watermark))
                            if watermark
                            else datetime.now(UTC)
                        ),
                        completed=set(persisted_completed),
                        step_checkpoints=persisted_checkpoints,
                        metadata={"status": persisted.get("status")},
                    )
            if previous is None:
                raise ResumeMismatchError(
                    "resume run id must refer to a known failed run"
                )
            if previous.selector != selector or previous.steps != selected:
                raise ResumeMismatchError(
                    "resume selector and canonical steps must match the original run"
                )
            if previous.metadata.get("status") != "FAILED":
                raise ResumeMismatchError("only a failed run can be resumed")
        context = PipelineContext(
            run_id=resume_run_id or str(uuid.uuid4()),
            selector=selector,
            steps=selected,
            cycle_watermark=(
                previous.cycle_watermark
                if previous
                else datetime.now(UTC) - timedelta(hours=interval_hours)
            ),
            completed=set(previous.completed) if previous else set(),
        )
        owner_token = str(uuid.uuid4())
        lease_keys: list[tuple[str, str]] = []
        if selector.startswith(("product:", "product_code:")):
            lease_keys.append(("product_pipeline", selector))
        elif selector in {"cycle", "all-products"}:
            lease_keys.append(("cycle", "all"))
            if self.product_ids is not None:
                lease_keys.extend(
                    ("product_pipeline", f"product:{product_id}")
                    for product_id in self.product_ids(context)
                )
        acquired_keys: list[tuple[str, str]] = []
        try:
            for lease_key in lease_keys:
                if not self.lease_store.acquire(
                    lease_key[0], lease_key[1], owner_token, context.run_id
                ):
                    raise LeaseBusyError(
                        f"active lease exists for {lease_key[0]}:{lease_key[1]}"
                    )
                acquired_keys.append(lease_key)
        except Exception:
            for lease_key in reversed(acquired_keys):
                self.lease_store.release(lease_key[0], lease_key[1], owner_token)
            raise
        self.runs[context.run_id] = context
        try:
            for step in CANONICAL_STEPS:
                if step not in selected or step in context.completed:
                    continue
                if self._shutdown:
                    break
                handler = self.step_handlers.get(step)
                history_row = None
                checkpoint: dict[str, object] = {
                    "selector": context.selector,
                    "steps": list(context.steps),
                    "cycle_watermark": context.cycle_watermark.isoformat(),
                    "completed": sorted(context.completed),
                    "step_checkpoints": {
                        step: value.isoformat()
                        for step, value in context.step_checkpoints.items()
                    },
                    "metadata": dict(context.metadata),
                }
                store = self.run_store
                if store is not None:
                    history_row = store.record_step(
                        run_id=context.run_id,
                        step_name=step,
                        scope_key=context.selector,
                        status="RUNNING",
                        checkpoint=checkpoint,
                    )
                try:
                    if lease_keys:
                        heartbeat = getattr(self.lease_store, "heartbeat", None)
                        if heartbeat is not None:
                            for lease_key in lease_keys:
                                if not heartbeat(
                                    lease_key[0], lease_key[1], owner_token
                                ):
                                    raise LeaseHeartbeatLostError(
                                        f"lease heartbeat lost for {lease_key[0]}:{lease_key[1]}"
                                    )
                    if handler is None:
                        raise StepHandlerNotConfigured(
                            f"no handler configured for pipeline step: {step}"
                        )
                    self._run_handler_with_heartbeat(
                        handler,
                        context,
                        lease_keys=lease_keys,
                        owner_token=owner_token,
                    )
                    context.completed.add(step)
                    context.step_checkpoints[step] = datetime.now(UTC)
                    if history_row is not None and store is not None:
                        checkpoint["completed"] = sorted(context.completed)
                        checkpoint["step_checkpoints"] = {
                            name: value.isoformat()
                            for name, value in context.step_checkpoints.items()
                        }
                        checkpoint["metadata"] = dict(context.metadata)
                        store.complete(history_row, checkpoint=checkpoint)
                except Exception as error:
                    if history_row is not None and store is not None:
                        store.fail(
                            history_row,
                            error_code=type(error).__name__,
                        )
                    raise
            context.metadata["status"] = "COMPLETED"
            return context
        except Exception as error:
            context.metadata["status"] = "FAILED"
            context.metadata["error"] = str(error)
            raise
        finally:
            for lease_key in reversed(acquired_keys):
                self.lease_store.release(lease_key[0], lease_key[1], owner_token)

    def _run_handler_with_heartbeat(
        self,
        handler: Callable[[PipelineContext], None],
        context: PipelineContext,
        *,
        lease_keys: list[tuple[str, str]],
        owner_token: str,
    ) -> None:
        if not lease_keys:
            handler(context)
            return
        heartbeat = getattr(self.lease_store, "heartbeat", None)
        if not callable(heartbeat):
            handler(context)
            return
        interval = max(
            0.01, float(getattr(self.lease_store, "heartbeat_seconds", 15.0))
        )
        stop = Event()
        lost = Event()

        def heartbeat_loop() -> None:
            while not stop.wait(interval):
                try:
                    for lease_key in lease_keys:
                        if not heartbeat(lease_key[0], lease_key[1], owner_token):
                            lost.set()
                            return
                except Exception:  # noqa: BLE001 - lease loss fails the run closed
                    lost.set()
                    return

        watchdog = Thread(target=heartbeat_loop, name="pipeline-lease-heartbeat")
        watchdog.daemon = True
        watchdog.start()
        try:
            handler(context)
        finally:
            stop.set()
            watchdog.join(timeout=interval + 1.0)
        if lost.is_set():
            raise LeaseHeartbeatLostError(
                "lease heartbeat lost for "
                + ",".join(f"{kind}:{scope}" for kind, scope in lease_keys)
            )

    def run_forever(
        self, *, selector: str, steps: str | Iterable[str], interval_hours: float
    ) -> None:
        if interval_hours <= 0:
            raise ValueError("foreground interval must be positive")
        while not self._shutdown:
            self.run_once(
                selector=selector,
                steps=steps,
                interval_hours=interval_hours,
            )
            if self._shutdown:
                break
            time.sleep(interval_hours * 3600)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the canonical Oliview pipeline")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--product-id", type=int)
    selector.add_argument("--product-code")
    selector.add_argument("--all-products", action="store_true")
    selector.add_argument("--cycle", action="store_true")
    parser.add_argument("--steps", default="all")
    parser.add_argument("--interval-hours", type=float, default=0)
    parser.add_argument("--resume-run-id")
    return parser


def failure_event(
    *,
    selector: str,
    steps: str | Iterable[str],
    error: BaseException,
    run_id: str | None = None,
) -> dict[str, object]:
    """Return an operator-readable, secret-free failure record."""
    return {
        "event": "pipeline_failed",
        "status": "FAILED",
        "selector": selector,
        "steps": list(steps) if not isinstance(steps, str) else steps,
        "run_id": run_id,
        "error_code": type(error).__name__,
        "message": str(error),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    selector = resolve_selector(
        product_id=args.product_id,
        product_code=args.product_code,
    ) if args.product_id is not None or args.product_code is not None else (
        "cycle" if args.cycle else "all-products"
    )
    runner: PipelineRunner | None = None
    try:
        if (
            args.interval_hours == 0
            and os.getenv("MYSQL_USER")
            and os.getenv("MYSQL_PASSWORD")
        ):
            from oliview_core.db.connection import create_mysql_engine, session_scope
            from oliview_core.db.lease import SqlAlchemyLeaseStore
            from oliview_core.db.orm import Product
            from sqlalchemy import select

            from .persistence import SqlAlchemyRunStore
            from .runtime import build_green_handlers

            engine = create_mysql_engine()
            with session_scope(engine) as session:
                if args.product_code is not None:
                    product_id = session.scalar(
                        select(Product.product_id).where(
                            Product.product_code == args.product_code.strip()
                        )
                    )
                    selector = resolve_selector(
                        product_code=args.product_code,
                        lookup=lambda _code: product_id,
                    )
                runner = PipelineRunner(
                    step_handlers=build_green_handlers(session),
                    lease_store=SqlAlchemyLeaseStore(session),
                    run_store=SqlAlchemyRunStore(session),
                    product_ids=lambda _context: session.scalars(
                        select(Product.product_id)
                        .where(Product.is_active.is_(True))
                        .order_by(Product.product_id)
                    ).all(),
                )
                signal.signal(signal.SIGINT, runner.stop)
                signal.signal(signal.SIGTERM, runner.stop)
                runner.run_once(
                    selector=selector, steps=args.steps, resume_run_id=args.resume_run_id
                )
        else:
            if args.product_code is not None:
                raise RuntimeError(
                    "--product-code requires a MySQL-backed pipeline runner"
                )
            runner = PipelineRunner()
            signal.signal(signal.SIGINT, runner.stop)
            signal.signal(signal.SIGTERM, runner.stop)
            if args.interval_hours == 0:
                runner.run_once(
                    selector=selector, steps=args.steps, resume_run_id=args.resume_run_id
                )
            else:
                runner.run_forever(
                    selector=selector, steps=args.steps, interval_hours=args.interval_hours
                )
        return 0
    except Exception as error:  # noqa: BLE001 - CLI boundary must report all failures
        run_id = next(reversed(runner.runs), None) if runner and runner.runs else None
        print(
            json.dumps(
                failure_event(
                    selector=selector,
                    steps=args.steps,
                    error=error,
                    run_id=run_id,
                ),
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
