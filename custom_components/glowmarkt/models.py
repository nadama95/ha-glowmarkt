"""Type hint models."""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ResourceType = Literal[
    "gas consumption", "gas cost", "electricity consumption", "electricity cost"
]


@dataclass
class ReadingData:
    """Reading Data."""

    datestamp: datetime
    value: float

@dataclass
class Reading:
    """Reading."""

    data: list[ReadingData]

@dataclass
class ResourceTypeInfo:
    """Resource Type Info."""

    unit: str
    type: Literal["GAS", "ELEC"]


@dataclass
class ResourceOverview:
    """Virtual Entity Resource Overview."""

    resource_id: str
    resource_type_id: str
    name: str

@dataclass
class Resource:
    """Virtual Entity Resource."""

    active: bool
    resource_type_id: str
    owner_id: str
    name: str
    description: str
    label: str
    data_source_resource_type_info: ResourceTypeInfo
    data_source_type: str
    classifier: str
    base_unit: str
    resource_id: str
    updated_at: str
    created_at: str
    data_souce_unit_info: dict[str, str]

@dataclass
class TariffRates:
    """Tariff Rates."""

    rate: float
    standing_charge: float

@dataclass
class TariffData:
    """Tariff data."""

    current_rates: TariffRates

@dataclass
class VirtualEntity:
    """Virtual Entity."""

    resources: list[ResourceOverview]
    name: str
    id: str
