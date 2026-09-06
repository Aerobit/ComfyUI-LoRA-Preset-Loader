# Architecture

LoRA Preset Loader is a ComfyUI V1 custom-node extension with a Python backend and browser-native editor.

| Path | Responsibility |
| --- | --- |
| `__init__.py` | Registers the node and frontend directory. |
| `loader.py` | Declares inputs/outputs, resolves rows, checks files, fingerprints cache inputs, and invokes ComfyUI's loader. |
| `preset_store.py` | Validates JSON, normalizes filenames, manages revisions/backups, and writes atomically. |
| `routes.py` | Provides list, save, and delete endpoints through ComfyUI's server. |
| `web/lora_presets.js` | Registers the editor button, synchronizes choices, and implements the preset editor. |
| `web/lora_presets.css` | Styles the editor and independent strength controls. |
| `tests/` | Tests backend behavior and frontend lifecycle hooks without GPU inference. |

## Execution flow

1. ComfyUI supplies MODEL, a preset name, and optionally CLIP.
2. The store reads and validates the preset document.
3. Disabled rows and rows with no applicable strength are removed.
4. Every applicable filename is checked before loading starts.
5. Rows are passed in order to ComfyUI's built-in `LoraLoader`.
6. Without CLIP, the loader receives `None` and a CLIP strength of zero, matching ComfyUI's model-only behavior.
7. The node returns modified MODEL and modified CLIP or `None`.

The editor sends structured JSON only to fixed routes. The backend validates field types, numeric ranges, document size, names, and relative paths. Presets live under the ComfyUI user directory rather than the source tree.

`IS_CHANGED` hashes the selected active rows with resolved file paths, sizes, and timestamps. An invalid selection returns a non-cacheable value so an earlier output is not reused.

Compatibility principles: preserve `LoraPresetLoader`, preserve the JSON schema or migrate explicitly, keep MODEL required and CLIP optional, keep user data outside the extension, and delegate LoRA parsing to ComfyUI.

