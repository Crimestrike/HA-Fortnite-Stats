import logging
import asyncio
from datetime import timedelta

import aiohttp
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA, 
    SensorEntity, 
    SensorStateClass
)
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed, CoordinatorEntity

_LOGGER = logging.getLogger(__name__)

CONF_PLAYERS = "players"
SCAN_INTERVAL = timedelta(minutes=15)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_API_KEY): cv.string,
    vol.Required(CONF_PLAYERS): vol.All(cv.ensure_list, [cv.string]),
})

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up de Fortnite sensoren vanuit YAML."""
    api_key = config[CONF_API_KEY]
    players = config[CONF_PLAYERS]
    session = async_get_clientsession(hass)

    entities = []

    for player in players:
        coordinator = FortniteDataUpdateCoordinator(hass, session, api_key, player)
        
        # Haal direct de eerste keer data op
        await coordinator.async_refresh()

        # Hier voegen we de 'unit' toe aan de lijst, die is nodig voor de grafiek
        stats_to_track = [
            ("wins", "Wins", "mdi:trophy", "wins"),
            ("kills", "Kills", "mdi:target", "kills"),
            ("deaths", "Deaths", "mdi:skull", "deaths"),
            ("kd", "KD Ratio", "mdi:calculator", "KD"),
            ("matches", "Matches", "mdi:controller-classic", "matches"),
        ]

        for stat_key, label, icon, unit in stats_to_track:
            entities.append(FortniteSensor(coordinator, player, stat_key, label, icon, unit))

    async_add_entities(entities)

class FortniteDataUpdateCoordinator(DataUpdateCoordinator):
    """Beheert het ophalen van data voor één specifieke speler."""

    def __init__(self, hass, session, api_key, player_name):
        super().__init__(
            hass,
            _LOGGER,
            name=f"Fortnite stats voor {player_name}",
            update_interval=SCAN_INTERVAL,
        )
        self.session = session
        self.api_key = api_key
        self.player_name = player_name

    async def _async_update_data(self):
        """Haal de data op als één pakket."""
        url = f"https://fortnite-api.com/v2/stats/br/v2?name={self.player_name}"
        headers = {"Authorization": self.api_key}

        try:
            async with self.session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    json_res = await response.json()
                    if "data" in json_res and "stats" in json_res["data"]:
                        stats = json_res['data']['stats']['all']['overall']
                        return {
                            "wins": stats.get("wins"),
                            "kills": stats.get("kills"),
                            "deaths": stats.get("deaths"),
                            "matches": stats.get("matches"),
                            "kd": stats.get("kd")
                        }
                    else:
                        raise UpdateFailed("Ongeldige response van API")
                elif response.status == 429:
                    raise UpdateFailed("Rate limit (429)")
                else:
                    raise UpdateFailed(f"API fout: {response.status}")
        except Exception as err:
            raise UpdateFailed(f"Verbindingsfout: {err}")

class FortniteSensor(CoordinatorEntity, SensorEntity):
    """Sensor die data uit de Coordinator haalt en geschikt is voor grafieken."""

    def __init__(self, coordinator, player, key, label, icon, unit):
        super().__init__(coordinator)
        self.key = key
        self._attr_name = f"Fortnite {player} {label}"
        self._attr_icon = icon
        self._attr_unique_id = f"fortnite_{player}_{key}".lower().replace(" ", "_")
        
        # DEZE REGELS ZIJN NIEUW EN NODIG VOOR JE GRAFIEK:
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self):
        """Geef de waarde door aan Home Assistant."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.key)