"""Preset editor endpoints. All writes target one fixed preset file."""

from aiohttp import web
from server import PromptServer

from .loader import STORE, installed_loras, resolve_rows
from .preset_store import NO_PRESET, PresetConflict, PresetError, validate_preset

routes = PromptServer.instance.routes


def response(snapshot=None):
    document, revision = snapshot if snapshot is not None else STORE.snapshot()
    return web.json_response({
        "presets": document["presets"], "revision": revision,
        "no_preset": NO_PRESET, "loras": sorted(installed_loras(), key=str.casefold),
    }, headers={"Cache-Control": "no-store"})


def error_response(exc):
    return web.json_response({"error": str(exc)}, status=409 if isinstance(exc, PresetConflict) else 400)


async def request_body(request):
    if request.content_type != "application/json":
        raise PresetError("Expected application/json.")
    body = await request.json()
    if not isinstance(body, dict):
        raise PresetError("Expected a JSON object.")
    return body


@routes.get("/lora-preset-loader/presets")
async def get_presets(request):
    try:
        return response()
    except (ValueError, OSError) as exc:
        return error_response(exc)


@routes.post("/lora-preset-loader/presets/save")
async def save_preset(request):
    try:
        body = await request_body(request)
        preset = validate_preset(body.get("preset"))
        resolve_rows(preset)
        result = STORE.save(body.get("name"), preset, body.get("revision"), body.get("overwrite", False))
        return response(result)
    except (ValueError, OSError) as exc:
        return error_response(exc)


@routes.post("/lora-preset-loader/presets/delete")
async def delete_preset(request):
    try:
        body = await request_body(request)
        return response(STORE.delete(body.get("name"), body.get("revision")))
    except (ValueError, OSError) as exc:
        return error_response(exc)
