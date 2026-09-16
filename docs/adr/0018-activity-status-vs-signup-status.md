# 活动状态与报名状态分离

`status` / `statusName` 是活动本身（未开始/进行中/已结束），不是能不能报。现场存在「活动进行中、报名已结束」。

`signup_status` / `allow_signup` 才是报名窗口：

- list `/apis/activity/list`：人读报名状态在 `startTimeValue`（报名进行中/报名已结束/报名未开始）；报名开始时刻是 `joinStartTime`（list 常无 `joinEndTime`）
- info `/apis/activity/info`：无 `startTimeValue`。报名窗口是 `baseInfo.joinStartTime` / `joinEndTime`；`buttonInfo` 在可报时为 `{"name":"报名","event":"join"}`，未开始为名称含「报名未开始」，结束后未报常为「未报名」
- `allow_signup` 为 true 当且仅当 `signup_status == 报名进行中` 或 `buttonInfo` 含 `event==join`

不要把 `allowJoinCount`（live 常为 0）、`joinStatus` / `hasJoin` / `signed_in`（用户是否已报/已签）当成报名窗口。
