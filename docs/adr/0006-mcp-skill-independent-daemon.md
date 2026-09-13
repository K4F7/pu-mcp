# Agent 用标准 MCP + skill；持久任务不自建 daemon

网页不做。Agent 通过标准 MCP 调能力，用 skill 读注意事项。持久调度交给 Hermes / OpenClaw：到点抢是无模型一次执行本工具入口；开抢提醒和参加提醒是 agent 任务。本仓库不自建 daemon，不 import 调度宿主 SDK。
