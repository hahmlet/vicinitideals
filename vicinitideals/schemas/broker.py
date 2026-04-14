"""Pydantic schemas for broker and brokerage records."""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class BrokerageBase(BaseModel):
    name: str
    crexi_name: str | None = None
    street: str | None = None
    street2: str | None = None
    city: str | None = None
    state_code: str | None = None
    zip_code: str | None = None


class BrokerageCreate(BrokerageBase):
    pass


class BrokerageRead(BrokerageBase):
    id: uuid.UUID

    model_config = {"from_attributes": True}


class BrokerBase(BaseModel):
    crexi_broker_id: int | None = None
    crexi_global_id: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    brokerage_name: str | None = None
    thumbnail_url: str | None = None
    is_platinum: bool = False
    number_of_assets: int | None = None
    brokerage_id: uuid.UUID | None = None
    email: str | None = None
    phone: str | None = None
    license_number: str | None = None
    license_state: str | None = None


class BrokerCreate(BrokerBase):
    pass


class BrokerRead(BrokerBase):
    id: uuid.UUID

    model_config = {"from_attributes": True}
