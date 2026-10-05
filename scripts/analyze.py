"""Analyze support incident CSV files without exposing customer data."""

from __future__ import annotations

import argparse
import csv
import re
import sys
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
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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

    if not EMAIL_PATTERN.fullmatch(value("customer_email")):
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
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")
        missing_columns = [column for column in REQUIRED_COLUMNS if column not in reader.fieldnames]
        if missing_columns:
            raise ValueError("CSV is missing required columns: " + ", ".join(missing_columns))

        rows = list(reader)

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

        category_counts[row["category"]] += 1
        status = row["status"]
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


def print_report(file_path: Path, results: dict[str, object]) -> None:
    valid = int(results["valid"])
    categories = results["categories"]
    statuses = results["statuses"]
    invalid_reasons = results["invalid_reasons"]
    score_counts = results["score_counts"]
    scores = results["scores"]

    print("=" * 60)
    print("  NEXOVA — ANÁLISIS DE TICKETS DE SOPORTE")
    print(f"  Archivo: {file_path.name}")
    print("=" * 60)
    print(f"\nREGISTROS TOTALES .............. {results['total']}")
    print(f"  Válidos ...................... {results['valid']}")
    print(f"  Inválidos / incompletos ....... {results['invalid']}")

    print("\nDESGLOSE DE REGISTROS INVÁLIDOS")
    if invalid_reasons:
        for reason, count in sorted(invalid_reasons.items()):
            print(f"  {REASON_LABELS[reason]:34} {count}")
    else:
        print("  Sin registros inválidos")

    print("\nDESGLOSE POR CATEGORÍA (registros válidos)")
    for category in CATEGORIES:
        count = categories[category]
        print(f"  {category:12} {count:>4}  ({_percentage(count, valid)})")

    print("\nDESGLOSE POR ESTADO (registros válidos)")
    for status in STATUSES:
        count = statuses[status]
        print(f"  {status:12} {count:>4}  ({_percentage(count, valid)})")

    average = sum(scores) / len(scores) if scores else None
    average_text = f"{average:.2f} / 5.00" if average is not None else "N/A"
    print("\nÍNDICE DE SATISFACCIÓN (tickets cerrados válidos)")
    print(f"  Tickets puntuados: {len(scores)} de {results['closed']}")
    print(f"  Puntuación media: {average_text}")
    for score, label in (
        (1, "Muy insatisfecho"),
        (2, "Insatisfecho"),
        (3, "Neutral"),
        (4, "Satisfecho"),
        (5, "Muy satisfecho"),
    ):
        print(f"  Puntuación {score} ({label:18}) {score_counts[score]}")
    print("\n" + "=" * 60)


def export_results(file_path: Path, results: dict[str, object], output_path: Path) -> None:
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

    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(("metric", "value"))
        writer.writerows(metrics)

    print(f"Resultados exportados a {output_path} (origen: {file_path.name}).")


def ask_export() -> bool:
    while True:
        try:
            answer = input("¿Deseas exportar los resultados a CSV? (Y / N): ").strip().lower()
        except EOFError:
            return False
        if answer in {"y", "s", "si", "sí"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Respuesta no válida. Escribe Y/S o N.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analiza un CSV de tickets de soporte Nexova.")
    parser.add_argument("csv_file", type=Path, help="Ruta al archivo CSV de incidentes")
    args = parser.parse_args(argv)

    try:
        results = analyze_csv(args.csv_file)
    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        print(f"Error al procesar el CSV: {error}", file=sys.stderr)
        return 2

    print_report(args.csv_file, results)
    if ask_export():
        try:
            export_results(args.csv_file, results, Path("results.csv"))
        except OSError as error:
            print(f"Error al exportar los resultados: {error}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())