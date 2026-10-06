"""Analyze support incident CSV files without exposing customer data."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.api.incidents import (
    CATEGORIES, STATUSES, REASON_LABELS, analyze_csv, _percentage, render_csv,
)


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
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        csv_file.write(render_csv(results))

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