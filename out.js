"use strict";
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// temp.tsx
var temp_exports = {};
__export(temp_exports, {
  default: () => BrushToolPanel
});
module.exports = __toCommonJS(temp_exports);
var import_jsx_runtime = require("react/jsx-runtime");
var useTool = () => ({ brushColor: [1, 1, 1, 1], setBrushColor: () => {
}, brushSize: 10, setBrushSize: () => {
} });
var PRESET_COLORS = [
  // Grayscale
  "#ffffff",
  "#e0e0e0",
  "#c0c0c0",
  "#808080",
  "#404040",
  "#000000",
  // Reds & Pinks
  "#ff0000",
  "#ff4d4d",
  "#ff9999",
  "#ff00ff",
  "#ff66b2",
  "#ffb3d9",
  // Oranges & Yellows
  "#ffa500",
  "#ffc04d",
  "#ffff00",
  "#ffff80",
  "#8b4513",
  "#d2b48c",
  // Greens
  "#00ff00",
  "#4dff4d",
  "#008000",
  "#006400",
  "#32cd32",
  "#98fb98",
  // Cyans & Blues
  "#00ffff",
  "#80ffff",
  "#0000ff",
  "#4d4dff",
  "#00008b",
  "#add8e6",
  // Purples
  "#800080",
  "#b366ff",
  "#4b0082",
  "#9932cc",
  "#da70d6",
  "#e6e6fa"
];
function toHex(rgba) {
  const [r, g, b] = rgba.map((v) => Math.round(v * 255).toString(16).padStart(2, "0"));
  return "#" + r + g + b;
}
function fromHex(hex, alpha = 1) {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  return [r, g, b, alpha];
}
function BrushToolPanel() {
  const { brushColor, setBrushColor, brushSize, setBrushSize } = useTool();
  const hexValue = toHex(brushColor);
  const opacity = brushColor[3];
  const handleColorChange = (hex) => {
    setBrushColor(fromHex(hex, opacity));
  };
  const handleOpacityChange = (newOpacity) => {
    const [r, g, b] = brushColor;
    setBrushColor([r, g, b, newOpacity]);
  };
  const handleHexInputChange = (e) => {
    let val = e.target.value;
    if (!val.startsWith("#")) val = "#" + val;
    if (/^#[0-9A-Fa-f]{6}$/.test(val)) {
      handleColorChange(val);
    }
  };
  return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "tp-panel", children: [
    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "tp-header", children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "tp-icon", children: "??" }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "tp-title", children: "Brush Tool" })
    ] }),
    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", { className: "tp-section", children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", { className: "tp-section-title", children: "Color" }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "tp-row", style: { gap: "8px", marginBottom: "12px" }, children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
          "input",
          {
            type: "color",
            value: hexValue,
            onChange: (e) => handleColorChange(e.target.value),
            title: "Custom Color Picker",
            style: { width: "28px", height: "24px", cursor: "pointer", padding: 0, border: "none", background: "transparent" }
          }
        ),
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
          "input",
          {
            type: "text",
            className: "tp-input",
            value: hexValue.toUpperCase(),
            onChange: handleHexInputChange,
            style: { width: "80px", textTransform: "uppercase" }
          }
        )
      ] }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "tp-row", children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("label", { className: "tp-label", children: "Presets" }) }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { style: { display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: "4px", marginBottom: "16px", padding: "0 12px" }, children: PRESET_COLORS.map((color) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
        "div",
        {
          onClick: () => handleColorChange(color),
          style: {
            width: "100%",
            aspectRatio: "1/1",
            backgroundColor: color,
            cursor: "pointer",
            border: hexValue.toLowerCase() === color ? "2px solid #fff" : "1px solid rgba(255,255,255,0.2)",
            borderRadius: "2px",
            boxSizing: "border-box"
          },
          title: color
        },
        color
      )) })
    ] }),
    /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", { className: "tp-section", children: [
      /* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", { className: "tp-section-title", children: "Settings" }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "tp-row", children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)("label", { className: "tp-label", children: "Opacity" }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
          "input",
          {
            type: "range",
            className: "tp-range",
            min: 0,
            max: 1,
            step: 0.01,
            value: opacity,
            onChange: (e) => handleOpacityChange(parseFloat(e.target.value))
          }
        ),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "tp-badge", children: [
          Math.round(opacity * 100),
          "%"
        ] })
      ] }),
      /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { className: "tp-row", children: [
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)("label", { className: "tp-label", children: "Size" }),
        /* @__PURE__ */ (0, import_jsx_runtime.jsx)(
          "input",
          {
            type: "range",
            className: "tp-range",
            min: 1,
            max: 100,
            step: 1,
            value: brushSize,
            onChange: (e) => setBrushSize(parseInt(e.target.value))
          }
        ),
        /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { className: "tp-badge", children: [
          brushSize,
          "px"
        ] })
      ] })
    ] })
  ] });
}
