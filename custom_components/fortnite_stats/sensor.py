import logging
import asyncio
from datetime import timedelta

import aiohttp
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed, CoordinatorEntity

_LOGGER = logging.getLogger(__name__)

CONF_PLAYERS = "players"
# We zetten de interval op 15 minuten om veilig te blijven
SCAN_INTERVAL = timedelta(minutes=15)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_API_KEY): cv.string,
    vol.Required(CONF_PLAYERS): vol.All(cv.ensure_list, [cv.string]),
})

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up de Fortnite sensoren."""
    api_key = config[CONF_API_KEY]
    players = config[CONF_PLAYERS]
    session = async_get_clientsession(hass)

    entities = []

    for player in players:
        # Maak één coordinator per speler
        coordinator = FortniteDataUpdateCoordinator(hass, session, api_key, player)
        
        # Haal de eerste keer data op
        await coordinator.async_refresh()

        # Maak de sensoren aan en koppel ze aan deze coordinator
        for stat_key, label, icon in [
            ("wins", "Wins", "mdi:trophy"),
            ("kills", "Kills", "mdi:target"),
            ("deaths", "Deaths", "mdi:skull"),
            ("kd", "KD Ratio", "mdi:calculator"),
            ("matches", "Matches", "mdi:controller-classic"),
        ]:
            entities.append(FortniteSensor(coordinator, player, stat_key, label, icon))

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
                    stats = json_res['data']['stats']['all']['overall']
                    return {
                        "wins": stats.get("wins"),
                        "kills": stats.get("kills"),
                        "deaths": stats.get("deaths"),
                        "matches": stats.get("matches"),
                        "kd": stats.get("kd")
                    }
                elif response.status == 429:
                    raise UpdateFailed("Rate limit bereikt (429). Probeer later opnieuw.")
                else:
                    raise UpdateFailed(f"API Fout: {response.status}")
        except Exception as err:
            raise UpdateFailed(f"Verbindingsfout: {err}")

class FortniteSensor(CoordinatorEntity, SensorEntity):
    """Sensor die zijn data uit de Coordinator haalt."""

    def __init__(self, coordinator, player, key, label, icon):
        super().__init__(coordinator)
        self.key = key
        self._attr_name = f"Fortnite {player} {label}"
        self._attr_icon = icon
        self._attr_unique_id = f"fortnite_{player}_{key}".lower().replace(" ", "_")

    @property
    def state(self):
        """Haal de waarde direct uit de gedeelde data van de coordinator."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.key)