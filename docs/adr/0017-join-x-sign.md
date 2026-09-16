# join 使用 X-Sign 与数字 activityId

`POST /apis/activity/join` 在 live PU 上要求 JSON 数字 `activityId` 和 `X-Sign`（AES-CBC，算法见 `src/pu_mcp/x_sign.py`，与 PU 网页端 / PU-SignUpBot 一致）。缺签或 id 为字符串会返回「请更新到最新版本」。仅 join 带 X-Sign；其它接口不变。非数字 id 在客户端拒绝。
