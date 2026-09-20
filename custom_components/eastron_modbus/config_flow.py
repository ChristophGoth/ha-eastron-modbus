"""Config flow for the Eastron SDM Modbus integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_METERS,
    CONF_MODEL,
    CONF_SLAVE_ID,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    slave_identifier,
)
from .hub import EastronHub, EastronModbusError

_LOGGER = logging.getLogger(__name__)

GATEWAY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=5, max=600)
        ),
    }
)


def _meter_schema(default_slave: int) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_SLAVE_ID, default=default_slave): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=247)
            ),
            vol.Required(CONF_NAME): cv.string,
        }
    )


@callback
def _async_remove_meter_device(
    hass: HomeAssistant, entry: ConfigEntry, slave_id: int
) -> None:
    """Delete the device registry entry of one meter, and so its entities.

    Devices record their slave id as an identifier, so this works whether or
    not the entry is loaded. Devices created before that did not, and are
    matched through the serial their running coordinator reports; if there is
    no coordinator either, the device is left for the reload to reconcile.
    """
    registry = dr.async_get(hass)
    device = registry.async_get_device(identifiers={slave_identifier(slave_id)})

    if device is None:
        runtime = getattr(entry, "runtime_data", None)
        serial = next(
            (
                c.identity.serial
                for c in (runtime.coordinators if runtime else [])
                if c.slave_id == slave_id
            ),
            None,
        )
        if serial is None:
            return
        device = registry.async_get_device(identifiers={(DOMAIN, str(serial))})

    if device is not None:
        registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)


class EastronConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for the gateway, then add meters one at a time."""

    VERSION = 1

    def __init__(self) -> None:
        """Start with no gateway and no meters."""
        self._gateway: dict[str, Any] = {}
        self._meters: list[dict[str, Any]] = []
        self._hub: EastronHub | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the gateway address and verify it accepts a connection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            self._gateway = dict(user_input)
            self._hub = EastronHub(host, port, DEFAULT_TIMEOUT)
            return await self.async_step_meter()

        return self.async_show_form(
            step_id="user", data_schema=GATEWAY_SCHEMA, errors=errors
        )

    async def async_step_meter(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Probe one slave id, detect its model, and name it."""
        assert self._hub is not None
        errors: dict[str, str] = {}
        next_slave = self._meters[-1][CONF_SLAVE_ID] + 1 if self._meters else 1

        if user_input is not None:
            slave_id = user_input[CONF_SLAVE_ID]

            if any(meter[CONF_SLAVE_ID] == slave_id for meter in self._meters):
                errors[CONF_SLAVE_ID] = "duplicate_slave"
            else:
                try:
                    identity = await self._hub.async_read_identity(slave_id)
                except EastronModbusError as err:
                    _LOGGER.debug("Probe of slave %s failed: %s", slave_id, err)
                    errors["base"] = "no_meter"
                else:
                    if identity.model is None:
                        errors["base"] = "unknown_model"
                    else:
                        self._meters.append(
                            {
                                CONF_SLAVE_ID: slave_id,
                                CONF_NAME: user_input[CONF_NAME],
                                CONF_MODEL: identity.model,
                            }
                        )
                        return await self.async_step_add_another()

        return self.async_show_form(
            step_id="meter",
            data_schema=_meter_schema(next_slave),
            errors=errors,
            description_placeholders={"count": str(len(self._meters))},
        )

    async def async_step_add_another(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer to configure a further meter on the same gateway."""
        if user_input is not None:
            if user_input["add_another"]:
                return await self.async_step_meter()
            return await self._async_create()

        last = self._meters[-1]
        return self.async_show_form(
            step_id="add_another",
            data_schema=vol.Schema({vol.Required("add_another", default=True): cv.boolean}),
            description_placeholders={
                "name": last[CONF_NAME],
                "model": last[CONF_MODEL],
                "slave_id": str(last[CONF_SLAVE_ID]),
            },
        )

    async def _async_create(self) -> ConfigFlowResult:
        """Store the gateway and its meters as one entry."""
        if self._hub is not None:
            await self._hub.async_close()

        host = self._gateway[CONF_HOST]
        return self.async_create_entry(
            title=f"Eastron gateway ({host})",
            data={**self._gateway, CONF_METERS: self._meters},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Expose the poll interval and the meter list for later changes."""
        return EastronOptionsFlow()


class EastronOptionsFlow(OptionsFlow):
    """Retune the poll interval, or add and remove meters, after setup."""

    def __init__(self) -> None:
        """Start with no pending gateway connection."""
        self._hub: EastronHub | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer the things that can be changed after setup."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["interval", "add_meter", "remove_meter"],
        )

    async def async_step_interval(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and store the poll interval."""
        if user_input is not None:
            return self.async_create_entry(data={**self.config_entry.options, **user_input})

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        return self.async_show_form(
            step_id="interval",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        vol.Coerce(int), vol.Range(min=5, max=600)
                    )
                }
            ),
        )

    async def async_step_add_meter(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Probe one more slave id and append it to the entry."""
        errors: dict[str, str] = {}
        meters: list[dict[str, Any]] = list(self.config_entry.data[CONF_METERS])
        next_slave = max((m[CONF_SLAVE_ID] for m in meters), default=0) + 1

        if user_input is not None:
            slave_id = user_input[CONF_SLAVE_ID]

            if any(meter[CONF_SLAVE_ID] == slave_id for meter in meters):
                errors[CONF_SLAVE_ID] = "duplicate_slave"
            else:
                if self._hub is None:
                    self._hub = EastronHub(
                        self.config_entry.data[CONF_HOST],
                        self.config_entry.data[CONF_PORT],
                        DEFAULT_TIMEOUT,
                    )
                try:
                    identity = await self._hub.async_read_identity(slave_id)
                except EastronModbusError as err:
                    _LOGGER.debug("Probe of slave %s failed: %s", slave_id, err)
                    errors["base"] = "no_meter"
                else:
                    if identity.model is None:
                        errors["base"] = "unknown_model"
                    else:
                        meters.append(
                            {
                                CONF_SLAVE_ID: slave_id,
                                CONF_NAME: user_input[CONF_NAME],
                                CONF_MODEL: identity.model,
                            }
                        )
                        return await self._async_apply(meters)

        return self.async_show_form(
            step_id="add_meter",
            data_schema=_meter_schema(min(next_slave, 247)),
            errors=errors,
        )

    async def async_step_remove_meter(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Drop one or more meters from the entry, devices and all."""
        meters: list[dict[str, Any]] = list(self.config_entry.data[CONF_METERS])

        if len(meters) <= 1:
            # The entry exists to hold meters; emptying it would leave a
            # gateway with nothing to poll, so delete the entry instead.
            return self.async_abort(reason="last_meter")

        errors: dict[str, str] = {}

        if user_input is not None:
            removed = {int(value) for value in user_input[CONF_SLAVE_ID]}
            kept = [m for m in meters if m[CONF_SLAVE_ID] not in removed]
            if not kept:
                # Selecting every meter would leave the gateway polling
                # nothing, which is what deleting the entry is for.
                errors["base"] = "last_meter"
            else:
                for meter in meters:
                    if meter[CONF_SLAVE_ID] in removed:
                        _async_remove_meter_device(
                            self.hass, self.config_entry, meter[CONF_SLAVE_ID]
                        )
                return await self._async_apply(kept)

        options = {
            str(meter[CONF_SLAVE_ID]): (
                f"{meter[CONF_NAME]} ({meter[CONF_MODEL]}, slave {meter[CONF_SLAVE_ID]})"
            )
            for meter in meters
        }
        return self.async_show_form(
            step_id="remove_meter",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SLAVE_ID): cv.multi_select(options),
                }
            ),
            errors=errors,
        )

    async def _async_apply(self, meters: list[dict[str, Any]]) -> ConfigFlowResult:
        """Write the new meter list to the entry and reload it."""
        if self._hub is not None:
            await self._hub.async_close()
            self._hub = None

        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={**self.config_entry.data, CONF_METERS: meters},
        )
        # Finishing the options flow stores the options unchanged, which still
        # fires the update listener and reloads the entry with the new meter
        # list. One reload, triggered the same way a changed interval is.
        return self.async_create_entry(data=dict(self.config_entry.options))
