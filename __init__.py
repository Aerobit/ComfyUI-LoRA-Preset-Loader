from .loader import LoraPresetLoader
from . import routes  # Register editor endpoints when ComfyUI loads the package.

NODE_CLASS_MAPPINGS = {"LoraPresetLoader": LoraPresetLoader}
NODE_DISPLAY_NAME_MAPPINGS = {"LoraPresetLoader": "LoRA Preset Loader"}
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
