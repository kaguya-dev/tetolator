/* Tetolator frontend logic. No framework - plain DOM manipulation.
 *
 * Structure:
 *   - state          -> in-memory cache of the four data sets
 *   - loadAll()      -> fetch everything from the API on startup
 *   - renderers      -> one per tab (prints, clients, filaments, settings)
 *   - modal helpers  -> open/close a generic modal form
 *   - toast()        -> small feedback message
 */

const state = {
  settings: { currency: "$", cost_per_hour: 0, markup_percent: 0 },
  clients: [],
  filaments: [],
  prints: [],
  filters: { client: "", filament: "", from: "", to: "" },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function money(value) {
  const n = Number(value || 0);
  return state.settings.currency + n.toFixed(2);
}

function fmtDuration(hours, minutes) {
  const h = Number(hours || 0);
  const m = Number(minutes || 0);
  return `${h}h ${String(m).padStart(2, "0")}m`;
}

function toast(message, ok = false) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.className = "toast" + (ok ? " ok" : "");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 3000);
}

async function refresh() {
  const [clients, filaments, prints, settings] = await Promise.all([
    API.listClients(), API.listFilaments(), API.listPrints(), API.getSettings(),
  ]);
  state.clients = clients;
  state.filaments = filaments;
  state.prints = prints;
  state.settings = settings;
  renderAll();
}

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

function bindTabs() {
  document.getElementById("tabs").addEventListener("click", (e) => {
    const btn = e.target.closest(".tab");
    if (!btn) return;
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
  });
}

// ---------------------------------------------------------------------------
// Prints
// ---------------------------------------------------------------------------

function filteredPrints() {
  const f = state.filters;
  return state.prints.filter((p) => {
    if (f.client && String(p.client_id) !== f.client) return false;
    if (f.filament && String(p.filament_id) !== f.filament) return false;
    if (f.from && p.print_date < f.from) return false;
    if (f.to && p.print_date > f.to) return false;
    return true;
  });
}

function renderPrints() {
  const tbody = document.getElementById("prints-body");
  const rows = filteredPrints();

  if (rows.length === 0) {
    tbody.innerHTML = '<tr><td class="empty" colspan="8">No prints recorded yet.</td></tr>';
  } else {
    tbody.innerHTML = rows.map((p) => `
      <tr>
        <td>${esc(p.model_name)}</td>
        <td>${esc(p.client_name || "—")}</td>
        <td>${esc(p.filament_name || "—")}</td>
        <td>${Number(p.weight_used_g || 0).toFixed(1)}</td>
        <td>${fmtDuration(p.hours, p.minutes)}</td>
        <td>${esc(p.print_date)}</td>
        <td class="num">${money(p.total_cost)}</td>
        <td class="actions">
          <button class="btn btn-sm" data-action="edit-print" data-id="${p.id}">Edit</button>
          <button class="btn btn-sm btn-danger" data-action="del-print" data-id="${p.id}">Delete</button>
        </td>
      </tr>`).join("");
  }

  const total = rows.reduce((sum, p) => sum + Number(p.total_cost || 0), 0);
  const weight = rows.reduce((sum, p) => sum + Number(p.weight_used_g || 0), 0);
  document.getElementById("prints-summary").textContent =
    `${rows.length} print(s) · ${weight.toFixed(1)} g of filament · total ${money(total)}`;
}

function fillFilterSelects() {
  const clientSel = document.getElementById("filter-client");
  const filamentSel = document.getElementById("filter-filament");
  clientSel.innerHTML = '<option value="">All clients</option>' +
    state.clients.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("");
  filamentSel.innerHTML = '<option value="">All filaments</option>' +
    state.filaments.map((f) => `<option value="${f.id}">${esc(f.name)}</option>`).join("");
  clientSel.value = state.filters.client;
  filamentSel.value = state.filters.filament;
}

function bindPrintActions() {
  document.getElementById("btn-new-print").addEventListener("click", () => openPrintModal(null));

  document.getElementById("prints-body").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;
    const id = Number(btn.dataset.id);
    const print = state.prints.find((p) => p.id === id);
    if (btn.dataset.action === "edit-print") openPrintModal(print);
    if (btn.dataset.action === "del-print") deletePrint(print);
  });

  const f = document.getElementById("print-filters");
  f.addEventListener("change", (e) => {
    state.filters[e.target.id.replace("filter-", "")] = e.target.value;
    renderPrints();
  });
  document.getElementById("btn-clear-filters").addEventListener("click", () => {
    state.filters = { client: "", filament: "", from: "", to: "" };
    document.getElementById("filter-from").value = "";
    document.getElementById("filter-to").value = "";
    fillFilterSelects();
    renderPrints();
  });
}

function openPrintModal(print) {
  const isEdit = Boolean(print);
  const fields = `
    <label>Client / Project
      <select name="client_id" data-fk>
        <option value="">— none —</option>
        ${state.clients.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("")}
      </select>
    </label>
    <label>Model name *
      <input name="model_name" required placeholder="e.g. benchy" />
    </label>
    <label>Filament roll
      <select name="filament_id" data-fk>
        <option value="">— none —</option>
        ${state.filaments.map((f) => `<option value="${f.id}">${esc(f.name)}</option>`).join("")}
      </select>
    </label>
    <label>Filament weight used (g) *
      <input name="weight_used_g" type="number" step="0.1" min="0" required />
    </label>
    <div class="form-grid">
      <label>Hours
        <input name="hours" type="number" step="1" min="0" value="0" />
      </label>
      <label>Minutes
        <input name="minutes" type="number" step="1" min="0" max="59" value="0" />
      </label>
    </div>
    <label>Date of print *
      <input name="print_date" type="date" required />
    </label>
    <label>Notes
      <textarea name="notes" rows="2"></textarea>
    </label>
    <p class="hint" id="cost-preview">Cost preview will appear here.</p>
  `;

  openModal(isEdit ? "Edit Print" : "New Print", fields, async (formData) => {
    formData.model_name = formData.model_name.trim();
    formData.print_date = formData.print_date;
    if (isEdit) await API.updatePrint(print.id, formData);
    else await API.createPrint(formData);
    toast("Print saved.", true);
    await refresh();
  });

  const form = document.getElementById("modal-form");
  form.model_name.value = print?.model_name || "";
  form.client_id.value = print?.client_id ?? "";
  form.filament_id.value = print?.filament_id ?? "";
  form.weight_used_g.value = print?.weight_used_g ?? "";
  form.hours.value = print?.hours ?? 0;
  form.minutes.value = print?.minutes ?? 0;
  form.print_date.value = print?.print_date || new Date().toISOString().slice(0, 10);
  form.notes.value = print?.notes || "";

  form.addEventListener("input", async (e) => {
    if (e.target.name === "weight_used_g" ||
        e.target.name === "hours" ||
        e.target.name === "minutes" ||
        e.target.name === "filament_id") {
      const preview = document.getElementById("cost-preview");
      try {
        const costs = await API.previewCost({
          weight_used_g: form.weight_used_g.value,
          hours: form.hours.value,
          minutes: form.minutes.value,
          filament_id: form.filament_id.value,
        });
        preview.textContent =
          `Filament ${money(costs.filament_cost)} · Time ${money(costs.time_cost)} · ` +
          `Markup ${money(costs.markup)} · Total ${money(costs.total_cost)}`;
      } catch (_) { /* ignore preview errors while typing */ }
    }
  });
}

async function deletePrint(print) {
  if (!confirm(`Delete print "${print.model_name}"? This cannot be undone.`)) return;
  await API.deletePrint(print.id);
  toast("Print deleted.");
  await refresh();
}

// ---------------------------------------------------------------------------
// Clients
// ---------------------------------------------------------------------------

function renderClients() {
  const list = document.getElementById("clients-list");
  if (state.clients.length === 0) {
    list.innerHTML = '<p class="summary">No clients yet. Add your first client to get started.</p>';
    return;
  }
  list.innerHTML = state.clients.map((c) => `
    <div class="card">
      <h3>${esc(c.name)}</h3>
      <p>${esc(c.notes || "No notes.")}</p>
      <div class="actions">
        <button class="btn btn-sm" data-action="edit-client" data-id="${c.id}">Edit</button>
        <button class="btn btn-sm btn-danger" data-action="del-client" data-id="${c.id}">Delete</button>
      </div>
    </div>`).join("");
}

function bindClientActions() {
  document.getElementById("btn-new-client").addEventListener("click", () => openClientModal(null));

  document.getElementById("clients-list").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;
    const client = state.clients.find((c) => c.id === Number(btn.dataset.id));
    if (btn.dataset.action === "edit-client") openClientModal(client);
    if (btn.dataset.action === "del-client") deleteClient(client);
  });
}

function openClientModal(client) {
  const isEdit = Boolean(client);
  const fields = `
    <label>Name *
      <input name="name" required placeholder="e.g. Workshop, Company X" />
    </label>
    <label>Notes
      <textarea name="notes" rows="3" placeholder="Any details about this client/project"></textarea>
    </label>
  `;
  openModal(isEdit ? "Edit Client" : "New Client", fields, async (formData) => {
    formData.name = formData.name.trim();
    if (isEdit) await API.updateClient(client.id, formData);
    else await API.createClient(formData);
    toast("Client saved.", true);
    await refresh();
  });
  const form = document.getElementById("modal-form");
  form.name.value = client?.name || "";
  form.notes.value = client?.notes || "";
}

async function deleteClient(client) {
  const linked = state.prints.filter((p) => p.client_id === client.id).length;
  const msg = linked > 0
    ? `Delete "${client.name}"? ${linked} print(s) will keep existing but lose their client link.`
    : `Delete "${client.name}"?`;
  if (!confirm(msg)) return;
  await API.deleteClient(client.id);
  toast("Client deleted.");
  await refresh();
}

// ---------------------------------------------------------------------------
// Filaments
// ---------------------------------------------------------------------------

function renderFilaments() {
  const tbody = document.getElementById("filaments-body");
  if (state.filaments.length === 0) {
    tbody.innerHTML = '<tr><td class="empty" colspan="8">No filament profiles yet. Add your first spool.</td></tr>';
    return;
  }
  tbody.innerHTML = state.filaments.map((f) => {
    const kg = f.spool_weight_g ? (f.price / (f.spool_weight_g / 1000)) : 0;
    return `
      <tr>
        <td>${esc(f.name)}</td>
        <td>${esc(f.brand || "—")}</td>
        <td>${esc(f.material)}</td>
        <td><span class="swatch" style="background:${cssColor(f.color)}"></span>${esc(f.color || "—")}</td>
        <td>${Number(f.spool_weight_g).toFixed(0)}</td>
        <td>${money(f.price)}</td>
        <td class="num">${money(kg)}</td>
        <td class="actions">
          <button class="btn btn-sm" data-action="edit-filament" data-id="${f.id}">Edit</button>
          <button class="btn btn-sm btn-danger" data-action="del-filament" data-id="${f.id}">Delete</button>
        </td>
      </tr>`;
  }).join("");
}

function cssColor(color) {
  if (!color) return "transparent";
  return /^(#[0-9a-f]{3,8}|rgb)/i.test(color.trim()) ? color.trim() : "#e53935";
}

function bindFilamentActions() {
  document.getElementById("btn-new-filament").addEventListener("click", () => openFilamentModal(null));

  document.getElementById("filaments-body").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;
    const filament = state.filaments.find((f) => f.id === Number(btn.dataset.id));
    if (btn.dataset.action === "edit-filament") openFilamentModal(filament);
    if (btn.dataset.action === "del-filament") deleteFilament(filament);
  });
}

function openFilamentModal(filament) {
  const isEdit = Boolean(filament);
  const materials = ["PLA", "PETG", "ABS", "ASA", "TPU", "Nylon", "PC", "Other"];
  const fields = `
    <label>Name *
      <input name="name" required placeholder="e.g. Red PLA 1.75mm" />
    </label>
    <div class="form-grid">
      <label>Brand
        <input name="brand" placeholder="e.g. Sunlu" />
      </label>
      <label>Material
        <select name="material">
          ${materials.map((m) => `<option value="${m}">${m}</option>`).join("")}
        </select>
      </label>
    </div>
    <label>Color (name or hex, e.g. red or #ff0000)
      <input name="color" placeholder="red" />
    </label>
    <div class="form-grid">
      <label>Spool weight (g)
        <input name="spool_weight_g" type="number" step="1" min="1" value="1000" />
      </label>
      <label>Price paid
        <input name="price" type="number" step="0.01" min="0" placeholder="0.00" />
      </label>
    </div>
    <label>Notes
      <textarea name="notes" rows="2"></textarea>
    </label>
  `;
  openModal(isEdit ? "Edit Filament" : "New Filament", fields, async (formData) => {
    formData.name = formData.name.trim();
    if (isEdit) await API.updateFilament(filament.id, formData);
    else await API.createFilament(formData);
    toast("Filament saved.", true);
    await refresh();
  });
  const form = document.getElementById("modal-form");
  form.name.value = filament?.name || "";
  form.brand.value = filament?.brand || "";
  form.material.value = filament?.material || "PLA";
  form.color.value = filament?.color || "";
  form.spool_weight_g.value = filament?.spool_weight_g ?? 1000;
  form.price.value = filament?.price ?? "";
  form.notes.value = filament?.notes || "";
}

async function deleteFilament(filament) {
  const linked = state.prints.filter((p) => p.filament_id === filament.id).length;
  const msg = linked > 0
    ? `Delete "${filament.name}"? ${linked} print(s) will keep existing but lose their filament reference.`
    : `Delete "${filament.name}"?`;
  if (!confirm(msg)) return;
  await API.deleteFilament(filament.id);
  toast("Filament deleted.");
  await refresh();
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

function renderSettings() {
  const form = document.getElementById("settings-form");
  form.currency.value = state.settings.currency || "$";
  form.cost_per_hour.value = state.settings.cost_per_hour || 0;
  form.markup_percent.value = state.settings.markup_percent || 0;
}

function bindSettings() {
  document.getElementById("settings-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    await API.updateSettings({
      currency: form.currency.value.trim() || "$",
      cost_per_hour: form.cost_per_hour.value,
      markup_percent: form.markup_percent.value,
    });
    toast("Settings saved.", true);
    await refresh();
  });
}

// ---------------------------------------------------------------------------
// Backup
// ---------------------------------------------------------------------------

function download(url, filename) {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function bindBackup() {
  document.getElementById("btn-export-all").addEventListener("click", () =>
    download("/api/backup/export", ""));
  document.getElementById("btn-export-prints").addEventListener("click", () =>
    download("/api/backup/export/prints", ""));
  document.getElementById("btn-export-clients").addEventListener("click", () =>
    download("/api/backup/export/clients", ""));
  document.getElementById("btn-export-filaments").addEventListener("click", () =>
    download("/api/backup/export/filaments", ""));

  // ZIP upload -> full restore
  document.getElementById("file-zip").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (!confirm("Restoring a backup REPLACES all current data. Continue?")) {
      e.target.value = "";
      return;
    }
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/backup/import", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) { toast(data.error || "Import failed"); }
    else {
      const parts = Object.entries(data.imported).map(([k, v]) => `${k}: ${v}`);
      toast(`Restored. ${parts.join(" · ")}`, true);
      await refresh();
    }
    e.target.value = "";
  });

  // Single CSV uploads
  ["prints", "clients", "filaments"].forEach((table) => {
    document.getElementById("file-" + table).addEventListener("change", async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      if (!confirm(`Restoring ${table}.csv REPLACES all current ${table} data. Continue?`)) {
        e.target.value = "";
        return;
      }
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`/api/backup/import/${table}`, { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) { toast(data.error || "Import failed"); }
      else { toast(`Restored ${data.rows} ${table} row(s).`, true); await refresh(); }
      e.target.value = "";
    });
  });

  document.getElementById("backup-result");
}

// ---------------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------------

function openModal(title, fieldsHtml, onSubmit) {
  const overlay = document.getElementById("modal");
  document.getElementById("modal-title").textContent = title;
  document.getElementById("modal-fields").innerHTML = fieldsHtml;
  overlay.classList.remove("hidden");

  const form = document.getElementById("modal-form");
  const finish = (fn) => async (e) => {
    e.preventDefault();
    try {
      const fd = new FormData(form);
      const data = {};
      for (const [key, value] of fd.entries()) data[key] = value;
      await fn(data);
      closeModal();
    } catch (err) {
      toast(err.message);
    }
  };
  form.onsubmit = finish(onSubmit);
}

function closeModal() {
  document.getElementById("modal").classList.add("hidden");
}

function bindModal() {
  document.getElementById("modal-cancel").addEventListener("click", closeModal);
  document.getElementById("modal").addEventListener("click", (e) => {
    if (e.target.id === "modal") closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
  });
}

// ---------------------------------------------------------------------------
// Render all
// ---------------------------------------------------------------------------

function renderAll() {
  renderPrints();
  renderClients();
  renderFilaments();
  renderSettings();
  fillFilterSelects();
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

function runErrorHandler(fn) {
  return () => fn().catch((err) => toast(err.message));
}

document.addEventListener("DOMContentLoaded", () => {
  bindTabs();
  bindPrintActions();
  bindClientActions();
  bindFilamentActions();
  bindSettings();
  bindBackup();
  bindModal();
  runErrorHandler(refresh)();
});
