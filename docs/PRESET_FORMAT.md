# Preset File Format

The loader stores UTF-8 JSON at `lora_preset_loader/presets.json` under the active ComfyUI user directory. Stop ComfyUI before manually editing it.

## Example

```json
{
  "version": 1,
  "presets": {
    "Ultra Realism": {
      "loras": [
        {
          "lora_name": "portraits/detail.safetensors",
          "strength_model": 0.75,
          "strength_clip": 0.5,
          "enabled": true
        }
      ],
      "notes": "Optional checkpoint and trigger-word reminder."
    }
  }
}
```

## Rules

- The root object contains exactly `version` and `presets`; `version` is currently integer `1`.
- Preset names contain 1–120 characters, have no surrounding whitespace or control characters, and cannot equal the reserved bypass label.
- Each preset contains an ordered `loras` array and optional `notes` up to 8,000 characters.
- Repeated LoRA filenames are allowed and are applied repeatedly.
- `lora_name` is a relative filename from configured LoRA folders. Absolute paths and traversal segments are rejected.
- Both strengths are finite JSON numbers from `-100` to `100`.
- `enabled` is a JSON boolean.
- The complete file is limited to 1 MiB. Duplicate keys and non-finite numbers are rejected.

Windows backslashes are normalized to forward slashes. Prefer filenames shown by the editor.

## Recovery

Saving validates the document and atomically replaces the current file. Previous contents are kept as `presets.json.bak`. If the main file becomes invalid, stop ComfyUI, copy both files somewhere safe, correct the main file or restore the backup, and restart.

The editor uses a revision hash to reject stale-tab saves. Reload before retrying a rejected edit.

