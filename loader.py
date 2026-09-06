"""Apply a saved LoRA stack to MODEL and, optionally, CLIP."""

import hashlib
import json
import logging
from pathlib import Path

import folder_paths
from nodes import LoraLoader

from .preset_store import NO_PRESET, PresetError, PresetStore, normalize_filename

def preset_file_path():
    # Older portable builds predate get_user_directory(). Do not let that
    # optional helper prevent ComfyUI from importing and registering the node.
    get_user_directory = getattr(folder_paths, "get_user_directory", None)
    if callable(get_user_directory):
        user_directory = get_user_directory()
    else:
        user_directory = getattr(folder_paths, "user_directory", None)
    if user_directory is None:
        base_path = getattr(folder_paths, "base_path", None)
        if base_path is None:
            base_path = Path(folder_paths.__file__).resolve().parent
        user_directory = Path(base_path) / "user"
    return Path(user_directory) / "lora_preset_loader" / "presets.json"


STORE = PresetStore(preset_file_path())
LOGGER = logging.getLogger(__name__)


def installed_loras():
    # Preserve ComfyUI's native names when invoking its loader (Windows included).
    return {normalize_filename(name): name for name in folder_paths.get_filename_list("loras")}


def resolve_rows(preset, apply_clip=True):
    installed = installed_loras()
    planned, missing = [], []
    for row in preset["loras"]:
        if not row["enabled"] or (row["strength_model"] == 0
                                   and (not apply_clip or row["strength_clip"] == 0)):
            continue
        name = row["lora_name"]
        native_name = installed.get(name)
        full_path = folder_paths.get_full_path("loras", native_name) if native_name is not None else None
        if full_path is None or not Path(full_path).is_file():
            missing.append(name)
        else:
            planned.append((row, native_name, Path(full_path)))
    if missing:
        raise PresetError("Missing LoRA file(s): " + ", ".join(missing)
                          + ". Install them in a ComfyUI LoRA folder, or edit/disable those rows.")
    return planned


def execution_plan(name, apply_clip=True):
    preset = STORE.get(name)
    if not preset["loras"]:
        raise PresetError(f"Preset {name!r} has no LoRAs yet. Click Edit presets, add your "
                          "installed LoRAs and strengths, then Save & use preset.")
    return resolve_rows(preset, apply_clip=apply_clip)


class LoraPresetLoader:
    CATEGORY = "model/loaders"
    RETURN_TYPES = ("MODEL", "CLIP")
    RETURN_NAMES = ("MODEL", "CLIP")
    OUTPUT_TOOLTIPS = ("The model with the preset's LoRAs applied.",
                       "The modified CLIP, available only when the CLIP input is connected.")
    FUNCTION = "load_preset"
    DESCRIPTION = "Apply a named LoRA preset to MODEL. Connect optional CLIP to also apply its saved strengths."
    SEARCH_ALIASES = ["lora presets", "style preset", "lora stack"]

    @classmethod
    def INPUT_TYPES(cls):
        try:
            document, _ = STORE.snapshot()
            names = sorted(document["presets"], key=str.casefold)
        except PresetError as exc:
            # Keep the node available, so the editor can report a corrupt config.
            LOGGER.error("LoRA Preset Loader: %s", exc)
            names = []
        return {"required": {
            "model": ("MODEL",),
            "preset": ([NO_PRESET] + names, {"default": NO_PRESET,
                "tooltip": "Choose a saved style. Use Edit presets to choose LoRAs and save their strengths."}),
        }, "optional": {
            "clip": ("CLIP", {"tooltip": "Optional. Leave disconnected for model-only loading; connect to apply saved CLIP strengths too."}),
        }}

    @classmethod
    def VALIDATE_INPUTS(cls, preset=None):
        # A linked preset string is validated during execution instead.
        if preset is None or preset == NO_PRESET:
            return True
        try:
            # Linked CLIP is not available during validation. Check model rows
            # now; execution checks every applicable file once CLIP is resolved.
            execution_plan(preset, apply_clip=False)
            return True
        except (PresetError, OSError) as exc:
            return str(exc)

    @classmethod
    def IS_CHANGED(cls, preset, **kwargs):
        if preset == NO_PRESET:
            return "bypass"
        try:
            signatures = []
            # Conservatively track both saved strengths: linked inputs may not
            # be resolved when ComfyUI asks for the cache fingerprint.
            for row, native_name, path in execution_plan(preset):
                stat = path.stat()
                signatures.append([row, str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns])
            payload = json.dumps([preset, signatures], sort_keys=True).encode("utf-8")
            return hashlib.sha256(payload).hexdigest()
        except (PresetError, OSError):
            # Never reuse an old successful result when a preset/file is now invalid.
            return float("nan")

    def load_preset(self, model, clip=None, preset=NO_PRESET):
        if preset == NO_PRESET:
            return model, clip
        apply_clip = clip is not None
        planned = execution_plan(preset, apply_clip=apply_clip)
        if not planned:
            return model, clip
        loader = LoraLoader()
        for row, native_name, _ in planned:
            model, clip = loader.load_lora(
                model, clip, native_name, row["strength_model"],
                row["strength_clip"] if apply_clip else 0.0
            )
        return model, clip
