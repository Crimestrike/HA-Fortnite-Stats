import logging
import asyncio
import aiohttp
from datetime import timedelta

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import CONF_API_KEY, CONF_NAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

# Instellingen
CONF_PLAYERS = "players"
SCAN_INTERVAL = timedelta(minutes=15) # De API ververst niet vaker dan dit

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
        # We maken per speler één coordinator aan die de data beheert
        coordinator = FortniteDataCoordinator(hass, session, api_key, player)
        
        # Voeg de verschillende sensoren toe voor deze speler
        entities.append(FortniteSensor(coordinator, player, "wins", "Wins", "mdi:trophy"))
        entities.append(FortniteSensor(coordinator, player, "kills", "Kills", "mdi:target"))
        entities.append(FortniteSensor(coordinator, player, "deaths", "Deaths", "mdi:skull"))
        entities.append(FortniteSensor(coordinator, player, "kd", "KD Ratio", "mdi:calculator"))
        entities.append(FortniteSensor(coordinator, player, "matches", "Matches", "mdi:controller-classic"))

    async_add_entities(entities, True)

class FortniteDataCoordinator:
    """Helper klasse om data op te halen en te delen tussen sensoren."""

    def __init__(self, hass, session, api_key, player_name):
        self.hass = hass
        self.session = session
        self.api_key = api_key
        self.player_name = player_name
        self.data = {}

    async def async_update(self):
        """Haal de data op bij Fortnite-API.com."""
        url = f"https://fortnite-api.com/v2/stats/br/v2?name={self.player_name}"
        headers = {"Authorization": self.api_key}

        try:
            async with self.session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    json_res = await response.json()
                    # Navigeer naar de juiste plek in de JSON
                    stats = json_res['data']['stats']['all']['overall']
                    
                    self.data = {
                        "wins": stats.get("wins"),
                        "kills": stats.get("kills"),
                        "deaths": stats.get("deaths"),
                        "matches": stats.get("matches"),
                        "kd": stats.get("kd")
                    }
                    _LOGGER.debug(f"Fortnite data bijgewerkt voor {self.player_name}")
                elif response.status == 403:
                    _LOGGER.error(f"Fout: Profiel van {self.player_name} staat op 'Private'.")
                elif response.status == 401:
                    _LOGGER.error("Fout: Ongeldige Fortnite API Key.")
                else:
                    _LOGGER.error(f"Fortnite API fout {response.status} voor {self.player_name}")
        except Exception as e:
            _LOGGER.error(f"Fout bij verbinden met Fortnite API: {e}")

class FortniteSensor(SensorEntity):
    """Representatie van een Fortnite statistiek."""

    def __init__(self, coordinator, player, key, label, icon):
        self.coordinator = coordinator
        self.key = key
        self._player = player
        self._label = label
        self._icon = icon
        self._attr_name = f"Fortnite {player} {label}"
        self._attr_unique_id = f"fortnite_{player}_{key}".lower().replace(" ", "_")

    @property
    def icon(self):
        return self._icon

    @property
    def state(self):
        """Geef de waarde van de specifieke statistiek terug."""
        return self.coordinator.data.get(self.key)

    async def async_update(self):
        """Vraag de coordinator om een update."""
        await self.coordinator.async_update()