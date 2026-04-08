"""GET/PUT/DELETE /api/config/* — live-editable settings.

The hot-field registry in
:mod:`hypersussy.api.settings_service` gates which fields this route
accepts. Writes update the in-memory ``HyperSussySettings`` instance
shared with the BackgroundRunner *and* persist the override in the
``settings_overrides`` SQLite table so it survives restarts.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from hypersussy.api.deps import ConfigStorageDep, SettingsDep
from hypersussy.api.schemas import (
    ConfigFieldItem,
    ConfigResponse,
    ConfigUpdateRequest,
)
from hypersussy.api.settings_service import (
    HOT_FIELDS,
    SettingsUpdateError,
    clear_override,
    persist_override,
    update_field,
)
from hypersussy.config import HyperSussySettings

router = APIRouter(prefix="/config", tags=["config"])

# Baseline values before any overrides are applied. Built once at
# import time from a default-constructed HyperSussySettings so the
# "reset to default" button and the ``default`` field in responses
# reflect code defaults (and env vars active at startup), not the
# current live values. This is deliberate — env vars set in the
# process environment are treated as "defaults" for UI purposes.
_DEFAULTS: dict[str, float | int | bool] = {
    name: getattr(HyperSussySettings(), name) for name in HOT_FIELDS
}


def _field_type(value: object) -> str:
    """Return the JSON-facing type label for a setting value."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    # Everything in HOT_FIELDS is numeric or boolean; anything else is
    # a registry bug worth surfacing immediately.
    msg = f"unsupported hot-field value type: {type(value).__name__}"
    raise TypeError(msg)


def _build_item(
    key: str,
    settings: HyperSussySettings,
) -> ConfigFieldItem:
    """Assemble a single response item from the registry + live value."""
    meta = HOT_FIELDS[key]
    current = getattr(settings, key)
    default = _DEFAULTS[key]
    return ConfigFieldItem(
        key=key,
        section=meta.section,
        label=meta.label,
        description=meta.description,
        type=_field_type(current),
        value=current,
        default=default,
        overridden=current != default,
        minimum=meta.minimum,
        maximum=meta.maximum,
    )


@router.get("")
def get_config(settings: SettingsDep) -> ConfigResponse:
    """Return every live-editable setting with its current value.

    The response is ordered by the HOT_FIELDS registry iteration
    order, which is authored by section so the frontend can group
    without extra sorting.

    Args:
        settings: Injected live settings instance.

    Returns:
        ConfigResponse with one ConfigFieldItem per hot field.
    """
    items = [_build_item(key, settings) for key in HOT_FIELDS]
    return ConfigResponse(fields=items)


@router.put("/{key}")
async def put_config_field(
    key: str,
    body: ConfigUpdateRequest,
    settings: SettingsDep,
    storage: ConfigStorageDep,
) -> ConfigFieldItem:
    """Validate, apply, and persist a single config field update.

    The sequence is: Pydantic validation (via a fresh settings
    instance inside ``update_field``) → in-place mutation of the
    live settings object → persistence to the ``settings_overrides``
    table. If validation fails the live object is untouched and the
    client gets a 422.

    Args:
        key: Hot-field name to update.
        body: New value payload.
        settings: Injected live settings instance (mutated in place).
        storage: Injected async storage handle for the override write.

    Returns:
        The updated ConfigFieldItem reflecting the applied value.

    Raises:
        HTTPException: 404 if ``key`` is not in the hot registry,
            422 if validation rejects the new value.
    """
    if key not in HOT_FIELDS:
        raise HTTPException(status_code=404, detail=f"unknown field {key!r}")
    try:
        applied = update_field(settings, key, body.value)
    except SettingsUpdateError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await persist_override(storage, key, applied)
    return _build_item(key, settings)


@router.delete("/{key}")
async def delete_config_field(
    key: str,
    settings: SettingsDep,
    storage: ConfigStorageDep,
) -> ConfigFieldItem:
    """Reset a field to its startup default.

    Removes the persisted override and restores the field on the
    live settings instance to the value captured at process start.
    If the field has never been overridden this is a no-op from the
    client's perspective.

    Args:
        key: Hot-field name to reset.
        settings: Injected live settings instance.
        storage: Injected async storage handle.

    Returns:
        The updated ConfigFieldItem reflecting the default value.

    Raises:
        HTTPException: 404 if ``key`` is not in the hot registry.
    """
    if key not in HOT_FIELDS:
        raise HTTPException(status_code=404, detail=f"unknown field {key!r}")
    default = _DEFAULTS[key]
    # Defaults come from the hot registry so they're always valid —
    # update_field still runs them through Pydantic which is cheap
    # and keeps the mutation path uniform.
    try:
        update_field(settings, key, default)
    except SettingsUpdateError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    await clear_override(storage, key)
    return _build_item(key, settings)
