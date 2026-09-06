import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const CLASS_NAME = "LoraPresetLoader";
const ROOT = "/lora-preset-loader/presets";
const nodes = new Set();
let cached = null;
let pendingRefresh = null;
let editor = null;

function element(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
}

function button(text, action, className = "") {
    const el = element("button", className, text);
    el.type = "button";
    el.addEventListener("click", action);
    return el;
}

function field(text, input) {
    const label = element("label", "lpl-field");
    label.append(element("span", "lpl-label", text), input);
    return label;
}

function hasPreset(data, name) {
    return Object.hasOwn(data.presets, name);
}

async function request(path = "", body) {
    const response = await api.fetchApi(ROOT + path, body === undefined ? { cache: "no-store" } : {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    let data;
    try { data = await response.json(); }
    catch { throw new Error(`The preset server returned HTTP ${response.status}. Check the ComfyUI console.`); }
    if (!response.ok) throw new Error(data.error || `Request failed (HTTP ${response.status}).`);
    return data;
}

function syncNode(node, selected) {
    if (!cached) return;
    const widget = node.widgets?.find((item) => item.name === "preset");
    if (!widget) return;
    const names = Object.keys(cached.presets).sort((a, b) => a.localeCompare(b));
    const value = selected ?? widget.value ?? cached.no_preset;
    const choices = [cached.no_preset, ...names];
    // Keep missing names visible: a stale workflow must report an error, not silently bypass.
    if (!choices.includes(value)) choices.push(value);
    widget.options ??= {};
    widget.options.values = choices;
    const changed = widget.value !== value;
    widget.value = value;
    if (changed) {
        widget.callback?.(value);
        node.graph?.change?.();
    }
    node.setDirtyCanvas?.(true, true);
}

function updateNodes(data) {
    cached = data;
    for (const reference of nodes) {
        const node = reference.deref();
        if (node) syncNode(node);
        else nodes.delete(reference);
    }
}

async function refresh() {
    if (!pendingRefresh) {
        pendingRefresh = request().then(updateNodes).finally(() => { pendingRefresh = null; });
    }
    return pendingRefresh;
}

function ensureStyles() {
    if (document.getElementById("lpl-styles")) return;
    const link = element("link");
    link.id = "lpl-styles";
    link.rel = "stylesheet";
    link.href = new URL("./lora_presets.css", import.meta.url).href;
    document.head.append(link);
}

async function openEditor(node) {
    if (editor) { editor.focus(); return; }
    ensureStyles();
    const dialog = element("dialog", "lpl-dialog");
    editor = dialog;
    dialog.setAttribute("aria-labelledby", "lpl-title");
    const form = element("form", "lpl-form");
    const header = element("div", "lpl-header");
    const heading = element("div");
    const title = element("h2", "", "LoRA presets");
    title.id = "lpl-title";
    heading.append(title, element("p", "lpl-muted", "Save a style once. Choose it whenever you need it."));
    const close = button("Close", () => closeEditor());
    header.append(heading, close);

    const toolbar = element("div", "lpl-toolbar");
    const presetSelect = element("select");
    presetSelect.setAttribute("aria-label", "Saved preset");
    const newButton = button("New preset", () => { if (canDiscard()) loadPreset(null); });
    const reloadButton = button("Reload", () => reload());
    toolbar.append(field("Saved preset", presetSelect), newButton, reloadButton);

    const name = element("input");
    name.type = "text";
    name.required = true;
    name.maxLength = 120;
    name.placeholder = "For example: Ultra Realism";
    const rows = element("div", "lpl-rows");
    const add = button("+ Add LoRA", () => { readRows(); draft.loras.push(defaultRow()); renderRows(); markDirty(); });
    const notes = element("textarea");
    notes.rows = 2;
    notes.maxLength = 8000;
    notes.placeholder = "Optional: intended checkpoint, trigger words, or reminders. Notes do not change your prompt.";
    const status = element("p", "lpl-status", "Loading presets…");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    const footer = element("div", "lpl-footer");
    const removePreset = button("Delete preset", () => deletePreset(), "lpl-danger");
    const save = element("button", "lpl-primary", "Save & use preset");
    save.type = "submit";
    footer.append(removePreset, element("span", "lpl-spacer"), save);
    form.append(header, toolbar, field("Preset name", name),
        element("p", "lpl-muted", "Adjust each LoRA separately. Use its − / + controls for 0.1 steps, or click the number to enter an exact strength such as 0.75."),
        element("p", "lpl-muted", "CLIP strengths apply only when this node's CLIP input is connected. They stay saved when you use MODEL only."),
        rows, add, field("Notes", notes), status, footer);
    dialog.append(form);
    document.body.append(dialog);

    let data = null;
    let loadedName = null;
    let draft = { loras: [], notes: "" };
    let controls = [];
    let dirty = false;
    let busy = false;

    function message(text, error = false) {
        status.textContent = text;
        status.classList.toggle("lpl-error", error);
    }

    function markDirty() { dirty = true; message("Unsaved changes"); }

    function canDiscard() {
        return !busy && (!dirty || window.confirm("Discard the unsaved changes to this preset?"));
    }

    function closeEditor() { if (canDiscard()) dialog.close(); }

    function setBusy(value) {
        busy = value;
        for (const control of form.querySelectorAll("input, select, textarea, button")) control.disabled = value;
        if (!value) {
            if (!data) {
                for (const control of form.querySelectorAll("input, select, textarea, button")) control.disabled = true;
                close.disabled = false;
                reloadButton.disabled = false;
                return;
            }
            removePreset.disabled = loadedName === null;
            add.disabled = !data?.loras.length;
            const rowActions = rows.querySelectorAll(".lpl-row-actions");
            rowActions.forEach((actions, index) => {
                actions.children[0].disabled = index === 0;
                actions.children[1].disabled = index === rowActions.length - 1;
            });
        }
    }

    function defaultRow() {
        return { lora_name: data.loras[0] || "", strength_model: 1, strength_clip: 1, enabled: true };
    }

    function fillSelect() {
        presetSelect.replaceChildren();
        const blank = element("option", "", "New preset…");
        blank.value = "";
        presetSelect.append(blank);
        for (const key of Object.keys(data.presets).sort((a, b) => a.localeCompare(b))) {
            const option = element("option", "", key);
            option.value = key;
            presetSelect.append(option);
        }
        presetSelect.value = loadedName ?? "";
    }

    function loadPreset(key) {
        loadedName = key && hasPreset(data, key) ? key : null;
        draft = loadedName ? JSON.parse(JSON.stringify(data.presets[loadedName])) : { loras: [], notes: "" };
        name.value = loadedName ?? "";
        notes.value = draft.notes ?? "";
        dirty = false;
        fillSelect();
        renderRows();
        removePreset.disabled = loadedName === null;
        add.disabled = data.loras.length === 0;
        save.disabled = false;
        message(data.loras.length ? "Changing the name saves a separate preset. Saving an existing name updates that preset."
            : "No installed LoRAs found. Add files to your ComfyUI LoRA folder, refresh ComfyUI's model list, then Reload here.");
    }

    function readRows() {
        draft.loras = controls.map((row) => ({
            lora_name: row.file.value,
            strength_model: row.model.valueAsNumber,
            strength_clip: row.clip.valueAsNumber,
            enabled: row.enabled.checked,
        }));
    }

    function move(index, offset) {
        const target = index + offset;
        if (target < 0 || target >= draft.loras.length) return;
        readRows();
        [draft.loras[index], draft.loras[target]] = [draft.loras[target], draft.loras[index]];
        renderRows();
        markDirty();
    }

    function renderRows() {
        rows.replaceChildren();
        controls = [];
        if (!draft.loras.length) {
            rows.append(element("p", "lpl-empty", "Add the LoRAs you want this style to use, then set their strengths."));
        }
        draft.loras.forEach((value, index) => {
            const row = element("div", "lpl-row");
            const enabled = element("input");
            enabled.type = "checkbox";
            enabled.checked = value.enabled;
            enabled.setAttribute("aria-label", `Enable LoRA ${index + 1}`);
            const toggle = field("On", enabled);
            toggle.classList.add("lpl-toggle");
            const file = element("select");
            file.required = true;
            file.setAttribute("aria-label", `LoRA ${index + 1} file`);
            if (!data.loras.includes(value.lora_name)) {
                const missing = element("option", "", `Missing: ${value.lora_name}`);
                missing.value = value.lora_name;
                file.append(missing);
            }
            for (const filename of data.loras) {
                const option = element("option", "", filename);
                option.value = filename;
                file.append(option);
            }
            file.value = value.lora_name;
            file.title = value.lora_name;
            const fileField = field(`LoRA ${index + 1}`, file);
            fileField.classList.add("lpl-file");
            const strength = (label, number) => {
                const input = element("input");
                input.type = "number";
                input.step = "any";
                input.inputMode = "decimal";
                input.min = "-100";
                input.max = "100";
                input.required = true;
                // Match the reference's 1.00 display without rounding away
                // more precise saved values such as 0.125.
                const display = (value) => {
                    const text = String(value);
                    if (/e/i.test(text)) return text;
                    const [whole, fraction = ""] = text.split(".");
                    return `${whole}.${fraction.padEnd(2, "0")}`;
                };
                input.value = display(number);
                input.setAttribute("aria-label", `LoRA ${index + 1} ${label.toLowerCase()} strength`);
                input.title = "Click to enter an exact strength. The − / + buttons adjust by 0.1.";
                const adjust = (direction) => {
                    const current = Number.isFinite(input.valueAsNumber) ? input.valueAsNumber : 0;
                    const next = Math.max(-100, Math.min(100,
                        Math.round((current + direction * 0.1) * 1e10) / 1e10));
                    input.value = display(next);
                    input.dispatchEvent(new Event("input", { bubbles: true }));
                };
                const group = element("div", "lpl-strength");
                const decrease = button("−", () => adjust(-1));
                const increase = button("+", () => adjust(1));
                decrease.setAttribute("aria-label", `Decrease LoRA ${index + 1} ${label.toLowerCase()} strength by 0.1`);
                increase.setAttribute("aria-label", `Increase LoRA ${index + 1} ${label.toLowerCase()} strength by 0.1`);
                input.addEventListener("keydown", (event) => {
                    if (event.key === "ArrowUp" || event.key === "ArrowDown") {
                        event.preventDefault();
                        adjust(event.key === "ArrowUp" ? 1 : -1);
                    }
                });
                input.addEventListener("blur", () => {
                    if (Number.isFinite(input.valueAsNumber)) input.value = display(input.valueAsNumber);
                });
                group.append(decrease, input, increase);
                return { input, field: field(`${label} strength`, group) };
            };
            const model = strength("Model", value.strength_model);
            const clip = strength("CLIP", value.strength_clip);
            const actions = element("div", "lpl-row-actions");
            const up = button("↑", () => move(index, -1));
            const down = button("↓", () => move(index, 1));
            const remove = button("×", () => {
                readRows(); draft.loras.splice(index, 1); renderRows(); markDirty();
            });
            up.setAttribute("aria-label", `Move LoRA ${index + 1} up`);
            down.setAttribute("aria-label", `Move LoRA ${index + 1} down`);
            remove.setAttribute("aria-label", `Remove LoRA ${index + 1}`);
            up.disabled = index === 0;
            down.disabled = index === draft.loras.length - 1;
            actions.append(up, down, remove);
            row.append(toggle, fileField, model.field, clip.field, actions);
            const updateRow = () => {
                row.classList.toggle("lpl-row-off", !enabled.checked);
                row.classList.toggle("lpl-row-missing", enabled.checked && !data.loras.includes(file.value));
                file.title = file.value;
            };
            row.addEventListener("input", () => { updateRow(); markDirty(); });
            row.addEventListener("change", updateRow);
            updateRow();
            controls.push({ file, model: model.input, clip: clip.input, enabled });
            rows.append(row);
        });
    }

    async function reload(initial = false) {
        if (!initial && !canDiscard()) return;
        setBusy(true);
        message("Loading presets…");
        try {
            data = await request();
            updateNodes(data);
            const selected = initial ? node.widgets?.find((w) => w.name === "preset")?.value : loadedName;
            loadPreset(selected && hasPreset(data, selected) ? selected : Object.keys(data.presets)[0] ?? null);
        } catch (error) { message(error.message, true); }
        finally { setBusy(false); }
    }

    async function deletePreset() {
        if (!loadedName || busy) return;
        if (!window.confirm(`Delete the saved preset “${loadedName}”? Workflows using it will need another preset. Unsaved edits will be discarded.`)) return;
        setBusy(true);
        try {
            data = await request("/delete", { name: loadedName, revision: data.revision });
            updateNodes(data);
            loadPreset(Object.keys(data.presets)[0] ?? null);
            message("Preset deleted.");
        } catch (error) { message(error.message, true); }
        finally { setBusy(false); }
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (busy || !data || !form.reportValidity()) return;
        readRows();
        const key = name.value.trim();
        if (!key) { message("Give this preset a name.", true); name.focus(); return; }
        const overwrite = hasPreset(data, key);
        if (overwrite && key !== loadedName && !window.confirm(`Replace the existing preset “${key}”?`)) return;
        setBusy(true);
        message("Saving preset…");
        try {
            data = await request("/save", {
                name: key, preset: { loras: draft.loras, notes: notes.value },
                revision: data.revision, overwrite,
            });
            updateNodes(data);
            syncNode(node, key);
            loadPreset(key);
            message(`Saved “${key}” and selected it on this node.`);
        } catch (error) { message(error.message, true); }
        finally { setBusy(false); }
    });
    presetSelect.addEventListener("change", () => {
        if (canDiscard()) loadPreset(presetSelect.value || null);
        else presetSelect.value = loadedName ?? "";
    });
    name.addEventListener("input", markDirty);
    notes.addEventListener("input", markDirty);
    dialog.addEventListener("cancel", (event) => { event.preventDefault(); closeEditor(); });
    dialog.addEventListener("close", () => { dialog.remove(); editor = null; });
    // Prevent canvas shortcuts from interpreting typing inside the dialog.
    dialog.addEventListener("keydown", (event) => event.stopPropagation());
    dialog.showModal();
    await reload(true);
}

app.registerExtension({
    name: "comfy.lora-preset-loader",
    nodeCreated(node) {
        if (node.comfyClass !== CLASS_NAME) return;
        nodes.add(new WeakRef(node));
        node.addWidget("button", "Edit presets", null, () => {
            openEditor(node).catch((error) => { console.error("LoRA Preset Loader:", error); });
        }, { serialize: false });
        const size = node.computeSize();
        node.setSize([Math.max(300, size[0], node.size?.[0] || 0), Math.max(size[1], node.size?.[1] || 0)]);
        syncNode(node);
    },
    loadedGraphNode(node) {
        if (node.comfyClass === CLASS_NAME) syncNode(node);
    },
    async setup() {
        try { await refresh(); }
        catch (error) { console.warn("LoRA Preset Loader:", error.message); }
    },
    async afterConfigureGraph() {
        try { await refresh(); }
        catch (error) { console.warn("LoRA Preset Loader:", error.message); }
    },
});
