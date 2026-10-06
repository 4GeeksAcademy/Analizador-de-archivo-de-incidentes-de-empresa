"""Local Nexova API and backoffice entry point."""

import csv
import io
from pathlib import Path
from threading import Lock

from flask import Flask, Response, jsonify, redirect, request, send_from_directory
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from services.api.incidents import CATEGORIES, STATUSES, analyze_stream, render_csv


ROOT = Path(__file__).resolve().parents[2]


def create_app():
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
    latest = None
    lock = Lock()

    @app.after_request
    def disable_cache(response):
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(error):
        return jsonify(error="El archivo supera el limite de 5 MB."), 413

    @app.errorhandler(BadRequest)
    def bad_request(error):
        return jsonify(error="Solicitud multipart incorrecta."), 400

    @app.post("/api/incidents/analyze")
    def analyze():
        nonlocal latest
        if request.mimetype != "multipart/form-data":
            return jsonify(error="Envia el CSV como multipart/form-data en el campo file."), 415
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return jsonify(error="Falta el archivo CSV en el campo file."), 400
        if not upload.filename.lower().endswith(".csv"):
            return jsonify(error="El archivo debe tener extension .csv."), 415
        content = upload.read()
        if not content.strip():
            return jsonify(error="El archivo CSV esta vacio."), 400
        try:
            results = analyze_stream(io.StringIO(content.decode("utf-8-sig"), newline=""))
        except UnicodeError:
            return jsonify(error="El CSV debe estar codificado en UTF-8."), 422
        except csv.Error:
            return jsonify(error="Formato CSV incorrecto: revisa comas y comillas."), 422
        except ValueError as error:
            return jsonify(error=str(error)), 422

        scores = results["scores"]
        summary = {
            "total": results["total"],
            "valid": results["valid"],
            "invalid": results["invalid"],
            "invalid_reasons": dict(results["invalid_reasons"]),
            "categories": {key: results["categories"][key] for key in CATEGORIES},
            "statuses": {key: results["statuses"][key] for key in STATUSES},
            "satisfaction": {
                "closed": results["closed"],
                "scored": len(scores),
                "average": round(sum(scores) / len(scores), 2) if scores else None,
                "distribution": {str(score): results["score_counts"][score] for score in range(1, 6)},
            },
        }
        with lock:
            latest = render_csv(results)
        return jsonify(summary)

    @app.get("/api/incidents/results/export")
    def export():
        with lock:
            content = latest
        if content is None:
            return jsonify(error="Todavia no hay un analisis disponible para descargar."), 404
        return Response(
            content,
            content_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="results.csv"'},
        )

    @app.get("/")
    def home():
        return redirect("/uis/backoffice/")

    @app.get("/uis/backoffice/")
    def backoffice():
        return send_from_directory(ROOT / "uis" / "backoffice", "index.html")

    @app.get("/uis/backoffice/<path:filename>")
    def backoffice_asset(filename):
        return send_from_directory(ROOT / "uis" / "backoffice", filename)

    @app.get("/uis/<path:filename>")
    def existing_ui(filename):
        return send_from_directory(ROOT / "uis", filename)

    return app


app = create_app()