from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


Country = Literal["Spain", "USA"]
Currency = Literal["EUR", "USD"]
Category = Literal[
    "job_boards",
    "ats_software",
    "assessment_tools",
    "training_platforms",
    "payroll_and_hr_software",
    "video_interview",
    "background_check",
    "office_and_facilities",
    "it_and_software_licenses",
]
SupplierStatus = Literal["active", "suspended"]


class SupplierCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    country: Country
    categories: list[Category] = Field(min_length=1)
    monthly_rate: float = Field(gt=0)
    currency: Currency
    status: SupplierStatus
    contract_renewal_date: date | None = None
    contact_email: EmailStr | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def currency_matches_country(self):
        expected_currency = "EUR" if self.country == "Spain" else "USD"
        if self.currency != expected_currency:
            raise ValueError(f"{self.country} requiere la moneda {expected_currency}.")
        return self


class SupplierUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monthly_rate: float | None = Field(default=None, gt=0)
    status: SupplierStatus | None = None

    @model_validator(mode="after")
    def require_an_update(self):
        if not self.model_fields_set:
            raise ValueError("Indica monthly_rate o status para actualizar el proveedor.")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Los campos enviados no pueden ser null.")
        return self


class Supplier(BaseModel):
    id: UUID
    name: str
    country: Country
    categories: list[Category]
    monthly_rate: float
    currency: Currency
    updated_at: datetime
    status: SupplierStatus
    contract_renewal_date: date | None = None
    contact_email: EmailStr | None = None
    notes: str | None = None