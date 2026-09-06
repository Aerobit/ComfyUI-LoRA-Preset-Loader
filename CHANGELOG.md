# Changelog

Notable changes are documented here. The project follows [Semantic Versioning](https://semver.org/) after its first tagged release.

## [Unreleased]

## [1.0.0] - 2026-09-06

### Added

- Named, ordered LoRA presets in one node.
- Independent model and CLIP decimal strengths per LoRA.
- Optional CLIP input for model-only workflows.
- Preset CRUD, ordering, enable/disable state, and notes.
- Atomic persistence, backup, revision conflicts, and path validation.
- Compatibility fallback for older portable builds without `get_user_directory`.

[Unreleased]: https://github.com/Aerobit/ComfyUI-LoRA-Preset-Loader/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Aerobit/ComfyUI-LoRA-Preset-Loader/releases/tag/v1.0.0
