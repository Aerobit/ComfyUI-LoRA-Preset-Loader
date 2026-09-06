"""Validated JSON storage for LoRA presets; no ComfyUI dependencies."""

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import threading

NO_PRESET = "(No preset — bypass)"
MAX_BYTES = 1024 * 1024
DEFAULT_DOCUMENT = {
    "version": 1,
    "presets": {
        "Ultra Realism": {
            "loras": [],
            "notes": "Add your installed realism LoRAs and save this preset. "
                     "You can record the intended checkpoint and trigger words here.",
        }
    },
}


class PresetError(ValueError):
    pass


class PresetConflict(PresetError):
    pass


def validate_name(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 120:
        raise PresetError("Preset names must contain 1–120 characters.")
    if value != value.strip() or any(ord(c) < 32 for c in value):
        raise PresetError("Preset names cannot have surrounding spaces or control characters.")
    if value == NO_PRESET:
        raise PresetError("This name is reserved for bypass.")
    return value


def normalize_filename(value):
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise PresetError("Each LoRA needs a filename from ComfyUI's LoRA list.")
    value = value.replace("\\", "/")
    if (value.startswith("/") or ":" in value
            or any(ord(c) < 32 for c in value)
            or any(part in ("", ".", "..") for part in value.split("/"))):
        raise PresetError("LoRA names must be relative filenames, including any subfolder.")
    return value


def validate_strength(value, label):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not -100 <= value <= 100 or not math.isfinite(value)):
        raise PresetError(f"{label} must be a finite number between -100 and 100.")
    return float(value)


def validate_preset(value):
    if not isinstance(value, dict) or set(value) - {"loras", "notes"}:
        raise PresetError("Each preset must contain 'loras' and optional 'notes'.")
    rows = value.get("loras")
    if not isinstance(rows, list):
        raise PresetError("'loras' must be a list.")
    notes = value.get("notes", "")
    if not isinstance(notes, str) or len(notes) > 8000:
        raise PresetError("Notes must be text of at most 8000 characters.")
    result = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or set(row) - {
            "lora_name", "strength_model", "strength_clip", "enabled"
        }:
            raise PresetError(f"LoRA row {index} has invalid fields.")
        enabled = row.get("enabled", True)
        if not isinstance(enabled, bool):
            raise PresetError(f"LoRA row {index}: enabled must be true or false.")
        try:
            result.append({
                "lora_name": normalize_filename(row.get("lora_name")),
                "strength_model": validate_strength(row.get("strength_model", 1.0), "Model strength"),
                "strength_clip": validate_strength(row.get("strength_clip", 1.0), "CLIP strength"),
                "enabled": enabled,
            })
        except PresetError as exc:
            raise PresetError(f"LoRA row {index}: {exc}") from exc
    return {"loras": result, "notes": notes}


def validate_document(value):
    if (not isinstance(value, dict) or type(value.get("version")) is not int
            or value["version"] != 1 or set(value) != {"version", "presets"}
            or not isinstance(value["presets"], dict)):
        raise PresetError("Expected a JSON object with version: 1 and a presets object.")
    return {"version": 1, "presets": {
        validate_name(name): validate_preset(preset)
        for name, preset in value["presets"].items()
    }}


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PresetError(f"Duplicate JSON key: {key!r}.")
        result[key] = value
    return result


def _encode(document):
    return (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def _revision(document):
    return hashlib.sha256(_encode(document)).hexdigest()


class PresetStore:
    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.RLock()

    def _read(self):
        try:
            with self.path.open("rb") as handle:
                raw = handle.read(MAX_BYTES + 1)
        except FileNotFoundError:
            return copy.deepcopy(DEFAULT_DOCUMENT)
        except OSError as exc:
            raise PresetError(f"Cannot read {self.path}: {exc}") from exc
        if len(raw) > MAX_BYTES:
            raise PresetError(f"{self.path} exceeds the 1 MiB preset file limit.")
        try:
            return validate_document(json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_keys))
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise PresetError(f"Invalid preset file {self.path}: {exc}. "
                              "Fix the file or restore presets.json.bak; it has not been overwritten.") from exc

    def snapshot(self):
        with self._lock:
            document = self._read()
            return document, _revision(document)

    def get(self, name):
        validate_name(name)
        document, _ = self.snapshot()
        if name not in document["presets"]:
            raise PresetError(f"Preset {name!r} does not exist. Open Edit presets to choose or create it.")
        return document["presets"][name]

    @staticmethod
    def _atomic_write(path, content):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent,
                                             prefix=path.name + ".", suffix=".tmp",
                                             delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _commit(self, document):
        content = _encode(validate_document(document))
        if len(content) > MAX_BYTES:
            raise PresetError("Preset data exceeds the 1 MiB file limit.")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                self._atomic_write(self.path.with_suffix(".json.bak"), self.path.read_bytes())
            self._atomic_write(self.path, content)
        except OSError as exc:
            raise PresetError(f"Could not save {self.path}: {exc}") from exc
        return document, _revision(document)

    def _check_revision(self, document, revision):
        if not isinstance(revision, str) or revision != _revision(document):
            raise PresetConflict("Presets changed since this editor was opened. "
                                 "Copy any unsaved values, then use Reload to get the latest presets.")

    def save(self, name, preset, revision, overwrite=False):
        name, preset = validate_name(name), validate_preset(preset)
        if not isinstance(overwrite, bool):
            raise PresetError("overwrite must be true or false.")
        with self._lock:
            document = self._read()
            self._check_revision(document, revision)
            if name in document["presets"] and not overwrite:
                raise PresetConflict(f"A preset named {name!r} already exists.")
            document["presets"][name] = preset
            return self._commit(document)

    def delete(self, name, revision):
        validate_name(name)
        with self._lock:
            document = self._read()
            self._check_revision(document, revision)
            if name not in document["presets"]:
                raise PresetError(f"Preset {name!r} no longer exists.")
            del document["presets"][name]
            return self._commit(document)
