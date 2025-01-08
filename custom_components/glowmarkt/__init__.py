"""Glowmarkt Integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import GlowMarkt
from .const import DOMAIN, PLATFORMS


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Glowmarkt from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    api = GlowMarkt(username=entry.data["username"], password=entry.data["password"])

    hass.data[DOMAIN][entry.entry_id] = api

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
