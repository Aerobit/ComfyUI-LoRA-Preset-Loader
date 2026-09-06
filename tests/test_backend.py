"""Behavior checks with only stdlib; ComfyUI's model loader is replaced by a spy."""

import asyncio
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class FakeRoutes:
    def __init__(self):
        self.handlers = {}

    def route(self, method, path):
        def register(handler):
            self.handlers[method, path] = handler
            return handler
        return register

    def get(self, path):
        return self.route("GET", path)

    def post(self, path):
        return self.route("POST", path)


class LoaderSpy:
    calls = []

    def load_lora(self, model, clip, filename, strength_model, strength_clip):
        self.calls.append((model, clip, filename, strength_model, strength_clip))
        return model + (filename,), None if clip is None else clip + ((filename, strength_clip),)


fake_folders = types.ModuleType("folder_paths")
fake_folders.get_user_directory = lambda: str(ROOT / "unused-test-user-dir")
fake_folders.get_filename_list = lambda _: []
fake_folders.get_full_path = lambda *_: None
fake_nodes = types.ModuleType("nodes")
fake_nodes.LoraLoader = LoaderSpy
fake_server = types.ModuleType("server")
fake_server.PromptServer = types.SimpleNamespace(instance=types.SimpleNamespace(routes=FakeRoutes()))
fake_aiohttp = types.ModuleType("aiohttp")
fake_aiohttp.web = types.SimpleNamespace(json_response=lambda body, status=200, headers=None: {
    "body": body, "status": status, "headers": headers,
})

with patch.dict(sys.modules, {"folder_paths": fake_folders, "nodes": fake_nodes,
                              "server": fake_server, "aiohttp": fake_aiohttp}):
    spec = importlib.util.spec_from_file_location("lpl_test_package", ROOT / "__init__.py",
                                                submodule_search_locations=[str(ROOT)])
    package = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = package
    spec.loader.exec_module(package)

backend = package.loader
storage = package.preset_store
routes = package.routes


def row(name="detail.safetensors", model=0.7, clip=0.4, enabled=True):
    return {"lora_name": name, "strength_model": model, "strength_clip": clip, "enabled": enabled}


def preset(*rows):
    return {"loras": list(rows), "notes": "Test preset"}


class Request:
    def __init__(self, body, content_type="application/json"):
        self.body = body
        self.content_type = content_type

    async def json(self):
        return self.body


class PresetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = storage.PresetStore(self.root / "user" / "lora_preset_loader" / "presets.json")
        self.loras = self.root / "loras"
        self.loras.mkdir()
        self.available = {}
        for module, name, value in [
            (backend, "STORE", self.store), (routes, "STORE", self.store),
            (fake_folders, "get_filename_list", lambda _: list(self.available)),
            (fake_folders, "get_full_path", lambda _, name: self.available.get(name)),
        ]:
            manager = patch.object(module, name, value)
            manager.start()
            self.addCleanup(manager.stop)
        LoaderSpy.calls.clear()

    def install(self, name):
        path = self.loras / name.replace("\\", "/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test weights")
        self.available[name] = str(path)
        return path

    def save(self, name, value):
        document, revision = self.store.snapshot()
        return self.store.save(name, value, revision, overwrite=name in document["presets"])

    def test_single_registered_node_and_frontend(self):
        self.assertEqual(list(package.NODE_CLASS_MAPPINGS), ["LoraPresetLoader"])
        self.assertEqual(package.WEB_DIRECTORY, "./web")
        self.assertEqual(backend.LoraPresetLoader.RETURN_TYPES, ("MODEL", "CLIP"))

    def test_import_on_portable_build_without_get_user_directory(self):
        # Exercise the complete package import: this used to fail before node registration.
        legacy_folders = types.ModuleType("folder_paths")
        legacy_folders.base_path = str(self.root / "ComfyUI")
        legacy_folders.get_filename_list = lambda _: []
        legacy_folders.get_full_path = lambda *_: None
        legacy_server = types.ModuleType("server")
        legacy_server.PromptServer = types.SimpleNamespace(instance=types.SimpleNamespace(routes=FakeRoutes()))
        with patch.dict(sys.modules, {"folder_paths": legacy_folders, "nodes": fake_nodes,
                                      "server": legacy_server, "aiohttp": fake_aiohttp}):
            spec = importlib.util.spec_from_file_location(
                "lpl_legacy_test", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
            imported = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = imported
            spec.loader.exec_module(imported)
            self.assertIn("LoraPresetLoader", imported.NODE_CLASS_MAPPINGS)
            self.assertIn("Ultra Realism", imported.LoraPresetLoader.INPUT_TYPES()["required"]["preset"][0])
            self.assertEqual(imported.loader.STORE.path,
                             self.root / "ComfyUI" / "user" / "lora_preset_loader" / "presets.json")
            self.assertEqual(len(legacy_server.PromptServer.instance.routes.handlers), 3)

    def test_legacy_directory_fallback_respects_configured_user_directory(self):
        with patch.object(fake_folders, "get_user_directory", None), \
                patch.object(fake_folders, "user_directory", str(self.root / "custom-user"), create=True):
            self.assertEqual(backend.preset_file_path(),
                             self.root / "custom-user" / "lora_preset_loader" / "presets.json")

    def test_legacy_directory_fallback_uses_folder_paths_location_without_base_path(self):
        with patch.object(fake_folders, "get_user_directory", None), \
                patch.object(fake_folders, "__file__", str(self.root / "ComfyUI" / "folder_paths.py"), create=True):
            self.assertEqual(backend.preset_file_path(),
                             self.root / "ComfyUI" / "user" / "lora_preset_loader" / "presets.json")

    def test_defaults_do_not_write_and_empty_starter_is_actionable(self):
        self.assertIn("Ultra Realism", self.store.snapshot()[0]["presets"])
        self.assertFalse(self.store.path.exists())
        self.assertIn("no LoRAs yet", backend.LoraPresetLoader.VALIDATE_INPUTS("Ultra Realism"))

    def test_saves_survive_new_store_and_preserve_previous_backup(self):
        self.save("Style", preset(row()))
        before = self.store.path.read_bytes()
        self.save("Style", preset(row(model=0.95, clip=-0.25)))
        reopened = storage.PresetStore(self.store.path)
        self.assertEqual(reopened.get("Style")["loras"][0]["strength_model"], 0.95)
        self.assertEqual(self.store.path.with_suffix(".json.bak").read_bytes(), before)
        self.assertEqual(list(self.store.path.parent.glob("*.tmp")), [])

    def test_stale_editor_cannot_overwrite_newer_save(self):
        _, revision = self.store.snapshot()
        self.save("First", preset(row()))
        with self.assertRaises(storage.PresetConflict):
            self.store.save("Second", preset(row()), revision)
        self.assertNotIn("Second", self.store.snapshot()[0]["presets"])

    def test_invalid_and_duplicate_json_never_get_overwritten(self):
        self.save("Style", preset(row()))
        for malformed in [b'{broken', b'{"version":1,"presets":{},"presets":{}}']:
            self.store.path.write_bytes(malformed)
            with self.assertRaises(storage.PresetError):
                self.store.save("Other", preset(row()), "stale", True)
            self.assertEqual(self.store.path.read_bytes(), malformed)

    def test_failed_atomic_replace_preserves_original(self):
        self.save("Style", preset(row()))
        original = self.store.path.read_bytes()
        replace = os.replace

        def fail_main(source, destination):
            if Path(destination) == self.store.path:
                raise PermissionError("read only")
            return replace(source, destination)

        with patch.object(storage.os, "replace", fail_main):
            with self.assertRaises(storage.PresetError):
                self.save("Style", preset(row(model=0.9)))
        self.assertEqual(self.store.path.read_bytes(), original)
        self.assertEqual(list(self.store.path.parent.glob("*.tmp")), [])

    def test_numeric_validation_and_valid_negative_or_zero_strengths(self):
        for number in [True, "0.7", None, float("nan"), float("inf"), -101, 101]:
            with self.subTest(number=number), self.assertRaises(storage.PresetError):
                storage.validate_preset(preset(row(model=number)))
        value = storage.validate_preset(preset(row(model=-0.3, clip=0)))
        self.assertEqual(value["loras"][0]["strength_model"], -0.3)

    def test_no_absolute_paths_or_traversal(self):
        for name in ["/etc/passwd", "../bad.safetensors", "sub/../bad", "C:\\test.safetensors", "\\\\server\\file", "sub//file"]:
            with self.subTest(name=name), self.assertRaises(storage.PresetError):
                storage.validate_preset(preset(row(name)))

    def test_loader_chains_model_clip_and_preserves_row_order(self):
        self.install("a.safetensors")
        self.install("b.safetensors")
        self.save("Style", preset(row("b.safetensors", -0.2, 0), row("a.safetensors", 0.8, 0.6)))
        model, clip = backend.LoraPresetLoader().load_preset((), (), "Style")
        self.assertEqual(model, ("b.safetensors", "a.safetensors"))
        self.assertEqual(clip, (("b.safetensors", 0), ("a.safetensors", 0.6)))
        self.assertEqual(LoaderSpy.calls[0][3:], (-0.2, 0))
        self.assertEqual(LoaderSpy.calls[1][0], ("b.safetensors",))
        self.assertEqual(LoaderSpy.calls[1][1], (("b.safetensors", 0),))

    def test_duplicate_lora_rows_are_applied_twice(self):
        self.install("detail.safetensors")
        self.save("Style", preset(row(), row(model=0.1)))
        backend.LoraPresetLoader().load_preset((), (), "Style")
        self.assertEqual(len(LoaderSpy.calls), 2)

    def test_optional_clip_preserves_model_strengths_and_saved_clip_values(self):
        schema = backend.LoraPresetLoader.INPUT_TYPES()
        self.assertNotIn("clip", schema["required"])
        self.assertEqual(schema["optional"]["clip"][0], "CLIP")
        self.install("a.safetensors")
        self.install("b.safetensors")
        self.save("Style", preset(row("b.safetensors", -0.2, 0.75),
                                 row("a.safetensors", 0.8, 0.125)))
        saved = self.store.path.read_bytes()
        node = backend.LoraPresetLoader()
        # ComfyUI omits unconnected optional inputs from these named arguments.
        model, clip = node.load_preset(model=(), preset="Style")
        self.assertEqual(model, ("b.safetensors", "a.safetensors"))
        self.assertIsNone(clip)
        self.assertEqual([call[3:] for call in LoaderSpy.calls], [(-0.2, 0), (0.8, 0)])
        self.assertTrue(all(call[1] is None for call in LoaderSpy.calls))
        self.assertEqual(self.store.path.read_bytes(), saved)
        LoaderSpy.calls.clear()
        # Connecting CLIP later applies the original independent strengths.
        model, clip = node.load_preset(model=(), clip=(), preset="Style")
        self.assertEqual(model, ("b.safetensors", "a.safetensors"))
        self.assertEqual(clip, (("b.safetensors", 0.75), ("a.safetensors", 0.125)))
        self.assertEqual(self.store.path.read_bytes(), saved)

    def test_model_only_ignores_clip_only_rows_but_connected_clip_checks_them(self):
        self.install("a.safetensors")
        self.save("Style", preset(row("a.safetensors", 0.3, 0.4),
                                 row("missing-clip-only.safetensors", 0, 0.6)))
        self.assertIs(backend.LoraPresetLoader.VALIDATE_INPUTS("Style"), True)
        node = backend.LoraPresetLoader()
        self.assertEqual(node.load_preset(model=(), preset="Style"), (("a.safetensors",), None))
        self.assertEqual(len(LoaderSpy.calls), 1)
        LoaderSpy.calls.clear()
        with self.assertRaisesRegex(storage.PresetError, "missing-clip-only"):
            node.load_preset(model=(), clip=(), preset="Style")
        self.assertEqual(LoaderSpy.calls, [])

    def test_model_only_bypass_and_zero_model_strength_pass_through(self):
        model = object()
        node = backend.LoraPresetLoader()
        with patch.object(self.store, "snapshot", side_effect=AssertionError("should not read")):
            result = node.load_preset(model=model, preset=storage.NO_PRESET)
        self.assertIs(result[0], model)
        self.assertIsNone(result[1])
        self.save("CLIP only", preset(row("unused.safetensors", 0, 0.75)))
        result = node.load_preset(model=model, preset="CLIP only")
        self.assertIs(result[0], model)
        self.assertIsNone(result[1])
        self.assertEqual(LoaderSpy.calls, [])

    def test_subfolder_windows_names_resolve_to_native_name(self):
        self.install("portraits\\skin.safetensors")
        self.save("Style", preset(row("portraits/skin.safetensors")))
        backend.LoraPresetLoader().load_preset((), (), "Style")
        self.assertEqual(LoaderSpy.calls[0][2], "portraits\\skin.safetensors")

    def test_all_missing_files_are_reported_before_any_load(self):
        self.install("a.safetensors")
        self.save("Style", preset(row("a.safetensors"), row("missing.safetensors"), row("other.safetensors")))
        with self.assertRaisesRegex(storage.PresetError, "missing.safetensors, other.safetensors"):
            backend.LoraPresetLoader().load_preset((), (), "Style")
        self.assertEqual(LoaderSpy.calls, [])

    def test_disabled_and_zero_rows_do_not_require_files(self):
        self.save("Style", preset(row("absent.safetensors", enabled=False), row("zero.safetensors", 0, 0)))
        model, clip = object(), object()
        result = backend.LoraPresetLoader().load_preset(model, clip, "Style")
        self.assertIs(result[0], model)
        self.assertIs(result[1], clip)
        self.assertEqual(LoaderSpy.calls, [])

    def test_bypass_returns_same_objects_without_reading_config(self):
        model, clip = object(), object()
        with patch.object(self.store, "snapshot", side_effect=AssertionError("should not read")):
            result = backend.LoraPresetLoader().load_preset(model, clip, storage.NO_PRESET)
        self.assertIs(result[0], model)
        self.assertIs(result[1], clip)

    def test_cache_changes_with_strengths_order_and_replaced_weights(self):
        first = self.install("a.safetensors")
        self.install("b.safetensors")
        self.save("Style", preset(row("a.safetensors"), row("b.safetensors")))
        fingerprint = backend.LoraPresetLoader.IS_CHANGED
        before = fingerprint("Style")
        self.assertEqual(before, fingerprint("Style"))
        self.save("Unrelated", preset(row("b.safetensors")))
        self.assertEqual(before, fingerprint("Style"))
        self.save("Style", preset(row("a.safetensors", 0.8), row("b.safetensors")))
        after_strength = fingerprint("Style")
        self.assertNotEqual(before, after_strength)
        self.save("Style", preset(row("b.safetensors"), row("a.safetensors", 0.8)))
        after_order = fingerprint("Style")
        self.assertNotEqual(after_strength, after_order)
        first.write_bytes(b"new test weights of a different size")
        self.assertNotEqual(after_order, fingerprint("Style"))
        first.unlink()
        self.assertTrue(math.isnan(fingerprint("Style")))

    def test_deleted_preset_errors_instead_of_silently_bypassing(self):
        self.save("Style", preset(row()))
        _, revision = self.store.snapshot()
        self.store.delete("Style", revision)
        self.assertIn("does not exist", backend.LoraPresetLoader.VALIDATE_INPUTS("Style"))

    def test_api_save_list_delete_and_conflict(self):
        self.install("detail.safetensors")
        initial = asyncio.run(routes.get_presets(Request(None)))["body"]
        payload = {"name": "Style", "preset": preset(row()), "revision": initial["revision"]}
        saved = asyncio.run(routes.save_preset(Request(payload)))
        self.assertEqual(saved["status"], 200)
        self.assertEqual(saved["body"]["loras"], ["detail.safetensors"])
        self.assertIn("Style", saved["body"]["presets"])
        self.assertEqual(asyncio.run(routes.save_preset(Request(payload)))["status"], 409)
        deleted = asyncio.run(routes.delete_preset(Request({"name": "Style", "revision": saved["body"]["revision"]})))
        self.assertEqual(deleted["status"], 200)
        self.assertNotIn("Style", deleted["body"]["presets"])

    def test_api_invalid_or_missing_lora_does_not_mutate_storage(self):
        initial = self.store.snapshot()
        for body, content_type in [(None, "application/json"), ([], "application/json"),
                                   ({}, "text/plain"),
                                   ({"name": "Style", "preset": preset(row("missing")),
                                     "revision": initial[1]}, "application/json")]:
            result = asyncio.run(routes.save_preset(Request(body, content_type)))
            self.assertEqual(result["status"], 400)
            self.assertEqual(self.store.snapshot(), initial)


if __name__ == "__main__":
    unittest.main()
