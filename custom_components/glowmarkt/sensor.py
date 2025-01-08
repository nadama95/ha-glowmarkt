"""Platform for sensor integration."""

import logging
from datetime import datetime, time, timedelta
from functools import cached_property
from typing import Literal

from homeassistant.components.sensor import (
    SensorDeviceClass,  # pyright: ignore [reportPrivateImportUsage]
    SensorEntity,
    SensorStateClass,  # pyright: ignore [reportPrivateImportUsage]
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .api import GlowMarkt
from .const import DOMAIN
from .models import Resource, TariffRates, VirtualEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> bool:
    """Set up Glowmarkt entity based on config entry."""

    entities: list[SensorEntity] = []
    meters: dict[str,str] = {}

    api: GlowMarkt = hass.data[DOMAIN][entry.entry_id]
    await api.connect()

    virtual_entities = await api.get_virtual_entites()
    _LOGGER.debug("Successfully loaded virtual entities: %s", virtual_entities)

    for virtual_entity in virtual_entities:
        resources = await api.get_resources(virtual_entity.id)
        _LOGGER.debug("Successfully loaded resources %s", resources)

        for resource in resources:
            if resource.classifier in (
                "electricity.consumption",
                "gas.consumption",
            ):
                usage_sensor = UsageSensor(hass, resource, virtual_entity, api)
                entities.append(usage_sensor)

                # Save the usage sensor as a meter so that the cost sensor can reference it
                meters[resource.classifier] = resource.resource_id

                # Standing and Rate sensors are handled by the coordinator
                coordinator = TariffCoordinator(hass, api, resource)
                standing_sensor = Standing(coordinator, resource, virtual_entity)
                entities.append(standing_sensor)
                rate_sensor = Rate(coordinator, resource, virtual_entity)
                entities.append(rate_sensor)

        # Cost sensors must be created after usage sensors as they reference them as a meter
        for resource in resources:
            if resource.classifier == "gas.consumption.cost":
                cost_sensor = Cost(
                    api, resource, virtual_entity, meters["gas.consumption"]
                )
                entities.append(cost_sensor)
            elif resource.classifier == "electricity.consumption.cost":
                cost_sensor = Cost(
                    api, resource, virtual_entity, meters["electricity.consumption"]
                )
                entities.append(cost_sensor)

    async_add_entities(entities, update_before_add=True)
    return True


class UsageSensor(SensorEntity):
    """Glowmarkt Consumption Sensor."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_has_entity_name = True
    _attr_last_reset = None
    _attr_name_ = "Usage (today)"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(
        self,
        hass: HomeAssistant,
        resource: Resource,
        virtual_entity: VirtualEntity,
        api: GlowMarkt,
    ) -> None:
        """Initialise Sensor."""
        self._attr_unique_id = resource.resource_id

        self.api = api
        self.hass = hass
        self.initalised = False
        self.resource = resource
        self.virtual_entity = virtual_entity

    @cached_property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.resource.resource_id)},
            manufacturer="Hildebrand",
            model="Glow (DCC)",
            name=device_name(self.resource, self.virtual_entity),
        )

    @cached_property
    def icon(self) -> str | None:
        """Icon to use in frontend."""
        match self.resource.classifier:
            case "gas.consumption":
                return "mdi.fire"
            case _:
                return None

    async def async_update(self) -> None:
        """Update all Node data from Glowmarkt."""

        if not self.initalised:
            value, t_from = await daily_data(self.api, self.resource)
            if value:
                self._attr_native_value = round(value, 2)
                self._attr_last_reset = t_from
                self.initalised = True

        elif await should_update():
            value, t_from = await daily_data(self.api, self.resource)
            if value:
                self._attr_native_value = round(value, 2)
                self._attr_last_reset = t_from


class Cost(SensorEntity):
    """Sensor usage for daily cost."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_has_entity_name = True
    _attr_name = "Cost (today)"
    _attr_native_unit_of_measurement = "GBP"
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(
        self,
        api: GlowMarkt,
        resource: Resource,
        virtual_entity: VirtualEntity,
        meter_id: str,
    ) -> None:
        """Initialize the sensor."""
        self._attr_unique_id = resource.resource_id

        self.api = api
        self.initialised = False
        self.meter_id = meter_id
        self.resource = resource
        self.virtual_entity = virtual_entity

    @cached_property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            # Get the identifier from the meter so that the cost sensors have the same device
            identifiers={(DOMAIN, self.meter_id)},
            manufacturer="Hildebrand",
            model="Glow (DCC)",
            name=device_name(self.resource, self.virtual_entity),
        )

    async def async_update(self) -> None:
        """Fetch new data for the sensor."""
        if not self.initialised:
            value, _ = await daily_data(self.api, self.resource)
            if value:
                self._attr_native_value = round(value / 100, 2)
                self.initialised = True
        elif await should_update():
            value, _ = await daily_data(self.api, self.resource)
            if value:
                self._attr_native_value = round(value / 100, 2)


class TariffCoordinator(DataUpdateCoordinator):
    """Data update coordinator for the tariff sensors."""

    def __init__(self, hass: HomeAssistant, api: GlowMarkt, resource: Resource) -> None:
        """Initalise the tariff coordinator."""
        super().__init__(
            hass, _LOGGER, name="tariff", update_interval=timedelta(minutes=5)
        )

        self.api = api
        self.rate_initalised = False
        self.standing_initalised = False
        self.resource = resource

    async def _async_update_data(self) -> dict[str, float]:
        if not self.standing_initalised or not self.rate_initalised:
            tariff = await tariff_data(self.api, self.resource)

            self.rate_initalised = True
            self.standing_initalised = True

            return {"rate": tariff.rate, "standing_charge": tariff.standing_charge}

        if await should_update():
            tariff = await tariff_data(self.api, self.resource)
            return {"rate": tariff.rate, "standing_charge": tariff.standing_charge}

        return {}


class Rate(CoordinatorEntity, SensorEntity):  # pyright: ignore [reportIncompatibleVariableOverride]
    """An entity using CoordinatorEntity.

    The CoordinatorEntity class provides:
      should_poll
      async_update
      async_added_to_hass
      available

    """

    _attr_device_class = None
    _attr_has_entity_name = True
    _attr_icon = "mdi:cash-multiple"
    _attr_name = "Rate"
    _attr_native_unit_of_measurement = "GBP/kWh"
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: TariffCoordinator,
        resource: Resource,
        virtual_entity: VirtualEntity,
    ) -> None:
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)

        self._attr_unique_id = resource.resource_id + "-rate"

        self.resource = resource
        self.virtual_entity = virtual_entity

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            value = float(self.coordinator.data["rate"] / 100)
            self._attr_native_value = round(value, 4)
            self.async_write_ha_state()

    @cached_property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.resource.resource_id)},
            name=device_name(self.resource, self.virtual_entity),
            manufacturer="Hildebrand",
            model="Glow (DCC)",
        )


class Standing(CoordinatorEntity, SensorEntity):  # pyright: ignore [reportIncompatibleVariableOverride]
    """An entity using CoordinatorEntity.

    The CoordinatorEntity class provides:
      should_poll
      async_update
      async_added_to_hass
      available

    """

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_has_entity_name = True
    _attr_name = "Standing charge"
    _attr_native_unit_of_measurement = "GBP"
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: TariffCoordinator,
        resource: Resource,
        virtual_entity: VirtualEntity,
    ) -> None:
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)

        self._attr_unique_id = resource.resource_id + "-tariff"

        self.resource = resource
        self.virtual_entity = virtual_entity

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            value = float(self.coordinator.data["standing_charge"] / 100)
            self._attr_native_value = round(value, 4)
            self.async_write_ha_state()

    @cached_property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.resource.resource_id)},
            name=device_name(self.resource, self.virtual_entity),
            manufacturer="Hildebrand",
            model="Glow (DCC)",
        )


async def daily_data(api: GlowMarkt, resource: Resource) -> tuple[float, datetime]:
    """Get daily data from Glowmarkt API."""
    if datetime.now().time() <= time(1, 5):
        _LOGGER.debug("Fetching yesterday's data")
        now = datetime.now() - timedelta(days=1)
    else:
        now = datetime.now()

    t_from = now.replace(hour=0, minute=0, second=0, microsecond=0)
    t_to = now.replace(second=0, microsecond=0)

    # Pull latest data
    await api.catchup(resource.resource_id)

    reading = await api.get_reading(resource.resource_id, t_from, t_to, "P1D")

    v = reading.data[0].value

    if len(reading.data) > 1:
        v += reading.data[1].value

    return (v, t_from)


async def tariff_data(api: GlowMarkt, resource: Resource) -> TariffRates:
    """Get Tariff data from the API."""
    tariff = await api.get_tariff(resource.resource_id)
    _LOGGER.debug("Successfully loaded tariff %s", tariff)

    return tariff.current_rates


def device_name(resource: Resource, virtual_entity: VirtualEntity) -> str:
    """Return device name, including name of virtual entitiy."""

    supply = supply_type(resource)

    return f"{virtual_entity.name} smart {supply} meter"


async def should_update() -> bool:
    """Check if time is between 1-5 or 31-35 minutes past the hour."""
    minutes = datetime.now().minute
    if (1 <= minutes <= 5) or (31 <= minutes <= 35):
        return True
    return False


def supply_type(resource: Resource) -> Literal["electricity", "gas"]:
    """Return the type of supply."""
    if "electricity.consumption" in resource.classifier:
        return "electricity"
    if "gas.consumption" in resource.classifier:
        return "gas"

    _LOGGER.error("Unexpected classifier in supply_type: %s", resource.classifier)
    raise ValueError("Unexpected classifer", resource.classifier)
