from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from services.api.supplier_store import SupplierStore
from services.api.supplier_models import Category, Country, Supplier, SupplierCreate, SupplierStatus, SupplierUpdate


router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


def get_supplier_store(request: Request) -> SupplierStore:
    return request.app.state.supplier_store


@router.get("", response_model=list[Supplier])
def list_suppliers(
    store: SupplierStore = Depends(get_supplier_store),
    country: Country | None = None,
    category: Category | None = None,
):
    return store.list(country=country, category=category)


@router.post("", response_model=Supplier, status_code=status.HTTP_201_CREATED)
def create_supplier(
    supplier: SupplierCreate,
    store: SupplierStore = Depends(get_supplier_store),
):
    return store.create(supplier)


@router.get("/{supplier_id}", response_model=Supplier)
def get_supplier(
    supplier_id: UUID,
    store: SupplierStore = Depends(get_supplier_store),
):
    supplier = store.get(supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado.")
    return supplier


@router.patch("/{supplier_id}", response_model=Supplier)
def update_supplier(
    supplier_id: UUID,
    update: SupplierUpdate,
    store: SupplierStore = Depends(get_supplier_store),
):
    supplier = store.update(supplier_id, update)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado.")
    return supplier