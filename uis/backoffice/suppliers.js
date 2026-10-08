const byId = (id) => document.getElementById(id);

const categoryLabels = {
  job_boards: "Job boards",
  ats_software: "ATS software",
  assessment_tools: "Assessment tools",
  training_platforms: "Training platforms",
  payroll_and_hr_software: "Nóminas y RR. HH.",
  video_interview: "Entrevistas por vídeo",
  background_check: "Background check",
  office_and_facilities: "Oficina e instalaciones",
  it_and_software_licenses: "Software y licencias IT",
};

let suppliers = [];
let busy = false;

function setMessage(text, error = false) {
  const message = byId("message");
  message.textContent = text;
  message.classList.toggle("error", error);
}

function setCreateMessage(text, error = false) {
  const message = byId("create-message");
  message.textContent = text;
  message.classList.toggle("error", error);
}

async function responseJson(response) {
  const result = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(result.detail)
      ? result.detail.map((item) => item.msg).join(" ")
      : result.detail || result.error;
    throw new Error(detail || "No se pudo completar la solicitud.");
  }
  return result;
}

function formatDate(dateText) {
  if (!dateText) return "Sin fecha";
  return new Intl.DateTimeFormat("es-ES", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${dateText}T00:00:00Z`));
}

function madridDateKey(date = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Madrid",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function renewalWindow() {
  const start = madridDateKey();
  const end = new Date(`${start}T00:00:00Z`);
  end.setUTCDate(end.getUTCDate() + 60);
  return [start, end.toISOString().slice(0, 10)];
}

function renewalIsSoon(dateText) {
  if (!dateText) return false;
  const [start, end] = renewalWindow();
  return dateText >= start && dateText <= end;
}

function formatTimestamp(value) {
  return new Intl.DateTimeFormat("es-ES", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Madrid",
  }).format(new Date(value));
}

function makeCell(text, className = "") {
  const cell = document.createElement("td");
  cell.textContent = text;
  if (className) cell.className = className;
  return cell;
}

function renderSupplier(supplier) {
  const row = document.createElement("tr");
  const name = document.createElement("th");
  name.scope = "row";
  name.className = "supplier-name";
  name.textContent = supplier.name;
  const details = document.createElement("span");
  details.className = "supplier-meta";
  details.textContent = supplier.contact_email || "Sin email de contacto";
  name.append(details);
  row.append(name);

  row.append(makeCell(supplier.country));
  const categories = makeCell(supplier.categories.map((category) => categoryLabels[category] || category).join(", "));
  categories.className = "category-cell";
  row.append(categories);

  const rateCell = document.createElement("td");
  rateCell.className = "rate-cell";
  const rateLine = document.createElement("div");
  rateLine.className = "rate-line";
  const rateValue = document.createElement("strong");
  rateValue.textContent = new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: supplier.currency,
    maximumFractionDigits: 2,
  }).format(supplier.monthly_rate);
  rateLine.append(rateValue);
  const rateInput = document.createElement("input");
  rateInput.type = "number";
  rateInput.min = "0.01";
  rateInput.step = "0.01";
  rateInput.value = supplier.monthly_rate;
  rateInput.setAttribute("aria-label", `Nueva tarifa mensual para ${supplier.name}`);
  const rateButton = document.createElement("button");
  rateButton.type = "button";
  rateButton.className = "icon-button";
  rateButton.title = `Guardar tarifa para ${supplier.name}`;
  rateButton.setAttribute("aria-label", `Guardar tarifa para ${supplier.name}`);
  rateButton.innerHTML = '<i data-lucide="save" aria-hidden="true"></i>';
  rateButton.addEventListener("click", () => updateRate(supplier, rateInput, rateButton));
  rateCell.append(rateLine, rateInput, rateButton);
  const updatedAt = document.createElement("span");
  updatedAt.className = "supplier-meta";
  updatedAt.textContent = `Actualizada ${formatTimestamp(supplier.updated_at)}`;
  rateCell.append(updatedAt);
  row.append(rateCell);

  const renewalCell = document.createElement("td");
  if (supplier.contract_renewal_date && renewalIsSoon(supplier.contract_renewal_date)) {
    const badge = document.createElement("span");
    badge.className = "renewal-badge";
    badge.textContent = "Próxima · ";
    renewalCell.append(badge);
  }
  renewalCell.append(document.createTextNode(formatDate(supplier.contract_renewal_date)));
  row.append(renewalCell);

  const statusCell = document.createElement("td");
  statusCell.className = "status-cell";
  const badge = document.createElement("span");
  badge.className = `status-badge ${supplier.status}`;
  badge.textContent = supplier.status === "active" ? "Activo" : "Suspendido";
  const statusButton = document.createElement("button");
  statusButton.type = "button";
  statusButton.className = "secondary status-action";
  const nextStatus = supplier.status === "active" ? "suspended" : "active";
  statusButton.textContent = supplier.status === "active" ? "Suspender" : "Activar";
  statusButton.setAttribute("aria-label", `${statusButton.textContent} ${supplier.name}`);
  statusButton.addEventListener("click", () => updateStatus(supplier, nextStatus, statusButton));
  statusCell.append(badge, statusButton);
  row.append(statusCell);

  return row;
}

function renderSuppliers() {
  const body = byId("supplier-rows");
  body.replaceChildren();
  for (const supplier of suppliers) body.append(renderSupplier(supplier));
  byId("supplier-count").textContent = `(${suppliers.length})`;
  if (window.lucide) window.lucide.createIcons();
}

async function loadSuppliers() {
  if (busy) return;
  busy = true;
  byId("refresh").disabled = true;
  byId("country-filter").disabled = true;
  byId("category-filter").disabled = true;
  setMessage("Cargando proveedores…");
  const params = new URLSearchParams();
  if (byId("country-filter").value) params.set("country", byId("country-filter").value);
  if (byId("category-filter").value) params.set("category", byId("category-filter").value);
  const query = params.size ? `?${params}` : "";
  try {
    suppliers = await responseJson(await fetch(`/api/suppliers${query}`, { headers: { Accept: "application/json" } }));
    renderSuppliers();
    setMessage(suppliers.length ? "Directorio actualizado." : "No hay proveedores para estos filtros.");
  } catch (error) {
    setMessage(error.message || "No se pudo cargar el directorio.", true);
  } finally {
    busy = false;
    byId("refresh").disabled = false;
    byId("country-filter").disabled = false;
    byId("category-filter").disabled = false;
  }
}

async function updateRate(supplier, input, button) {
  const monthlyRate = Number(input.value);
  if (!Number.isFinite(monthlyRate) || monthlyRate <= 0) {
    setMessage("La tarifa mensual debe ser mayor que cero.", true);
    input.focus();
    return;
  }
  button.disabled = true;
  try {
    const updated = await responseJson(await fetch(`/api/suppliers/${supplier.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ monthly_rate: monthlyRate }),
    }));
    suppliers = suppliers.map((item) => item.id === updated.id ? updated : item);
    renderSuppliers();
    setMessage(`Tarifa de ${updated.name} actualizada. Timestamp: ${formatTimestamp(updated.updated_at)}.`);
  } catch (error) {
    setMessage(error.message || "No se pudo actualizar la tarifa.", true);
    button.disabled = false;
  }
}

async function updateStatus(supplier, status, button) {
  button.disabled = true;
  try {
    const updated = await responseJson(await fetch(`/api/suppliers/${supplier.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ status }),
    }));
    suppliers = suppliers.map((item) => item.id === updated.id ? updated : item);
    renderSuppliers();
    setMessage(`${updated.name}: estado ${updated.status === "active" ? "activo" : "suspendido"}.`);
  } catch (error) {
    setMessage(error.message || "No se pudo cambiar el estado.", true);
    button.disabled = false;
  }
}

byId("country-filter").addEventListener("change", loadSuppliers);
byId("category-filter").addEventListener("change", loadSuppliers);
byId("refresh").addEventListener("click", loadSuppliers);

byId("country").addEventListener("change", (event) => {
  byId("currency").value = event.target.value === "Spain" ? "EUR" : event.target.value === "USA" ? "USD" : "";
});

byId("create-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const categories = [...document.querySelectorAll('input[name="categories"]:checked')].map((input) => input.value);
  if (!categories.length) {
    setCreateMessage("Selecciona al menos una categoría.", true);
    document.querySelector('input[name="categories"]').focus();
    return;
  }

  const form = event.currentTarget;
  const values = new FormData(form);
  const payload = {
    name: values.get("name").trim(),
    country: values.get("country"),
    categories,
    monthly_rate: Number(values.get("monthly_rate")),
    currency: values.get("currency"),
    status: values.get("status"),
  };
  const optionalFields = [
    ["contract_renewal_date", "contract_renewal_date"],
    ["contact_email", "contact_email"],
    ["notes", "notes"],
  ];
  for (const [field, key] of optionalFields) {
    const value = values.get(field).trim();
    if (value) payload[key] = value;
  }

  byId("create-button").disabled = true;
  form.setAttribute("aria-busy", "true");
  setCreateMessage("Guardando proveedor…");
  try {
    const created = await responseJson(await fetch("/api/suppliers", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    }));
    form.reset();
    byId("currency").value = "";
    setCreateMessage(`${created.name} quedó registrado.`);
    await loadSuppliers();
  } catch (error) {
    setCreateMessage(error.message || "No se pudo registrar el proveedor.", true);
  } finally {
    byId("create-button").disabled = false;
    form.removeAttribute("aria-busy");
  }
});

if (window.lucide) window.lucide.createIcons();
loadSuppliers();
