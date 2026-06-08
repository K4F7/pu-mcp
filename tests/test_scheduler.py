from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from pu_tool.errors import BusinessError, NetworkError, RiskControlError
from pu_tool.models import SignupPlan
from pu_tool.scheduler import LocalSignupScheduler
from pu_tool.storage import Storage


class FakeSignupService:
    def __init__(self, storage, failures=None):
        self.storage = storage
        self.failures = list(failures or [])
        self.calls = 0

    def list_signup_plans(self):
        return self.storage.list_plans()

    async def execute_signup_plan(self, plan_id):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        plan = self.storage.get_plan(plan_id)
        return self.storage.record_attempt_status(plan, "succeeded", "ok")


@pytest.mark.asyncio
async def test_scheduler_runs_due_plan_once_by_default(tmp_path):
    storage = Storage(tmp_path / "pu.sqlite")
    plan = storage.create_plan(
        SignupPlan(activity_id="ACT-1001", activity_title="x", run_at=datetime.now(UTC))
    )
    service = FakeSignupService(storage)
    scheduler = LocalSignupScheduler(service=service, storage=storage, retry_sleep=0)
    await scheduler.run_plan_now(plan.plan_id)
    assert service.calls == 1
    assert storage.get_plan(plan.plan_id).status == "succeeded"


@pytest.mark.asyncio
async def test_scheduler_retries_network_only_with_limit(tmp_path):
    storage = Storage(tmp_path / "pu.sqlite")
    plan = storage.create_plan(
        SignupPlan(
            activity_id="ACT-1001", activity_title="x", run_at=datetime.now(UTC), max_attempts=3
        )
    )
    service = FakeSignupService(
        storage, failures=[NetworkError("temporary"), NetworkError("temporary")]
    )
    scheduler = LocalSignupScheduler(service=service, storage=storage, retry_sleep=0)
    await scheduler.run_plan_now(plan.plan_id)
    assert service.calls == 3
    assert len(storage.list_attempts(plan_id=plan.plan_id)) == 3
    statuses = [attempt.status for attempt in storage.list_attempts(plan_id=plan.plan_id)]
    assert statuses == ["retrying", "retrying", "succeeded"]


@pytest.mark.asyncio
async def test_scheduler_business_failure_does_not_retry(tmp_path):
    storage = Storage(tmp_path / "pu.sqlite")
    plan = storage.create_plan(
        SignupPlan(
            activity_id="ACT-1001", activity_title="x", run_at=datetime.now(UTC), max_attempts=3
        )
    )
    service = FakeSignupService(storage, failures=[BusinessError("full")])
    scheduler = LocalSignupScheduler(service=service, storage=storage, retry_sleep=0)
    await scheduler.run_plan_now(plan.plan_id)
    assert service.calls == 1
    assert storage.get_plan(plan.plan_id).status == "failed"


@pytest.mark.asyncio
async def test_scheduler_risk_failure_records_risk_and_disables(tmp_path):
    storage = Storage(tmp_path / "pu.sqlite")
    plan = storage.create_plan(
        SignupPlan(activity_id="ACT-1001", activity_title="x", run_at=datetime.now(UTC))
    )
    service = FakeSignupService(storage, failures=[RiskControlError("captcha")])
    scheduler = LocalSignupScheduler(service=service, storage=storage, retry_sleep=0)
    await scheduler.run_plan_now(plan.plan_id)
    attempts = storage.list_attempts(plan_id=plan.plan_id)
    assert attempts[0].risk_flag is True
    assert storage.get_plan(plan.plan_id).enabled is False


@pytest.mark.asyncio
async def test_scheduler_prevents_same_plan_concurrent_execution(tmp_path):
    storage = Storage(tmp_path / "pu.sqlite")
    plan = storage.create_plan(
        SignupPlan(activity_id="ACT-1001", activity_title="x", run_at=datetime.now(UTC))
    )
    service = FakeSignupService(storage)
    scheduler = LocalSignupScheduler(service=service, storage=storage, retry_sleep=0)
    await asyncio.gather(scheduler.run_plan_now(plan.plan_id), scheduler.run_plan_now(plan.plan_id))
    assert service.calls == 1


@pytest.mark.asyncio
async def test_scheduler_network_error_only_fails_on_last_attempt(tmp_path):
    storage = Storage(tmp_path / "pu.sqlite")
    plan = storage.create_plan(
        SignupPlan(
            activity_id="ACT-1001", activity_title="x", run_at=datetime.now(UTC), max_attempts=2
        )
    )
    service = FakeSignupService(
        storage, failures=[NetworkError("temporary"), NetworkError("temporary")]
    )
    scheduler = LocalSignupScheduler(service=service, storage=storage, retry_sleep=0)

    await scheduler.run_plan_now(plan.plan_id)

    current = storage.get_plan(plan.plan_id)
    assert current.status == "failed"
    assert current.enabled is False
    statuses = [attempt.status for attempt in storage.list_attempts(plan_id=plan.plan_id)]
    assert statuses == ["retrying", "failed"]


def test_scheduler_restores_all_enabled_executable_states(tmp_path):
    storage = Storage(tmp_path / "pu.sqlite")
    scheduled = storage.create_plan(
        SignupPlan(activity_id="ACT-1001", activity_title="x", run_at=datetime.now(UTC))
    )
    retrying = storage.create_plan(
        SignupPlan(
            activity_id="ACT-1002",
            activity_title="x",
            run_at=datetime.now(UTC),
            status="retrying",
        )
    )
    running = storage.create_plan(
        SignupPlan(
            activity_id="ACT-1003",
            activity_title="x",
            run_at=datetime.now(UTC),
            status="running",
        )
    )
    failed = storage.create_plan(
        SignupPlan(
            activity_id="ACT-1004",
            activity_title="x",
            run_at=datetime.now(UTC),
            status="failed",
            enabled=False,
        )
    )
    scheduler = LocalSignupScheduler(service=FakeSignupService(storage), storage=storage)
    scheduler.restore_jobs()

    jobs = {job.id for job in scheduler._scheduler.get_jobs()}
    assert jobs == {
        f"signup-{scheduled.plan_id}",
        f"signup-{retrying.plan_id}",
        f"signup-{running.plan_id}",
    }
    assert f"signup-{failed.plan_id}" not in jobs


def test_scheduler_cancel_plan_removes_registered_job(tmp_path):
    storage = Storage(tmp_path / "pu.sqlite")
    plan = storage.create_plan(
        SignupPlan(activity_id="ACT-1001", activity_title="x", run_at=datetime.now(UTC))
    )
    scheduler = LocalSignupScheduler(service=FakeSignupService(storage), storage=storage)
    scheduler.register_plan(plan.plan_id, plan.run_at)

    scheduler.cancel_plan(plan.plan_id)

    assert scheduler._scheduler.get_job(f"signup-{plan.plan_id}") is None


def test_scheduler_register_plan_converts_naive_datetime_to_local_aware(tmp_path):
    storage = Storage(tmp_path / "pu.sqlite")
    scheduler = LocalSignupScheduler(service=FakeSignupService(storage), storage=storage)
    naive_run_at = datetime(2026, 6, 8, 18, 30)

    scheduler.register_plan(1, naive_run_at)

    job = scheduler._scheduler.get_job("signup-1")
    assert job is not None
    assert job.trigger.run_date.tzinfo is not None
    assert job.trigger.run_date.utcoffset() is not None
    assert job.trigger.run_date.hour == 18
    assert job.trigger.run_date.minute == 30
