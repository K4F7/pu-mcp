---
name: login-config
description: Help the user look up a PU school sid and log in locally. Use when the user needs to configure PU login, find a school sid from a Chinese school name, or is unauthenticated.
---

# 登录配置

只帮用户查出学校 sid，确认学校后再登录。不打开选学校页。不要在对话里收集、转述或保存密码。

- 交互式 / TTY：确认学校后让用户自己在本机终端运行 `pu login --sid …`；不要代跑、不要让用户把密码贴进对话。
- 无 TTY / Grok Bot / agent：可以非交互执行 `pu login`，一次传齐 `-u -p --sid`，或设好 `PU_USERNAME` / `PU_PASSWORD` / `PU_SID` 后直接 `pu login`（可省略标志）。优先 secret-request / 环境变量，不要把密码写进对话。`PU_SID` 是 `--sid` 的 typer envvar。

## 步骤

1. 若用户已给出数字学校 sid，跳到第 4 步。
2. 用学校查询（MCP `search_schools` 或 CLI `pu schools search <校名> --json`）按中文校名或拼音简称查。关键字不能为空。
3. 把匹配列表（id / name / short）给用户看。多个结果时列出匹配项，不要默默选一所学校。默认最多 20 条（`limit` 可改）；若结果被截断，说明还有更多匹配，请用户换更精确的关键字。请用户确认是哪一所。
4. 用户确认后：

   - 交互式 / TTY：告诉用户**自己**在终端运行：

     ```powershell
     pu login --sid 学校数字sid
     ```

   - 无 TTY / Grok Bot / agent：可非交互执行（占位符；不要向用户要密码贴进对话；优先 secret-request / `PU_USERNAME` / `PU_PASSWORD` / `PU_SID`）：

     ```bash
     uv run --python 3.12 --no-sync pu login
     ```

   把 sid 换成用户确认的那一项的 `id`（可设 `PU_SID` 或显式 `--sid`）。命令只接受 `--sid` 或 `--encoded-sid`，不接受中文校名。`PU_SID` 会作为 `--sid` 的 typer envvar 自动读取；显式 `--sid` 覆盖环境变量。
5. 登录完成后用 `auth_status`（MCP）或 `pu auth status` 确认已登录。返回是脱敏的，不要追问或回显密码、token。

## 禁止

- 不要向用户要密码，不要在对话里收集、转述或保存密码。需要密码时用环境变量或 Grok Bot secret-request，不要让用户把密码贴进聊天。
- 交互式 / TTY：不要替用户执行 `pu login`（该命令会提示输入密码）；让用户自己在终端登录。
- 无 TTY / Grok Bot / agent：可以非交互执行 `pu login`（一次传齐 `-u -p --sid`，或设好 `PU_USERNAME` / `PU_PASSWORD` / `PU_SID` 后省略标志），不要因此向用户在对话里要密码。
- 不要提供或调用 MCP login 工具；本工具没有 login。MCP 不收密码。
- 不要编造学校 sid。查不到就说明没匹配，请用户换关键字。
- 示例里不要写真实账号、密码、token。
