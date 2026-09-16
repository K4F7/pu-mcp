# join / cancel 使用 X-Sign 与数字 activityId

`POST /apis/activity/join` 与 `POST /apis/activity/cancel` 在 live PU 上使用 JSON 数字 `activityId`；join 缺签或 id 为字符串会返回「请更新到最新版本」。本仓库 join / cancel 均附带 `X-Sign`（AES-CBC，算法见 `src/pu_mcp/x_sign.py`，与 PU 网页端 / PU-SignUpBot / PocketUni-Client 一致）及 Origin/Referer，与 #28 对齐。其它接口不变。非数字 id 在客户端拒绝。
