from pathlib import Path

from services.api.supplier_seed import SUPPLIERS_SEED
from services.api.supplier_store import SupplierStore


ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = ROOT / "data" / "runtime" / "suppliers.json"


def seed_suppliers(db_path: Path = DATABASE_PATH) -> tuple[int, int]:
    store = SupplierStore(db_path)
    try:
        inserted = store.seed_if_empty(SUPPLIERS_SEED)
        total = len(store.list())
        return inserted, total
    finally:
        store.close()


def main():
    inserted, total = seed_suppliers()
    if inserted:
        print(f"Se insertaron {inserted} proveedores. Total en la base: {total}.")
    else:
        print(f"No se insertaron proveedores: la base ya contiene {total}.")