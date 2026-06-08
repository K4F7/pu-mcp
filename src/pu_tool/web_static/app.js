const root = document.querySelector("#app-root");
const view = document.body.dataset.view || "activities";

function el(tagName, options = {}, children = []) {
  const node = document.createElement(tagName);
  if (options.className) node.className = options.className;
  if (options.text !== undefined) node.textContent = options.text;
  if (options.href) node.setAttribute("href", options.href);
  if (options.type) node.setAttribute("type", options.type);
  if (options.name) node.setAttribute("name", options.name);
  if (options.value !== undefined) node.setAttribute("value", options.value);
  if (options.min !== undefined) node.setAttribute("min", options.min);
  if (options.max !== undefined) node.setAttribute("max", options.max);
  if (options.required) node.required = true;
  for (const child of children) {
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function textCell(value) {
  return el("td", { text: value ?? "-" });
}

function nodeCell(node) {
  return el("td", {}, [node]);
}

function table(headers, rows) {
  const thead = el("thead", {}, [
    el("tr", {}, headers.map((header) => el("th", { text: header }))),
  ]);
  const tbody = el(
    "tbody",
    {},
    rows.map((cells) => el("tr", {}, cells)),
  );
  return el("table", {}, [thead, tbody]);
}

function toolbar(title, actions = []) {
  return el("div", { className: "toolbar" }, [el("h1", { text: title }), ...actions]);
}

function notice(text) {
  return el("div", { className: "notice", text });
}

function scoreSummary(activity) {
  const items = activity.score_items || [];
  return items.map((item) => `${item.label}:${item.value}${item.unit || ""}`).join(" / ") || "-";
}

function showMessage(text, className = "notice") {
  const message = el("div", { className, text });
  root.prepend(message);
  return message;
}

async function requestJSON(url, options = {}) {
  const response = await fetch(url, options);
  if (response.ok) {
    if (response.status === 204) return null;
    return response.json();
  }
  let message = await response.text();
  try {
    const payload = JSON.parse(message);
    message = payload.error?.message || message;
  } catch {
    // Keep the plain response body.
  }
  throw new Error(message);
}

async function getJSON(url) {
  return requestJSON(url);
}

async function postJSON(url, payload) {
  return requestJSON(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function deleteJSON(url) {
  return requestJSON(url, { method: "DELETE" });
}

function createRefreshButton(handler) {
  const button = el("button", { type: "button", text: "强制刷新" });
  button.addEventListener("click", handler);
  return button;
}

function createPlanForm(defaults = {}) {
  const form = el("form", { className: "plan-form" });
  const activityId = el("input", {
    name: "activity_id",
    value: defaults.activity_id || "",
    required: true,
  });
  const title = el("input", {
    name: "activity_title",
    value: defaults.activity_title || defaults.activity_id || "",
    required: true,
  });
  const runAt = el("input", { name: "run_at", type: "datetime-local", required: true });
  const maxAttempts = el("input", {
    name: "max_attempts",
    type: "number",
    value: defaults.max_attempts || 1,
    min: 1,
    max: 3,
    required: true,
  });
  const submit = el("button", { type: "submit", text: "创建计划" });

  form.append(
    el("label", {}, ["Activity ID", activityId]),
    el("label", {}, ["标题", title]),
    el("label", {}, ["执行时间", runAt]),
    el("label", {}, ["最大尝试", maxAttempts]),
    submit,
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submit.disabled = true;
    try {
      await postJSON("/api/signup/plans", {
        activity_id: activityId.value,
        activity_title: title.value,
        run_at: new Date(runAt.value).toISOString(),
        max_attempts: Number(maxAttempts.value),
      });
      showMessage("计划已创建；保持 pu serve 运行后会按时执行。");
      if (view === "plans") await renderPlans();
    } finally {
      submit.disabled = false;
    }
  });
  return form;
}

async function renderActivities(refresh = false) {
  root.replaceChildren(
    toolbar("活动", [createRefreshButton(() => renderActivities(true))]),
    notice("默认优先使用本地缓存；强制刷新会访问配置的 PU API，请保持低频使用。"),
  );
  const activities = await getJSON(`/api/activities?refresh=${refresh ? "true" : "false"}`);
  const rows = activities.map((activity) => {
    const href = `/activities/${encodeURIComponent(activity.activity_id)}`;
    return [
      nodeCell(el("a", { href, text: activity.activity_id })),
      textCell(activity.title),
      textCell(activity.activity_type),
      textCell(`${activity.signup_start_time || "-"} ~ ${activity.signup_end_time || "-"}`),
      textCell(`${activity.start_time || "-"} ~ ${activity.end_time || "-"}`),
      textCell(scoreSummary(activity)),
    ];
  });
  root.append(
    table(["ID", "标题", "类型", "报名窗口", "活动时间", "加分/学分/积分"], rows),
  );
}

async function renderActivityDetail(activityId, refresh = false) {
  const encodedId = encodeURIComponent(activityId);
  const activity = await getJSON(`/api/activities/${encodedId}?refresh=${refresh ? "true" : "false"}`);
  root.replaceChildren(
    toolbar(activity.title, [
      createRefreshButton(() => renderActivityDetail(activityId, true)),
      el("a", { href: "/", text: "返回活动" }),
    ]),
    table(
      ["字段", "内容"],
      [
        [textCell("活动 ID"), textCell(activity.activity_id)],
        [textCell("类型"), textCell(activity.activity_type)],
        [textCell("组织方"), textCell(activity.organizer)],
        [textCell("地点"), textCell(activity.location)],
        [
          textCell("报名窗口"),
          textCell(`${activity.signup_start_time || "-"} ~ ${activity.signup_end_time || "-"}`),
        ],
        [
          textCell("活动时间"),
          textCell(`${activity.start_time || "-"} ~ ${activity.end_time || "-"}`),
        ],
        [textCell("加分/学分/积分"), textCell(scoreSummary(activity))],
      ],
    ),
    el("h2", { text: "创建报名计划" }),
    createPlanForm({
      activity_id: activity.activity_id,
      activity_title: activity.title,
    }),
  );
}

async function renderPlans() {
  const plans = await getJSON("/api/signup/plans");
  const rows = plans.map((plan) => {
    const cancel = el("button", { type: "button", text: "取消" });
    cancel.disabled = !plan.enabled || ["cancelled", "succeeded", "failed"].includes(plan.status);
    cancel.addEventListener("click", async () => {
      cancel.disabled = true;
      await deleteJSON(`/api/signup/plans/${encodeURIComponent(plan.plan_id)}`);
      await renderPlans();
    });
    return [
      textCell(plan.plan_id),
      textCell([plan.activity_id, plan.activity_title].filter(Boolean).join(" ")),
      textCell(plan.run_at),
      textCell(plan.status),
      textCell(`${plan.attempt_count}/${plan.max_attempts}`),
      nodeCell(cancel),
    ];
  });
  root.replaceChildren(
    toolbar("报名计划", [el("span", { className: "status", text: "默认 1 次，最多 3 次" })]),
    createPlanForm(),
    table(["ID", "活动", "执行时间", "状态", "尝试", "操作"], rows),
  );
}

async function renderAttempts() {
  const attempts = await getJSON("/api/signup/attempts");
  const rows = attempts.map((attempt) => [
    textCell(attempt.attempt_id),
    textCell(attempt.plan_id),
    textCell(attempt.activity_id),
    textCell(attempt.attempted_at),
    textCell(attempt.status),
    textCell(attempt.risk_flag ? "是" : "否"),
    textCell(attempt.message),
  ]);
  root.replaceChildren(
    toolbar("报名尝试记录", [
      el("span", { className: "status", text: "风控会停止自动操作" }),
    ]),
    table(["ID", "计划", "活动", "时间", "状态", "风险", "消息"], rows),
  );
}

async function renderSettings() {
  const status = await getJSON("/api/auth/status");
  root.replaceChildren(
    toolbar("设置", [el("span", { className: "status", text: "本地优先" })]),
    notice("仅用于本人账号；不会保存明文密码；token/sid 在状态输出中脱敏。"),
    el("pre", { text: JSON.stringify(status, null, 2) }),
  );
}

(async function boot() {
  try {
    if (view.startsWith("activity:")) {
      await renderActivityDetail(view.slice("activity:".length));
    } else if (view === "plans") {
      await renderPlans();
    } else if (view === "attempts") {
      await renderAttempts();
    } else if (view === "settings") {
      await renderSettings();
    } else {
      await renderActivities();
    }
  } catch (error) {
    root.replaceChildren(el("p", { className: "danger", text: error.message }));
  }
})();
