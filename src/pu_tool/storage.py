from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from pu_tool.models import Activity, SignupAttempt, SignupPlan


class DuplicatePlanError(ValueError):
    pass


def _dt(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _iso(value: datetime) -> str:
    return value.isoformat()


class Storage:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS signup_plans (
                    plan_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    activity_id TEXT NOT NULL,
                    activity_title TEXT NOT NULL,
                    run_at TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    max_attempts INTEGER NOT NULL,
                    attempt_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS ux_active_plan
                ON signup_plans(activity_id, run_at)
                WHERE enabled = 1 AND status IN ('scheduled', 'running', 'retrying');
                CREATE TABLE IF NOT EXISTS signup_attempts (
                    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id INTEGER NOT NULL,
                    activity_id TEXT NOT NULL,
                    attempted_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    response_code TEXT,
                    message TEXT NOT NULL,
                    risk_flag INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS activity_cache (
                    activity_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute("DROP INDEX IF EXISTS ux_active_plan")
            conn.execute(
                """
                CREATE UNIQUE INDEX ux_active_plan
                ON signup_plans(activity_id, run_at)
                WHERE enabled = 1 AND status IN ('scheduled', 'running', 'retrying')
                """
            )

    def create_plan(self, plan: SignupPlan) -> SignupPlan:
        now = datetime.now(UTC)
        plan = plan.model_copy(update={"created_at": plan.created_at or now, "updated_at": now})
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO signup_plans
                    (activity_id, activity_title, run_at, enabled, status, max_attempts,
                     attempt_count, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        plan.activity_id,
                        plan.activity_title,
                        _iso(plan.run_at),
                        int(plan.enabled),
                        plan.status,
                        plan.max_attempts,
                        plan.attempt_count,
                        _iso(plan.created_at),
                        _iso(plan.updated_at),
                    ),
                )
                return plan.model_copy(update={"plan_id": int(cursor.lastrowid)})
        except sqlite3.IntegrityError as exc:
            raise DuplicatePlanError(
                "active signup plan already exists for this activity and time"
            ) from exc

    def _row_to_plan(self, row: sqlite3.Row) -> SignupPlan:
        return SignupPlan(
            plan_id=row["plan_id"],
            activity_id=row["activity_id"],
            activity_title=row["activity_title"],
            run_at=_dt(row["run_at"]),
            enabled=bool(row["enabled"]),
            status=row["status"],
            max_attempts=row["max_attempts"],
            attempt_count=row["attempt_count"],
            created_at=_dt(row["created_at"]),
            updated_at=_dt(row["updated_at"]),
        )

    def get_plan(self, plan_id: int) -> SignupPlan:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM signup_plans WHERE plan_id = ?", (plan_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"signup plan not found: {plan_id}")
        return self._row_to_plan(row)

    def list_plans(self) -> list[SignupPlan]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM signup_plans ORDER BY run_at, plan_id").fetchall()
        return [self._row_to_plan(row) for row in rows]

    def update_plan_status(
        self,
        plan_id: int,
        status: str,
        *,
        enabled: bool | None = None,
        increment_attempt: bool = False,
    ) -> SignupPlan:
        plan = self.get_plan(plan_id)
        values = {
            "status": status,
            "enabled": plan.enabled if enabled is None else enabled,
            "attempt_count": plan.attempt_count + (1 if increment_attempt else 0),
            "updated_at": datetime.now(UTC),
        }
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE signup_plans
                SET status = ?, enabled = ?, attempt_count = ?, updated_at = ?
                WHERE plan_id = ?
                """,
                (
                    values["status"],
                    int(values["enabled"]),
                    values["attempt_count"],
                    _iso(values["updated_at"]),
                    plan_id,
                ),
            )
        return self.get_plan(plan_id)

    def cancel_plan(self, plan_id: int) -> SignupPlan:
        return self.update_plan_status(plan_id, "cancelled", enabled=False)

    def record_attempt(self, attempt: SignupAttempt) -> SignupAttempt:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO signup_attempts
                (plan_id, activity_id, attempted_at, status, response_code, message, risk_flag)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt.plan_id,
                    attempt.activity_id,
                    _iso(attempt.attempted_at),
                    attempt.status,
                    attempt.response_code,
                    attempt.message,
                    int(attempt.risk_flag),
                ),
            )
        return attempt.model_copy(update={"attempt_id": int(cursor.lastrowid)})

    def record_attempt_status(
        self,
        plan: SignupPlan,
        status: str,
        message: str,
        *,
        response_code: str | None = None,
        risk_flag: bool = False,
    ) -> SignupAttempt:
        attempt = self.record_attempt(
            SignupAttempt(
                plan_id=plan.plan_id or 0,
                activity_id=plan.activity_id,
                status=status,
                response_code=response_code,
                message=message,
                risk_flag=risk_flag,
            )
        )
        if status in {"succeeded", "skipped"}:
            self.update_plan_status(
                plan.plan_id or 0,
                "succeeded",
                enabled=False,
                increment_attempt=True,
            )
        elif status == "retrying":
            self.update_plan_status(
                plan.plan_id or 0,
                "retrying",
                enabled=True,
                increment_attempt=True,
            )
        else:
            self.update_plan_status(
                plan.plan_id or 0,
                "failed",
                enabled=False,
                increment_attempt=True,
            )
        return attempt

    def _row_to_attempt(self, row: sqlite3.Row) -> SignupAttempt:
        return SignupAttempt(
            attempt_id=row["attempt_id"],
            plan_id=row["plan_id"],
            activity_id=row["activity_id"],
            attempted_at=_dt(row["attempted_at"]),
            status=row["status"],
            response_code=row["response_code"],
            message=row["message"],
            risk_flag=bool(row["risk_flag"]),
        )

    def list_attempts(
        self, plan_id: int | None = None, activity_id: str | None = None
    ) -> list[SignupAttempt]:
        query = "SELECT * FROM signup_attempts"
        clauses: list[str] = []
        params: list[object] = []
        if plan_id is not None:
            clauses.append("plan_id = ?")
            params.append(plan_id)
        if activity_id is not None:
            clauses.append("activity_id = ?")
            params.append(activity_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY attempted_at, attempt_id"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_attempt(row) for row in rows]

    def cache_activity(self, activity: Activity) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO activity_cache(activity_id, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(activity_id) DO UPDATE SET
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (activity.activity_id, activity.model_dump_json(), _iso(datetime.now(UTC))),
            )

    def get_cached_activity(
        self, activity_id: str, max_age_seconds: float | None = None
    ) -> Activity | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload, updated_at FROM activity_cache WHERE activity_id = ?",
                (activity_id,),
            ).fetchone()
        if row is None or self._is_cache_stale(_dt(row["updated_at"]), max_age_seconds):
            return None
        return Activity.model_validate_json(row["payload"])

    def list_cached_activities(self, max_age_seconds: float | None = None) -> list[Activity]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload, updated_at FROM activity_cache ORDER BY activity_id"
            ).fetchall()
        activities = []
        for row in rows:
            if not self._is_cache_stale(_dt(row["updated_at"]), max_age_seconds):
                activities.append(Activity.model_validate_json(row["payload"]))
        return activities

    def _is_cache_stale(
        self, updated_at: datetime | None, max_age_seconds: float | None
    ) -> bool:
        if updated_at is None or max_age_seconds is None:
            return False
        now = datetime.now(updated_at.tzinfo or UTC)
        return (now - updated_at).total_seconds() > max_age_seconds
