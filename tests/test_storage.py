from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pu_tool.models import SignupAttempt, SignupPlan
from pu_tool.storage import DuplicatePlanError, Storage


def test_storage_persists_plan_and_attempt(tmp_path):
    db_path = tmp_path / "pu.sqlite"
    storage = Storage(db_path)
    run_at = datetime(2026, 6, 8, 18, 30, tzinfo=UTC)
    plan = storage.create_plan(
        SignupPlan(activity_id="ACT-1001", activity_title="合成活动", run_at=run_at)
    )
    storage.record_attempt(
        SignupAttempt(
            plan_id=plan.plan_id, activity_id=plan.activity_id, status="succeeded", message="ok"
        )
    )
    restored = Storage(db_path)
    assert restored.list_plans()[0].plan_id == plan.plan_id
    assert restored.list_attempts(plan_id=plan.plan_id)[0].status == "succeeded"


def test_storage_rejects_duplicate_active_plan(tmp_path):
    storage = Storage(tmp_path / "pu.sqlite")
    run_at = datetime(2026, 6, 8, 18, 30, tzinfo=UTC)
    storage.create_plan(
        SignupPlan(activity_id="ACT-1001", activity_title="合成活动", run_at=run_at)
    )
    with pytest.raises(DuplicatePlanError):
        storage.create_plan(
            SignupPlan(activity_id="ACT-1001", activity_title="合成活动", run_at=run_at)
        )


def test_storage_rejects_duplicate_retrying_plan(tmp_path):
    storage = Storage(tmp_path / "pu.sqlite")
    run_at = datetime(2026, 6, 8, 18, 30, tzinfo=UTC)
    plan = storage.create_plan(
        SignupPlan(activity_id="ACT-1001", activity_title="合成活动", run_at=run_at)
    )
    storage.update_plan_status(plan.plan_id, "retrying")

    with pytest.raises(DuplicatePlanError):
        storage.create_plan(
            SignupPlan(activity_id="ACT-1001", activity_title="合成活动", run_at=run_at)
        )


def test_storage_cancel_plan(tmp_path):
    storage = Storage(tmp_path / "pu.sqlite")
    plan = storage.create_plan(
        SignupPlan(activity_id="ACT-1001", activity_title="合成活动", run_at=datetime.now(UTC))
    )
    cancelled = storage.cancel_plan(plan.plan_id)
    assert cancelled.status == "cancelled"
    assert not cancelled.enabled
