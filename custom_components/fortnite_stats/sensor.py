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
# De coordinator draait elke 15 minuten en verwerkt dan ÉÉN speler
SCAN_INTERVAL = timedelta(minutes=15)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_API_KEY): cv.string,
    vol.Required(CONF_PLAYERS): vol.All(cv.ensure_list, [cv.string]),
})

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up de Fortnite sensoren met een gedeelde, sequentiële coordinator."""
    api_key = config.get(CONF_API_KEY)
    players = config.get(CONF_PLAYERS)
    session = async_get_clientsession(hass)

    # We maken één coordinator voor ALLE spelers
    coordinator = FortniteGlobalCoordinator(hass, session, api_key, players)
    
    # Haal bij de start slechts 1 speler op (de eerste in de lijst)
    await coordinator.async_refresh()

    entities = []
    for player in players:
        stats_map = [
            ("wins", "Wins", "mdi:trophy", "wins"),
            ("kills", "Kills", "mdi:target", "kills"),
            ("deaths", "Deaths", "mdi:skull", "deaths"),
            ("kd", "KD Ratio", "mdi:calculator", "KD"),
            ("matches", "Matches", "mdi:controller-classic", "matches"),
        ]

        for key, label, icon, unit in stats_map:
            entities.append(FortniteSensor(coordinator, player, key, label, icon, unit))

    async_add_entities(entities)

class FortniteGlobalCoordinator(DataUpdateCoordinator):
    """Coordinator die spelers één voor één ophaalt om rate limits te voorkomen."""

    def __init__(self, hass, session, api_key, players):
        super().__init__(
            hass,
            _LOGGER,
            name="Fortnite Global Coordinator",
            update_interval=SCAN_INTERVAL,
        )
        self.session = session
        self.api_key = api_key
        self.players = players
        self._current_player_index = 0
        # We slaan de data op per speler: { "Player1": {...}, "Player2": {...} }
        self.data = {player: {} for player in players}

    async def _async_update_data(self):
        """Haal data op voor de volgende speler in de lijst."""
        player_to_fetch = self.players[self._current_player_index]
        url = f"https://fortnite-api.com/v2/stats/br/v2?name={player_to_fetch}"
        headers = {"Authorization": self.api_key}

        _LOGGER.info(f"Bezig met ophalen Fortnite stats voor {player_to_fetch} (volgende speler over 15 min)")

        try:
            async with self.session.get(url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    res = await response.json()
                    stats = res['data']['stats']['all']['overall']
                    
                    # Update alleen de data van deze specifieke speler
                    self.data[player_to_fetch] = {
                        "wins": stats.get("wins"),
                        "kills": stats.get("kills"),
                        "deaths": stats.get("deaths"),
                        "matches": stats.get("matches"),
                        "kd": stats.get("kd")
                    }
                elif response.status == 429:
                    _LOGGER.warning("Rate limit bereikt. We slaan deze beurt over.")
                else:
                    _LOGGER.error(f"API Fout voor {player_to_fetch}: {response.status}")

            # Verplaats de index naar de volgende speler voor de volgende over 15 minuten
            self._current_player_index = (self._current_player_index + 1) % len(self.players)
            
            # Geef de volledige dictionary terug zodat alle sensoren hun data behouden
            return self.data

        except Exception as err:
            _LOGGER.error(f"Verbindingsfout tijdens ophalen {player_to_fetch}: {err}")
            return self.data

class FortniteSensor(CoordinatorEntity, SensorEntity):
    """Sensor die data uitleest uit de Global Coordinator."""

    def __init__(self, coordinator, player, key, label, icon, unit):
        super().__init__(coordinator)
        self.player = player
        self.key = key
        self._attr_name = f"Fortnite {player} {label}"
        self._attr_icon = icon
        self._attr_unique_id = f"fortnite_{player}_{key}".lower().replace(" ", "_")
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self):
        """Haal de waarde op van de specifieke speler uit de coordinator data."""
        if self.coordinator.data and self.player in self.coordinator.data:
            return self.coordinator.data[self.player].get(self.key)
        return None
