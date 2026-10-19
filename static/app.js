(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const listEl = $("#tasks"), stateEl = $("#state");
  let tasks = [], filter = "all", editingId = null;

  const savedTheme = (() => { try { return localStorage.getItem("theme"); } catch (e) { return null; } })();
  document.documentElement.dataset.theme = savedTheme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  $("#theme").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("theme", next); } catch (e) { /* ignore */ }
  });

  function toast(msg, isError) {
    const el = document.createElement("div");
    el.className = "toast" + (isError ? " error" : "");
    el.textContent = msg;
    $("#toasts").appendChild(el);
    setTimeout(() => el.remove(), 3500);
  }
  async function api(path, opts) {
    const res = await fetch(path, Object.assign({ headers: { "Content-Type": "application/json" } }, opts));
    if (res.status === 204) return null;
    let data = null;
    try { data = await res.json(); } catch (e) { /* non-JSON */ }
    if (!res.ok) throw new Error((data && data.error) || ("Request failed (" + res.status + ")"));
    return data;
  }

  async function checkHealth() {
    const el = $("#health");
    try {
      const h = await api("/health");
      el.className = "badge health up"; el.querySelector("b").textContent = "Healthy";
      $("#env-badge").textContent = "ENV: " + h.environment;
      $("#version").textContent = "v" + h.version;
    } catch (e) {
      el.className = "badge health down"; el.querySelector("b").textContent = "Unreachable";
    }
  }

  function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
  function render() {
    const total = tasks.length, done = tasks.filter((t) => t.completed).length;
    $("#c-total").textContent = total; $("#c-done").textContent = done; $("#c-pending").textContent = total - done;
    const shown = tasks.filter((t) => filter === "all" || (filter === "completed") === t.completed);
    listEl.replaceChildren();
    stateEl.textContent = shown.length ? "" : (total ? "No tasks match this filter." : "No tasks yet. Add your first task above.");
    for (const t of shown) listEl.appendChild(row(t));
  }
  function row(t) {
    const li = el("li", "task" + (t.completed ? " done" : ""));
    const cb = el("input"); cb.type = "checkbox"; cb.checked = t.completed; cb.setAttribute("aria-label", "Mark complete");
    cb.addEventListener("change", () => update(t.id, { completed: cb.checked }, cb.checked ? "Task completed" : "Task reopened"));
    const body = el("div");
    const title = el("div", "t-title", t.title);
    title.appendChild(el("span", "pill " + t.priority, t.priority));
    title.appendChild(el("span", "pill status" + (t.completed ? " done" : ""), t.completed ? "completed" : "pending"));
    body.appendChild(title);
    if (t.description) body.appendChild(el("div", "t-desc", t.description));
    const actions = el("div", "actions");
    const edit = el("button", "btn sm", "Edit"); edit.addEventListener("click", () => openEdit(t));
    const del = el("button", "btn sm danger", "Delete"); del.addEventListener("click", () => remove(t, del));
    actions.append(edit, del);
    li.append(cb, body, actions);
    return li;
  }

  async function load() {
    stateEl.textContent = "Loading tasks...";
    try { tasks = (await api("/api/tasks")).tasks; render(); }
    catch (e) { stateEl.textContent = "Could not load tasks: " + e.message; toast(e.message, true); }
  }
  async function update(id, changes, msg) {
    try { const t = await api("/api/tasks/" + id, { method: "PATCH", body: JSON.stringify(changes) });
      tasks = tasks.map((x) => (x.id === id ? t : x)); render(); toast(msg || "Task updated"); }
    catch (e) { toast(e.message, true); load(); }
  }
  async function remove(t, btn) {
    if (!confirm('Delete "' + t.title + '"?')) return;
    btn.disabled = true;
    try { await api("/api/tasks/" + t.id, { method: "DELETE" }); tasks = tasks.filter((x) => x.id !== t.id); render(); toast("Task deleted"); }
    catch (e) { toast(e.message, true); load(); }
  }

  $("#add-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const title = $("#f-title").value.trim();
    if (!title) { toast("Title is required.", true); return; }
    const btn = ev.target.querySelector("button"); btn.disabled = true;
    try {
      const t = await api("/api/tasks", { method: "POST", body: JSON.stringify({ title, description: $("#f-desc").value, priority: $("#f-prio").value }) });
      tasks.unshift(t); render(); ev.target.reset(); toast("Task added");
    } catch (e) { toast(e.message, true); } finally { btn.disabled = false; }
  });

  const dlg = $("#edit-dialog");
  function openEdit(t) { editingId = t.id; $("#e-title").value = t.title; $("#e-desc").value = t.description; $("#e-prio").value = t.priority; dlg.showModal(); }
  $("#e-cancel").addEventListener("click", () => dlg.close());
  $("#edit-form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const title = $("#e-title").value.trim();
    if (!title) { toast("Title is required.", true); return; }
    dlg.close();
    update(editingId, { title, description: $("#e-desc").value, priority: $("#e-prio").value }, "Task saved");
  });

  document.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => {
    document.querySelectorAll(".chip").forEach((x) => x.classList.remove("active"));
    c.classList.add("active"); filter = c.dataset.filter; render();
  }));

  checkHealth(); setInterval(checkHealth, 15000); load();
})();
