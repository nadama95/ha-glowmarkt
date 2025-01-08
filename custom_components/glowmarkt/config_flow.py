"""Config flow for Glowmarkt integration."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .api import GlowMarkt
from .const import CONFIG_ENTRY_VERSION, DOMAIN

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str}
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows connection to GLowmarkt.

    Data has the keys from DATA_SCHEMA with values provided by the user.
    """
    api = GlowMarkt(data[CONF_USERNAME], data[CONF_PASSWORD])
    try:
        await api.connect()
    except ValueError as err:
        raise InvalidAuth from err
    finally:
        await api.close()

    return {"title": "Glowmarkt Integration"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Glowmarkt."""

    VERSION = CONFIG_ENTRY_VERSION

    def __init__(self) -> None:
        """Set up initial data."""
        self.data: dict[str, Any] = {}
        self.token: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""

        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA)

        errors: dict[str, str] = {}
        info = {}

        try:
            info = await validate_input(self.hass, user_input)
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception:
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"

        if "base" not in errors:
            await self.async_set_unique_id(info.get("title"))
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
