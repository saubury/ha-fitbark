"""Sensor platform for FitBark."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTime, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FitBarkConfigEntry
from .api import FitBarkDogSnapshot
from .const import ATTRIBUTION, DOMAIN, MANUFACTURER
from .coordinator import FitBarkDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class FitBarkSensorEntityDescription(SensorEntityDescription):
    """Describes a FitBark sensor entity."""

    value_fn: Callable[[FitBarkDogSnapshot], float | int | None]


SENSOR_DESCRIPTIONS: tuple[FitBarkSensorEntityDescription, ...] = (
    FitBarkSensorEntityDescription(
        key="activity_points_today",
        translation_key="activity_points_today",
        icon="mdi:paw",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snap: snap.activity_points,
    ),
    FitBarkSensorEntityDescription(
        key="activity_goal_percent",
        translation_key="activity_goal_percent",
        icon="mdi:target",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snap: snap.activity_goal_percent,
    ),
    FitBarkSensorEntityDescription(
        key="minutes_active",
        translation_key="minutes_active",
        icon="mdi:run",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snap: snap.minutes_active,
    ),
    FitBarkSensorEntityDescription(
        key="minutes_play",
        translation_key="minutes_play",
        icon="mdi:tennis-ball",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snap: snap.minutes_play,
    ),
    FitBarkSensorEntityDescription(
        key="minutes_rest",
        translation_key="minutes_rest",
        icon="mdi:sleep",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snap: snap.minutes_rest,
    ),
    FitBarkSensorEntityDescription(
        key="battery_level",
        translation_key="battery_level",
        device_class=SensorDeviceClass.BATTERY,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda snap: snap.battery_level,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FitBarkConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up FitBark sensors from a config entry."""
    coordinator = entry.runtime_data
    known_dogs: set[str] = set()

    @callback
    def _add_new_dogs() -> None:
        new_dogs = set(coordinator.data) - known_dogs
        if not new_dogs:
            return
        known_dogs.update(new_dogs)
        async_add_entities(
            FitBarkSensor(coordinator, dog_slug, description)
            for dog_slug in new_dogs
            for description in SENSOR_DESCRIPTIONS
        )

    entry.async_on_unload(coordinator.async_add_listener(_add_new_dogs))
    _add_new_dogs()


class FitBarkSensor(CoordinatorEntity[FitBarkDataUpdateCoordinator], SensorEntity):
    """Representation of a single FitBark dog metric."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    entity_description: FitBarkSensorEntityDescription

    def __init__(
        self,
        coordinator: FitBarkDataUpdateCoordinator,
        dog_slug: str,
        description: FitBarkSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._dog_slug = dog_slug
        self._attr_unique_id = f"{dog_slug}_{description.key}"

        dog = coordinator.data[dog_slug].dog
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dog_slug)},
            name=dog.name,
            manufacturer=MANUFACTURER,
            model=dog.breed or "Dog Activity Monitor",
        )

    @property
    def native_value(self) -> float | int | None:
        """Return the current sensor value."""
        snapshot = self.coordinator.data.get(self._dog_slug)
        if snapshot is None:
            return None
        return self.entity_description.value_fn(snapshot)

    @property
    def available(self) -> bool:
        """Entity is unavailable if this dog dropped out of the coordinator data."""
        return super().available and self._dog_slug in self.coordinator.data
