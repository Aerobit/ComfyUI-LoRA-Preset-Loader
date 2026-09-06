// Lifecycle checks in Node.js; these do not render the editor or require a browser.
// Run: node --experimental-vm-modules tests/test_frontend.mjs
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import vm from "node:vm";

const source = await fs.readFile(new URL("../web/lora_presets.js", import.meta.url), "utf8");
let extension;
let response = {
    presets: { "Ultra Realism": { loras: [], notes: "" } },
    no_preset: "(No preset — bypass)", revision: "one", loras: [],
};
const warnings = [];
const context = vm.createContext({
    console: { warn: (...args) => warnings.push(args), error: (...args) => warnings.push(args) },
    URL, WeakRef,
});
const appModule = new vm.SyntheticModule(["app"], function () {
    this.setExport("app", { registerExtension: (value) => { extension = value; } });
}, { context });
const apiModule = new vm.SyntheticModule(["api"], function () {
    this.setExport("api", {
        fetchApi: async () => ({ ok: !response.error, status: response.error ? 400 : 200,
                                json: async () => response }),
    });
}, { context });
const module = new vm.SourceTextModule(source, { context });
await module.link((specifier) => specifier.endsWith("/app.js") ? appModule : apiModule);
await module.evaluate();

function fakeNode(selected, comfyClass = "LoraPresetLoader") {
    return {
        comfyClass, size: [260, 80], graph: { change() {} },
        widgets: [{ name: "preset", value: selected, options: { values: [] } }],
        addWidget(type, name, value, callback, options) {
            this.widgets.push({ type, name, value, callback, options });
        },
        computeSize: () => [260, 106],
        setSize(value) { this.size = value; },
        setDirtyCanvas() {},
    };
}

const existing = fakeNode("Ultra Realism");
const unrelated = fakeNode("Other", "OtherNode");
extension.nodeCreated(existing);
extension.nodeCreated(unrelated);
assert.equal(existing.widgets[1].name, "Edit presets");
assert.equal(existing.widgets[1].options.serialize, false);
assert.equal(unrelated.widgets.length, 1);
await extension.setup();
assert.deepEqual(Array.from(existing.widgets[0].options.values), [response.no_preset, "Ultra Realism"]);
assert.equal(existing.widgets[0].value, "Ultra Realism");
console.log("PASS: registers an unserialized editor button on the intended node only");

response = { ...response, presets: { ...response.presets, "Cinematic": { loras: [], notes: "" } } };
await extension.afterConfigureGraph();
assert.ok(existing.widgets[0].options.values.includes("Cinematic"));
assert.equal(existing.widgets[0].value, "Ultra Realism");
const newNode = fakeNode(response.no_preset);
extension.nodeCreated(newNode);
assert.ok(newNode.widgets[0].options.values.includes("Cinematic"));
console.log("PASS: refreshes choices on existing and new nodes without changing saved selections");

response = { ...response, presets: { "Cinematic": { loras: [], notes: "" } } };
await extension.afterConfigureGraph();
assert.equal(existing.widgets[0].value, "Ultra Realism");
assert.ok(existing.widgets[0].options.values.includes("Ultra Realism"));
assert.ok(!newNode.widgets[0].options.values.includes("Ultra Realism"));
console.log("PASS: preserves a deleted preset selection so execution can report it instead of bypassing");

response = { error: "Invalid preset file" };
await extension.afterConfigureGraph();
assert.equal(existing.widgets[0].value, "Ultra Realism");
assert.equal(warnings.length, 1);
assert.match(warnings[0].join(" "), /Invalid preset file/);
console.log("PASS: a failed refresh preserves the workflow and reports the error");
