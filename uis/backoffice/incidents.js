const byId = (id) => document.getElementById(id);
const reasons = {
  malformed_row: "Fila CSV mal formada",
  ticket_id_missing: "Falta ticket_id",
  ticket_id_invalid: "Formato de ticket_id inválido",
  ticket_id_duplicate: "ticket_id duplicado",
  date_missing: "Falta date",
  date_invalid: "Fecha inválida",
  client_company_missing: "Falta client_company",
  category_invalid: "Categoría ausente o inválida",
  description_invalid: "Descripción vacía o menor de 5 caracteres",
  agent_id_invalid: "agent_id ausente o inválido",
  status_invalid: "Estado ausente o inválido",
  email_invalid: "Email ausente o inválido",
  closed_score_missing: "Ticket CLOSED sin satisfacción",
  score_invalid: "Satisfacción no entera o fuera de 1–5",
};
const message = (text, error = false) => {
  byId("message").textContent = text;
  byId("message").classList.toggle("error", error);
};

function tableRows(id, entries, total) {
  const body = byId(id);
  body.replaceChildren();
  for (const [label, count] of entries) {
    const row = document.createElement("tr");
    const values = total === undefined ? [label, count] : [label, count, `${total ? (count / total * 100).toFixed(1) : "0.0"}%`];
    for (const value of values) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    }
    body.append(row);
  }
}

function showResults(result) {
  for (const key of ["total", "valid", "invalid"]) byId(key).textContent = result[key];
  byId("average").textContent = result.satisfaction.average === null ? "N/A" : `${result.satisfaction.average.toFixed(2)} / 5`;
  tableRows("categories", ["TECHNICAL", "BILLING", "ACCESS", "HR_QUERY", "COMPLAINT"].map((key) => [key, result.categories[key]]), result.valid);
  tableRows("statuses", ["OPEN", "CLOSED", "DISCARDED"].map((key) => [key, result.statuses[key]]), result.valid);
  tableRows("satisfaction", Object.entries(result.satisfaction.distribution), result.satisfaction.scored);
  byId("scored").textContent = `${result.satisfaction.scored} de ${result.satisfaction.closed} tickets cerrados puntuados`;
  tableRows("reasons", Object.entries(result.invalid_reasons).map(([key, count]) => [reasons[key] || key, count]));
  byId("invalid-table").hidden = result.invalid === 0;
  byId("quality").textContent = result.invalid ? `${result.invalid} registros excluidos. Una fila puede incumplir varias reglas.` : "Sin registros inválidos.";
  byId("results").hidden = false;
}

byId("file").addEventListener("change", () => {
  byId("download").disabled = true;
  byId("results").hidden = true;
  message("Sin análisis cargado.");
});

byId("upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = byId("file").files[0];
  if (!file) return;
  byId("download").disabled = true;
  byId("results").hidden = true;
  if (!file.name.toLowerCase().endsWith(".csv")) return message("Selecciona un archivo CSV.", true);
  if (!file.size) return message("El archivo está vacío.", true);
  if (file.size > 5 * 1024 * 1024) return message("El archivo supera el límite de 5 MB.", true);
  byId("analyze").disabled = true;
  byId("file").disabled = true;
  byId("upload-form").setAttribute("aria-busy", "true");
  message("Analizando incidencias…");
  const form = new FormData();
  form.append("file", file);
  try {
    const response = await fetch("/api/incidents/analyze", { method: "POST", body: form });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "No se pudo analizar el archivo.");
    showResults(result);
    byId("download").disabled = false;
    message(result.invalid ? `Análisis completado: ${result.invalid} registros inválidos.` : "Análisis completado.");
  } catch (error) {
    message(error.message || "No se pudo conectar con la API.", true);
  } finally {
    byId("analyze").disabled = false;
    byId("file").disabled = false;
    byId("upload-form").removeAttribute("aria-busy");
  }
});

byId("download").addEventListener("click", async () => {
  byId("download").disabled = true;
  try {
    const response = await fetch("/api/incidents/results/export");
    if (!response.ok) {
      const result = await response.json();
      throw new Error(result.error || "No se pudo descargar el CSV.");
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = "results.csv";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    message("Resultados descargados.");
  } catch (error) {
    message(error.message || "No se pudo descargar el CSV.", true);
  } finally {
    byId("download").disabled = false;
  }
});

if (window.lucide) window.lucide.createIcons();