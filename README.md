# LoRA Preset Loader for ComfyUI

Save reusable, named stacks of LoRAs and apply them from one ComfyUI node. A preset remembers the LoRA files, order, enabled state, model strength, CLIP strength, and notes for a style such as **Ultra Realism**, **Cinematic**, or **Anime**.

## Features

- One **LoRA Preset Loader** node instead of a repeated chain of loader nodes.
- Multiple LoRAs per preset with no fixed row-slot limit, applied in the displayed order.
- Separate decimal model and CLIP strengths for every LoRA.
- Individual minus/value/plus controls with `0.1` button and keyboard steps.
- Exact typed values such as `0.75` and `0.125` are preserved.
- Optional CLIP input: use MODEL alone, or connect CLIP to apply text-encoder weights.
- Named presets shared across workflows on the same ComfyUI installation.
- Preset editor with create, update, delete, reorder, enable/disable, notes, and missing-file warnings.
- No additional Python or JavaScript dependencies.

## Installation

### Downloaded archive

1. Download and extract the release archive.
2. Copy the `comfyui-lora-preset-loader` folder to `ComfyUI/custom_nodes/`.
3. Confirm this file exists: `ComfyUI/custom_nodes/comfyui-lora-preset-loader/__init__.py`.
4. Restart ComfyUI completely.
5. Refresh the browser with `Ctrl+F5`.

For Windows portable, the usual location is `ComfyUI_windows_portable/ComfyUI/custom_nodes/`.

Avoid an extra nested folder such as `comfyui-lora-preset-loader/comfyui-lora-preset-loader/`.

### Git clone

Clone the repository directly into `custom_nodes`:

```sh
cd ComfyUI/custom_nodes
git clone https://github.com/Aerobit/ComfyUI-LoRA-Preset-Loader.git comfyui-lora-preset-loader
```

Restart ComfyUI after installing or updating.

## Quick start

1. Double-click the ComfyUI canvas and add **LoRA Preset Loader**. It is under **model → loaders**.
2. Connect the checkpoint loader's **MODEL** output to this node's **model** input.
3. Click **Edit presets**.
4. Open the included **Ultra Realism** starter or create a preset.
5. Add installed LoRAs and adjust each model and CLIP strength separately.
6. Click **Save & use preset**.
7. Choose that preset from the node whenever you need it.

The Ultra Realism starter is empty because the extension cannot know which LoRAs are installed. No LoRA files, checkpoints, or model weights are included.

## Connecting MODEL and CLIP

MODEL is required. CLIP is optional.

### Model-only workflow

- Connect the checkpoint **MODEL** to the preset loader.
- Connect the preset loader **MODEL** to the sampler.
- Leave both CLIP sockets on the preset loader disconnected.
- Keep the checkpoint CLIP connected directly to the text encoders.

Only each row's model strength is applied. Saved CLIP strengths remain unchanged for future use.

### Model and CLIP workflow

| From | To |
| --- | --- |
| Checkpoint loader **MODEL** | LoRA Preset Loader **model** |
| Checkpoint loader **CLIP** | LoRA Preset Loader **clip** |
| LoRA Preset Loader **MODEL** | Sampler **model** |
| LoRA Preset Loader **CLIP** | Positive and negative text encoders' **clip** inputs |

The VAE connection does not pass through this node.

## Strength controls

Every LoRA has an independent **Model strength** and **CLIP strength** control:

- Minus and plus adjust by exactly `0.1`.
- Keyboard up/down arrows also adjust by `0.1`.
- Click the number to type an exact decimal.
- Accepted values range from `-100` to `100`.
- A disabled row is ignored.
- With CLIP connected, a row whose two strengths are both zero is skipped.
- Without CLIP connected, a row whose model strength is zero is skipped.

Changing one field never changes another LoRA or the other strength on the same LoRA.

## Preset behavior

- **Save & use preset** updates the named preset and selects it on the node that opened the editor.
- Changing the name before saving creates a separate preset. Replacing another existing name requires confirmation.
- **Reload** refreshes the preset data and ComfyUI's installed LoRA list.
- **(No preset — bypass)** returns MODEL and any connected CLIP unchanged.
- Missing active LoRA files are reported before the node applies any LoRA.
- The order shown in the editor is the order in which LoRAs are applied.
- Notes are reminders only; trigger words still belong in normal prompt nodes.

## Preset storage

Presets are stored outside the extension folder so updating the code does not remove them:

```text
ComfyUI/user/lora_preset_loader/presets.json
```

If ComfyUI uses a custom user directory, the same `lora_preset_loader/presets.json` subpath is used there. Each successful update keeps the previous file as `presets.json.bak` and replaces the current file atomically.

Preset names are saved in workflows, but preset contents are not embedded in workflow JSON. Editing a shared preset affects future executions of every workflow using that name.

The schema and manual-editing rules are documented in [docs/PRESET_FORMAT.md](docs/PRESET_FORMAT.md).

## Troubleshooting

| Problem | Resolution |
| --- | --- |
| Node does not appear | Check folder nesting, restart ComfyUI, press `Ctrl+F5`, and inspect the console for `IMPORT FAILED`. |
| No **Edit presets** button | Hard-refresh the browser and confirm the extension's `web` folder was copied. |
| LoRA is not listed | Add it to a configured LoRA folder, refresh ComfyUI's model list, then use **Reload**. |
| Missing LoRA error | Install the named file, choose the correct relative path, or disable/remove the row. |
| Presets changed since editor opened | Preserve any values you need, click **Reload**, and reapply the edit. |
| Cannot save | Confirm ComfyUI can write to its user directory; the error includes the attempted path. |
| Invalid preset file | Stop ComfyUI, correct `presets.json`, or restore `presets.json.bak`. |
| Old portable build lacks `get_user_directory` | Install the current release; it includes a fallback for older portable builds. |

## Compatibility

The extension uses ComfyUI's supported V1 custom-node and JavaScript extension APIs. It delegates actual LoRA application to ComfyUI's built-in `LoraLoader`, so LoRA format, checkpoint architecture, and metadata compatibility match the installed ComfyUI version.

The project is tested without GPU inference using ComfyUI substitutes. A real workflow in your installation remains the final compatibility check.

## Development

```sh
python -m unittest discover -s tests -v
node --check web/lora_presets.js
node --experimental-vm-modules tests/test_frontend.mjs
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the implementation overview.

## Project documentation

- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Support](SUPPORT.md)
- [Code of conduct](CODE_OF_CONDUCT.md)
- [Changelog](CHANGELOG.md)
- [Preset file format](docs/PRESET_FORMAT.md)
- [Architecture](docs/ARCHITECTURE.md)

## License

Released under the [MIT License](LICENSE).
