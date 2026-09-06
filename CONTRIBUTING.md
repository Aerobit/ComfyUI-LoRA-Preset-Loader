# Contributing

Thank you for helping improve LoRA Preset Loader.

## Before opening an issue

- Confirm the problem still occurs with current ComfyUI and extension versions.
- Restart ComfyUI and hard-refresh the browser.
- Search existing issues.
- Remove unrelated custom nodes from the reproduction when practical.
- Do not post private workflows, credentials, prompts, or model files.

## Development setup

ComfyUI supplies the extension's runtime modules. For live testing, place this repository in `ComfyUI/custom_nodes/comfyui-lora-preset-loader`, restart ComfyUI, and hard-refresh after frontend changes.

```sh
python -m unittest discover -s tests -v
node --check web/lora_presets.js
node --experimental-vm-modules tests/test_frontend.mjs
```

## Pull requests

1. Keep changes focused and preserve preset files and workflow compatibility.
2. Add or update tests for behavior changes.
3. Update user documentation and the changelog when behavior changes.
4. Run every check above.
5. Test the affected workflow in ComfyUI when possible.
6. Explain what changed, why, and what was verified.

## Compatibility expectations

- Never write presets inside the extension directory.
- Never silently replace a missing preset with bypass.
- Check every applicable LoRA path before applying the first LoRA.
- Preserve separate decimal model and CLIP strengths.
- Keep CLIP optional and preserve model-only workflows.
- Keep network access out of normal node execution.

By contributing, you agree that your contribution may be distributed under the MIT License.

