# 持久任务不自建 daemon

到点抢、开抢提醒、参加提醒交给 Hermes / OpenClaw。到点抢是无模型一次执行 `pu signup run {plan_id}`；开抢提醒和参加提醒是 agent 任务。本仓库不自建 daemon，不 import 调度宿主 SDK。
