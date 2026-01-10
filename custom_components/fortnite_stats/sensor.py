import logging
import voluptuous as vol
import aiohttp
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.helpers.event import async_track_time_interval

_LOGGER = logging.getLogger(__name__)

# Instellingen voor de YAML
CONF_PLAYERS = "players"
SCAN_INTERVAL = timedelta(minutes=30) # Niet te vaak i.v.m. rate limits

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_PLAYERS): vol.All(cv.ensure_list, [cv.string]),
})

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up de Fortnite sensoren vanuit YAML."""
    players = config[CONF_PLAYERS]
    entities = []

    for player in players:
        # We maken per speler één 'DataCoordinator' aan die alle stats ophaalt
        coordinator = FortniteDataUpdateCoordinator(hass, player)
        
        # We voegen voor elke waarde een sensor toe
        entities.append(FortniteSensor(coordinator, player, "wins", "Wins"))
        entities.append(FortniteSensor(coordinator, player, "kills", "Kills"))
        entities.append(FortniteSensor(coordinator, player, "deaths", "Deaths"))
        entities.append(FortniteSensor(coordinator, player, "kd", "KD Ratio"))

    async_add_entities(entities, True)

class FortniteDataUpdateCoordinator:
    """Regelt het ophalen van de data voor een specifieke speler."""
    def __init__(self, hass, player_name):
        self.player_name = player_name
        self.data = {}

    async def async_update(self):
        url = f"https://fortnite-api.com/v2/stats/br/v2?name={self.player_name}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        res_data = await response.json()
                        stats = res_data['data']['stats']['all']['overall']
                        
                        self.data['wins'] = stats['wins']
                        self.data['kills'] = stats['kills']
                        self.data['deaths'] = stats['deaths']
                        
                        # KD Ratio berekening
                        k = stats['kills']
                        d = stats['deaths']
                        self.data['kd'] = round(k / d, 2) if d > 0 else k
                    else:
                        _LOGGER.error(f"Fortnite API fout voor {self.player_name}: {response.status}")
            except Exception as e:
                _LOGGER.error(f"Fout bij ophalen Fortnite data: {e}")

class FortniteSensor(SensorEntity):
    """De eigenlijke sensor in Home Assistant."""
    def __init__(self, coordinator, player, key, label):
        self.coordinator = coordinator
        self.key = key
        self._name = f"Fortnite {player} {label}"

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self.coordinator.data.get(self.key)

    async def async_update(self):
        """Haal nieuwe data op via de coordinator."""
        await self.coordinator.async_update()