"""Local Nexova API and backoffice entry point."""

import csv
import io
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from services.api.incidents import CATEGORIES, STATUSES, analyze_stream, render_csv
from services.api.supplier_seed import SUPPLIERS_SEED
from services.api.supplier_store import SupplierStore
from services.api.suppliers import router as suppliers_router


ROOT = Path(__file__).resolve().parents[2]
MAX_REQUEST_SIZE = 5 * 1024 * 1024


def create_app(supplier_db_path: Path | None = None):
    db_path = supplier_db_path or ROOT / "data" / "runtime" / "suppliers.json"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        supplier_store = SupplierStore(db_path)
        supplier_store.seed_if_empty(SUPPLIERS_SEED)
        app.state.supplier_store = supplier_store
        try:
            yield
        finally:
            supplier_store.close()

    app = FastAPI(lifespan=lifespan)
    latest = None
    lock = Lock()

    @app.middleware("http")
    async def apply_response_headers(request: Request, call_next):
        if request.headers.get("content-length", "").isdigit() and int(request.headers["content-length"]) > MAX_REQUEST_SIZE:
            response = JSONResponse({"error": "El archivo supera el limite de 5 MB."}, status_code=413)
        else:
            response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, error: StarletteHTTPException):
        if error.status_code == 400:
            message = "Solicitud multipart incorrecta."
        else:
            message = str(error.detail)
        return JSONResponse({"error": message}, status_code=error.status_code, headers=error.headers)

    @app.post("/api/incidents/analyze")
    async def analyze(request: Request):
        nonlocal latest
        if request.headers.get("content-type", "").split(";", 1)[0].strip() != "multipart/form-data":
            return JSONResponse({"error": "Envia el CSV como multipart/form-data en el campo file."}, status_code=415)
        form = await request.form()
        upload = form.get("file")
        if upload is None or not getattr(upload, "filename", None):
            return JSONResponse({"error": "Falta el archivo CSV en el campo file."}, status_code=400)
        if not upload.filename.lower().endswith(".csv"):
            return JSONResponse({"error": "El archivo debe tener extension .csv."}, status_code=415)
        content = await upload.read(MAX_REQUEST_SIZE + 1)
        if len(content) > MAX_REQUEST_SIZE:
            return JSONResponse({"error": "El archivo supera el limite de 5 MB."}, status_code=413)
        if not content.strip():
            return JSONResponse({"error": "El archivo CSV esta vacio."}, status_code=400)
        try:
            results = analyze_stream(io.StringIO(content.decode("utf-8-sig"), newline=""))
        except UnicodeError:
            return JSONResponse({"error": "El CSV debe estar codificado en UTF-8."}, status_code=422)
        except csv.Error:
            return JSONResponse({"error": "Formato CSV incorrecto: revisa comas y comillas."}, status_code=422)
        except ValueError as error:
            return JSONResponse({"error": str(error)}, status_code=422)

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
        return summary

    @app.get("/api/incidents/results/export")
    async def export():
        with lock:
            content = latest
        if content is None:
            return JSONResponse({"error": "Todavia no hay un analisis disponible para descargar."}, status_code=404)
        return Response(
            content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="results.csv"'},
        )

    @app.get("/")
    async def home():
        return RedirectResponse("/uis/backoffice/", status_code=302)

    app.include_router(suppliers_router)
    app.mount("/uis/backoffice", StaticFiles(directory=ROOT / "uis" / "backoffice", html=True), name="backoffice")
    app.mount("/uis", StaticFiles(directory=ROOT / "uis", html=True), name="uis")

    return app


app = create_app()