#include "EffectRegistry.hpp"
#include "EffectInstance.hpp"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>

// Minimal JSON helpers — replaces Qt's QJsonDocument/QJsonObject
// Uses nlohmann/json if available, otherwise simple hand-rolled parser.
// We include a single-header nlohmann/json.hpp in deps/include.
#include <nlohmann/json.hpp>
using json = nlohmann::json;

#define LOG_INFO(m)  do { std::cout  << "[EffectRegistry] " << m << "\n"; } while(0)
#define LOG_WARN(m)  do { std::cout  << "[EffectRegistry][WARN] " << m << "\n"; } while(0)
#define LOG_ERROR(m) do { std::cerr  << "[EffectRegistry][ERR] "  << m << "\n"; } while(0)

// ── Singleton ─────────────────────────────────────────────────────────────────

EffectRegistry& EffectRegistry::instance() {
    static EffectRegistry s;
    return s;
}

// ── Directory scan ─────────────────────────────────────────────────────────────

void EffectRegistry::scanEffectsDir(const std::string& path) {
    namespace fs = std::filesystem;
    if (!fs::exists(path)) {
        LOG_WARN("Effects directory not found: " + path);
        return;
    }
    for (const auto& entry : fs::directory_iterator(path)) {
        if (entry.path().extension() == ".json")
            loadEffect(entry.path().string());
    }
    LOG_INFO("Loaded " + std::to_string(m_defs.size()) + " effects from " + path);
}

// ── Load single effect JSON + SkSL ───────────────────────────────────────────

void EffectRegistry::loadEffect(const std::string& jsonPath) {
    // Read JSON file
    std::ifstream f(jsonPath);
    if (!f.is_open()) { LOG_ERROR("Cannot open: " + jsonPath); return; }
    json obj;
    try { f >> obj; } catch (const std::exception& e) {
        LOG_ERROR("JSON parse error in " + jsonPath + ": " + e.what()); return;
    }

    EffectDef def;
    def.typeId       = obj.value("typeId",       std::string{});
    def.displayName  = obj.value("displayName",  std::string{});
    def.category     = obj.value("category",     std::string{"Uncategorized"});
    def.internal     = obj.value("internal",     false);

    if (def.typeId.empty()) { LOG_ERROR("Missing typeId in " + jsonPath); return; }

    // Load SkSL shader — kept as-is (Skia's GPU backend compiles SkSL natively)
    std::string shaderFile = obj.value("shader", std::string{});
    if (!shaderFile.empty()) {
        namespace fs = std::filesystem;
        fs::path shaderPath = fs::path(jsonPath).parent_path() / shaderFile;
        std::ifstream sf(shaderPath);
        if (!sf.is_open()) { LOG_ERROR("Cannot open SkSL: " + shaderPath.string()); return; }
        std::ostringstream ss; ss << sf.rdbuf();
        std::string skslSrc = ss.str();

        auto [effect, err] = SkRuntimeEffect::MakeForShader(SkString(skslSrc.c_str()));
        if (!effect) {
            LOG_ERROR("SkSL compile error in " + shaderFile + ": " + std::string(err.c_str()));
            return;
        }
        def.compiled = effect;
    }

    // Parse params
    if (obj.contains("params") && obj["params"].is_array()) {
        for (const auto& p : obj["params"]) {
            ParamDef pd;
            pd.id          = p.value("id",          std::string{});
            pd.displayName = p.value("displayName",  std::string{});
            pd.uiType      = parseParamType(p.value("type", std::string{"FloatSlider"}));
            pd.hint        = parseHint(p.value("hint", std::string{"Default"}));

            if (pd.uiType == ParamType::Vec2Input) {
                auto def2 = p.value("default", std::vector<float>{0,0});
                auto min2 = p.value("min",     std::vector<float>{0,0});
                auto max2 = p.value("max",     std::vector<float>{1,1});
                pd.defaultVal = glm::vec2(def2[0], def2[1]);
                pd.minVal     = glm::vec2(min2[0], min2[1]);
                pd.maxVal     = glm::vec2(max2[0], max2[1]);
            } else if (pd.uiType == ParamType::Vec4Input) {
                auto def4 = p.value("default", std::vector<float>{0,0,0,1});
                auto min4 = p.value("min",     std::vector<float>{0,0,0,0});
                auto max4 = p.value("max",     std::vector<float>{1,1,1,1});
                pd.defaultVal = glm::vec4(def4[0], def4[1], def4[2], def4[3]);
                pd.minVal     = glm::vec4(min4[0], min4[1], min4[2], min4[3]);
                pd.maxVal     = glm::vec4(max4[0], max4[1], max4[2], max4[3]);
            } else if (pd.uiType == ParamType::IntSlider) {
                pd.defaultVal = p.value("default", 0);
                pd.minVal     = p.value("min",     0);
                pd.maxVal     = p.value("max",     100);
            } else {
                pd.defaultVal = static_cast<float>(p.value("default", 0.0));
                pd.minVal     = static_cast<float>(p.value("min",     0.0));
                pd.maxVal     = static_cast<float>(p.value("max",     1.0));
            }
            def.params.push_back(std::move(pd));
        }
    }

    LOG_INFO("Loaded effect: " + def.displayName + " (" + def.typeId + ")");
    m_defs[def.typeId] = std::move(def);
}

// ── Type parsers ──────────────────────────────────────────────────────────────

ParamType EffectRegistry::parseParamType(const std::string& str) {
    if (str == "FloatSlider") return ParamType::FloatSlider;
    if (str == "IntSlider")   return ParamType::IntSlider;
    if (str == "ToggleBool")  return ParamType::ToggleBool;
    if (str == "Vec2Input")   return ParamType::Vec2Input;
    if (str == "Vec4Input")   return ParamType::Vec4Input;
    if (str == "comboBox")    return ParamType::comboBox;
    return ParamType::FloatSlider;
}

ParamDisplayHint EffectRegistry::parseHint(const std::string& str) {
    if (str == "Color")      return ParamDisplayHint::Color;
    if (str == "Vec4Value")  return ParamDisplayHint::Vec4Value;
    if (str == "Vec2Value")  return ParamDisplayHint::Vec2Value;
    if (str == "FloatValue") return ParamDisplayHint::FloatValue;
    if (str == "IntValue")   return ParamDisplayHint::IntValue;
    return ParamDisplayHint::Default;
}

// ── Queries ───────────────────────────────────────────────────────────────────

const EffectDef* EffectRegistry::getDef(const std::string& typeId) const {
    auto it = m_defs.find(typeId);
    return (it != m_defs.end()) ? &it->second : nullptr;
}

std::vector<const EffectDef*> EffectRegistry::getAllDefs() const {
    std::vector<const EffectDef*> result;
    result.reserve(m_defs.size());
    for (const auto& [id, def] : m_defs)
        if (!def.internal) result.push_back(&def);
    return result;
}

std::unique_ptr<EffectInstance> EffectRegistry::create(const std::string& typeId,
                                                        AnimationEngine& engine) {
    auto* def = getDef(typeId);
    if (!def) { LOG_ERROR("Unknown effect type: " + typeId); return nullptr; }
    return std::make_unique<EffectInstance>(*def, engine);
}
