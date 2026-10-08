from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4

from tinydb import Query, TinyDB

from services.api.supplier_models import Supplier, SupplierCreate, SupplierUpdate


class SupplierStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = TinyDB(self.db_path)
        self._table = self._db.table("suppliers")
        self._lock = RLock()

    def seed_if_empty(self, suppliers: list[dict]):
        with self._lock:
            if len(self._table) > 0:
                return 0
            for supplier in suppliers:
                self.create(SupplierCreate.model_validate(supplier))
            return len(suppliers)

    def list(self, country: str | None = None, category: str | None = None) -> list[Supplier]:
        with self._lock:
            suppliers = [Supplier.model_validate(record) for record in self._table.all()]
        return [
            supplier
            for supplier in suppliers
            if (country is None or supplier.country == country)
            and (category is None or category in supplier.categories)
        ]

    def get(self, supplier_id: UUID) -> Supplier | None:
        with self._lock:
            record = self._table.get(Query().id == str(supplier_id))
        return Supplier.model_validate(record) if record is not None else None

    def create(self, supplier: SupplierCreate) -> Supplier:
        record = Supplier(
            id=uuid4(),
            **supplier.model_dump(),
            updated_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._table.insert(record.model_dump(mode="json"))
        return record

    def update(self, supplier_id: UUID, update: SupplierUpdate) -> Supplier | None:
        with self._lock:
            record = self._table.get(Query().id == str(supplier_id))
            if record is None:
                return None

            supplier = Supplier.model_validate(record)
            changes = update.model_dump(exclude_unset=True)
            updated_at = datetime.now(timezone.utc) if "monthly_rate" in changes else supplier.updated_at
            updated = supplier.model_copy(update={**changes, "updated_at": updated_at})
            self._table.update(updated.model_dump(mode="json"), doc_ids=[record.doc_id])
            return updated

    def close(self):
        self._db.close()