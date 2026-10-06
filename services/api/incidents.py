"""Shared Nexova validation, analysis and aggregate CSV export."""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from datetime import date
from pathlib import Path


CATEGORIES = ("TECHNICAL", "BILLING", "ACCESS", "HR_QUERY", "COMPLAINT")

STATUSES = ("OPEN", "CLOSED", "DISCARDED")

REQUIRED_COLUMNS = (
    "ticket_id",
    "date",
    "client_company",
    "category",
    "description",
    "agent_id",
    "status",
    "customer_email",
)

REASON_LABELS = {
    "malformed_row": "Malformed CSV row",
    "ticket_id_missing": "Missing ticket_id",
    "ticket_id_invalid": "Invalid ticket_id",
    "ticket_id_duplicate": "Duplicate ticket_id",
    "date_missing": "Missing date",
    "date_invalid": "Invalid date",
    "client_company_missing": "Missing client_company",
    "category_invalid": "Invalid or missing category",
    "description_invalid": "Empty or too-short description",
    "agent_id_invalid": "Invalid or missing agent_id",
    "status_invalid": "Invalid or missing status",
    "email_invalid": "Invalid or missing email",
    "closed_score_missing": "Closed ticket, no score",
    "score_invalid": "Invalid satisfaction score",
}

TICKET_ID_PATTERN = re.compile(r"^NXV-\d{6}$")

AGENT_ID_PATTERN = re.compile(r"^AGT-\d{2}$")


def _validate_row(row: dict[str, str | list[str] | None], duplicate_ids: set[str]) -> list[str]:
    issues: list[str] = []
    if None in row:
        issues.append("malformed_row")

    def value(field: str) -> str:
        raw_value = row.get(field)
        return raw_value.strip() if isinstance(raw_value, str) else ""

    ticket_id = value("ticket_id")
    if not ticket_id:
        issues.append("ticket_id_missing")
    elif not TICKET_ID_PATTERN.fullmatch(ticket_id):
        issues.append("ticket_id_invalid")
    elif ticket_id in duplicate_ids:
        issues.append("ticket_id_duplicate")

    date_value = value("date")
    if not date_value:
        issues.append("date_missing")
    else:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value):
                raise ValueError
            date.fromisoformat(date_value)
        except ValueError:
            issues.append("date_invalid")

    if not value("client_company"):
        issues.append("client_company_missing")

    if value("category") not in CATEGORIES:
        issues.append("category_invalid")

    if len(value("description")) < 5:
        issues.append("description_invalid")

    if not AGENT_ID_PATTERN.fullmatch(value("agent_id")):
        issues.append("agent_id_invalid")

    status = value("status")
    if status not in STATUSES:
        issues.append("status_invalid")

    if "@" not in value("customer_email"):
        issues.append("email_invalid")

    score_value = value("satisfaction_score")
    if status == "CLOSED" and not score_value:
        issues.append("closed_score_missing")
    elif score_value:
        try:
            score = int(score_value)
            if not 1 <= score <= 5:
                raise ValueError
        except ValueError:
            issues.append("score_invalid")

    return issues

def analyze_csv(file_path: Path) -> dict[str, object]:
    with file_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return analyze_stream(csv_file)

def analyze_stream(csv_file) -> dict[str, object]:
    reader = csv.DictReader(csv_file, strict=True)
    if reader.fieldnames is None:
        raise ValueError("El CSV esta vacio o no tiene cabecera.")
    if len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError("La cabecera del CSV contiene columnas duplicadas.")
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in reader.fieldnames]
    if missing_columns:
        raise ValueError("Faltan columnas requeridas: " + ", ".join(missing_columns))
    rows = list(reader)
    if not rows:
        raise ValueError("El CSV no contiene registros.")

    id_counts = Counter(
        row.get("ticket_id", "").strip()
        for row in rows
        if isinstance(row.get("ticket_id"), str) and row.get("ticket_id", "").strip()
    )
    duplicate_ids = {ticket_id for ticket_id, count in id_counts.items() if count > 1}

    invalid_count = 0
    invalid_reasons: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    score_counts: Counter[int] = Counter()
    closed_count = 0
    scores: list[int] = []

    for row in rows:
        issues = _validate_row(row, duplicate_ids)
        if issues:
            invalid_count += 1
            invalid_reasons.update(issues)
            continue

        category_counts[row["category"].strip()] += 1
        status = row["status"].strip()
        status_counts[status] += 1
        if status == "CLOSED":
            closed_count += 1
            score = int(row["satisfaction_score"])
            scores.append(score)
            score_counts[score] += 1

    return {
        "total": len(rows),
        "valid": len(rows) - invalid_count,
        "invalid": invalid_count,
        "invalid_reasons": invalid_reasons,
        "categories": category_counts,
        "statuses": status_counts,
        "closed": closed_count,
        "scores": scores,
        "score_counts": score_counts,
    }

def _percentage(count: int, total: int) -> str:
    return f"{count / total * 100:.1f}%" if total else "0.0%"

def render_csv(results: dict[str, object]) -> str:
    metrics: list[tuple[str, object]] = [
        ("total_records", results["total"]),
        ("valid_records", results["valid"]),
        ("invalid_records", results["invalid"]),
    ]
    invalid_reasons = results["invalid_reasons"]
    for reason in REASON_LABELS:
        metrics.append((f"invalid_{reason}", invalid_reasons[reason]))

    categories = results["categories"]
    statuses = results["statuses"]
    valid = int(results["valid"])
    for category in CATEGORIES:
        metrics.append((f"category_{category.lower()}_count", categories[category]))
        metrics.append((f"category_{category.lower()}_percent", _percentage(categories[category], valid)))
    for status in STATUSES:
        metrics.append((f"status_{status.lower()}_count", statuses[status]))
        metrics.append((f"status_{status.lower()}_percent", _percentage(statuses[status], valid)))

    scores = results["scores"]
    average = sum(scores) / len(scores) if scores else ""
    metrics.extend(
        [
            ("closed_tickets", results["closed"]),
            ("scored_closed_tickets", len(scores)),
            ("average_satisfaction", f"{average:.2f}" if average != "" else "N/A"),
        ]
    )
    score_counts = results["score_counts"]
    for score in range(1, 6):
        metrics.append((f"satisfaction_score_{score}_count", score_counts[score]))

    csv_file = io.StringIO(newline="")
    writer = csv.writer(csv_file)
    writer.writerow(("metric", "value"))
    writer.writerows(metrics)
    return csv_file.getvalue()
