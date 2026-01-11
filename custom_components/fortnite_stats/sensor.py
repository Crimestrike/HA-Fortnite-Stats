import logging
import asyncio
from datetime import timedelta

import aiohttp
import voluptuous as vol

# Deze import is essentieel om de 'api_key' fout op te lossen:
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
# Scan interval op 15 minuten. 
# Omdat we rouleren, wordt elke individuele speler eens per (15 * aantal_spelers) minuten geüpdatet.
SCAN_INTERVAL = timedelta(minutes=15)

# Hier definiëren we dat 'api_key' verplicht is. 
# Als HA hierover klaagt, leest hij dit stukje code niet.
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_API_KEY): cv.string,
    vol.Required(CONF_PLAYERS): vol.All(cv.ensure_list, [cv.string]),
})

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up de Fortnite sensoren met sequentiële updates."""
    # Gebruik .get() voor veiligheid, maar schema validatie vangt het meestal al af
    api_key = config.get(CONF_API_KEY)
    players = config.get(CONF_PLAYERS)
    
    session = async_get_clientsession(hass)

    # We maken één gedeelde coordinator aan
    coordinator = FortniteSequentialCoordinator(hass, session, api_key, players)
    
    # Haal direct de eerste keer data op (dit pakt alleen speler 1!)
    await coordinator.async_refresh()

    entities = []
    # Maak wel alvast de sensoren aan voor ALLE spelers
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

class FortniteSequentialCoordinator(DataUpdateCoordinator):
    """Coordinator die spelers één voor één ophaalt."""

    def __init__(self, hass, session, api_key, players):
        super().__init__(
            hass,
            _LOGGER,
            name="Fortnite Sequential Coordinator",
            update_interval=SCAN_INTERVAL,
        )
        self.session = session
        self.api_key = api_key
        self.players = players
        self._current_player_index = 0
        
        # We initialiseren lege data voor iedereen, zodat sensoren niet crashen voor de eerste update
        self.data = {player: {} for player in players}

    async def _async_update_data(self):
        """Haal data op voor ééntje, en schuif de index door."""
        # Wie is er aan de beurt?
        player_to_fetch = self.players[self._current_player_index]
        
        url = f"https://fortnite-api.com/v2/stats/br/v2?name={player_to_fetch}"
        headers = {"Authorization": self.api_key}

        _LOGGER.debug(f"Fortnite update beurt: {player_to_fetch} ophalen...")

        try:
            async with self.session.get(url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    res = await response.json()
                    if "data" in res and "stats" in res["data"]:
                        stats = res['data']['stats']['all']['overall']
                        
                        # Update ALLEEN de data van de huidige speler in het geheugen
                        self.data[player_to_fetch] = {
                            "wins": stats.get("wins"),
                            "kills": stats.get("kills"),
                            "deaths": stats.get("deaths"),
                            "matches": stats.get("matches"),
                            "kd": stats.get("kd")
                        }
                    else:
                        _LOGGER.error(f"Ongeldige data structuur voor {player_to_fetch}")
                elif response.status == 429:
                    _LOGGER.warning(f"Rate limit hit tijdens ophalen {player_to_fetch}. We proberen het over 15 min opnieuw.")
                elif response.status == 404:
                     _LOGGER.error(f"Speler {player_to_fetch} niet gevonden.")
                else:
                    _LOGGER.error(f"API Fout {response.status} voor {player_to_fetch}")

            # BELANGRIJK: Schuif de beurt door naar de volgende speler
            # De modulo operator (%) zorgt dat hij na de laatste speler weer bij 0 begint
            self._current_player_index = (self._current_player_index + 1) % len(self.players)
            
            # Retourneer de complete dataset (met oude data van de anderen + nieuwe data van de huidige)
            return self.data

        except Exception as err:
            _LOGGER.error(f"Verbindingsfout bij {player_to_fetch}: {err}")
            # Bij een fout ook doorschuiven, anders blijft hij hangen op de 'kapotte' speler
            self._current_player_index = (self._current_player_index + 1) % len(self.players)
            return self.data

class FortniteSensor(CoordinatorEntity, SensorEntity):
    """Sensor die wacht tot zijn specifieke speler aan de beurt is geweest."""

    def __init__(self, coordinator, player, key, label, icon, unit):
        super().__init__(coordinator)
        self.player = player
        self.key = key
        self._attr_name = f"Fortnite {player} {label}"
        self._attr_icon = icon
        self._attr_unique_id = f"fortnite_{player}_{key}".lower().replace(" ", "_")
        
        # Grafiek instellingen
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self):
        """Haal waarde op uit de centrale dataset."""
        # Check of we data hebben én of onze speler erin staat
        if self.coordinator.data and self.player in self.coordinator.data:
            return self.coordinator.data[self.player].get(self.key)
        return None
