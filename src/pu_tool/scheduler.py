from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from pu_tool.errors import BusinessError, NetworkError, RiskControlError
from pu_tool.storage import Storage
from pu_tool.time_utils import ensure_aware_local


class LocalSignupScheduler:
    def __init__(self, service, storage: Storage, retry_sleep: float = 1):
        self.service = service
        self.storage = storage
        self.retry_sleep = retry_sleep
        self._locks: dict[int, asyncio.Lock] = {}
        self._scheduler = AsyncIOScheduler(timezone="UTC")

    def restore_jobs(self) -> None:
        for plan in self.storage.list_plans():
            if plan.enabled and plan.status in {"scheduled", "retrying", "running"}:
                self.register_plan(plan.plan_id or 0, plan.run_at)

    def register_plan(self, plan_id: int, run_at: datetime) -> None:
        run_at = ensure_aware_local(run_at)
        self._scheduler.add_job(
            self.run_plan_now,
            "date",
            run_date=run_at,
            args=[plan_id],
            id=f"signup-{plan_id}",
            replace_existing=True,
            max_instances=1,
        )

    def cancel_plan(self, plan_id: int) -> None:
        try:
            self._scheduler.remove_job(f"signup-{plan_id}")
        except JobLookupError:
            pass

    def start(self) -> None:
        if not self._scheduler.running:
            self.restore_jobs()
            self._scheduler.start()

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    async def run_plan_now(self, plan_id: int):
        lock = self._locks.setdefault(plan_id, asyncio.Lock())
        if lock.locked():
            return None
        async with lock:
            plan = self.storage.get_plan(plan_id)
            if not plan.enabled or plan.status in {"succeeded", "cancelled"}:
                return None
            result = None
            remaining_attempts = plan.max_attempts - plan.attempt_count
            if remaining_attempts <= 0:
                self.storage.update_plan_status(plan_id, "failed", enabled=False)
                return None
            for index in range(remaining_attempts):
                current = self.storage.get_plan(plan_id)
                try:
                    result = await self.service.execute_signup_plan(plan_id)
                    return result
                except NetworkError as exc:
                    is_last_attempt = index >= remaining_attempts - 1
                    result = self.storage.record_attempt_status(
                        current,
                        "failed" if is_last_attempt else "retrying",
                        str(exc),
                    )
                    if is_last_attempt:
                        self.storage.update_plan_status(plan_id, "failed", enabled=False)
                        return result
                    await asyncio.sleep(self.retry_sleep)
                except RiskControlError as exc:
                    result = self.storage.record_attempt_status(
                        current,
                        "failed",
                        str(exc),
                        risk_flag=True,
                    )
                    self.storage.update_plan_status(plan_id, "failed", enabled=False)
                    return result
                except BusinessError as exc:
                    result = self.storage.record_attempt_status(current, "failed", str(exc))
                    self.storage.update_plan_status(plan_id, "failed", enabled=False)
                    return result
            self.storage.update_plan_status(plan_id, "failed", enabled=False)
            return result


def utc_now() -> datetime:
    return datetime.now(UTC)
