#pragma once
#include <cstdint>
#include <string>
#include <vector>

// ── Transform (matches Python timeline's transform dict) ──────────────────────
struct ClipTransform {
    float x         = 0.f;
    float y         = 0.f;
    float scaleX    = 1.f;
    float scaleY    = 1.f;
    float rotation  = 0.f;  // degrees
    float anchorX   = 0.f;
    float anchorY   = 0.f;
};

// ── Per-effect parameters ─────────────────────────────────────────────────────
struct EffectParam {
    std::string typeId;         // e.g. "fade:blur", "fade:glow"
    // Uniform values keyed by param id — flat float array (vec4 = 4 floats)
    struct UniformValue {
        std::string id;
        std::vector<float> values; // 1=float, 2=vec2, 4=vec4
    };
    std::vector<UniformValue> uniforms;
};

// ── Single clip to composite at a given frame ─────────────────────────────────
struct ClipDesc {
    std::string  clipId;
    std::string  file;          // absolute path to media file
    int64_t      sourceFrame;   // which frame to decode from the source
    float        opacity    = 1.f;
    int          blendMode  = 0;  // 0=normal, 1=add, 2=multiply, ...
    ClipTransform transform;
    std::vector<EffectParam> effects;

    // Clip type
    enum class Type { Video, Image, Solid, Shape } type = Type::Video;

    // For Solid clips
    float solidR = 0.5f, solidG = 0.5f, solidB = 0.5f, solidA = 1.f;

    // Raw RGBA pixel data — supplied by NAPI bridge from Python's frame cache.
    // Points into a JS Buffer/SharedArrayBuffer; valid only during renderFrame().
    const uint8_t* rawRGBA     = nullptr;
    size_t         rawRGBASize = 0;
};

// ── Full frame descriptor sent from Python /render/frame/{n} ──────────────────
struct FrameDescriptor {
    int64_t frame     = 0;
    float   fps       = 30.f;
    int     width     = 1920;
    int     height    = 1080;
    std::vector<ClipDesc> clips;  // bottom-to-top order

    bool valid = false;
};

// ── JSON → FrameDescriptor (uses nlohmann/json) ───────────────────────────────
#include <nlohmann/json.hpp>

inline FrameDescriptor parseFrameDescriptor(const std::string& jsonStr) {
    FrameDescriptor fd;
    try {
        auto j = nlohmann::json::parse(jsonStr);
        fd.frame  = j.value("frame",  int64_t{0});
        fd.fps    = j.value("fps",    30.f);
        fd.width  = j.value("width",  1920);
        fd.height = j.value("height", 1080);

        for (const auto& c : j.value("clips", nlohmann::json::array())) {
            ClipDesc cd;
            cd.clipId      = c.value("clipId",      std::string{});
            cd.file        = c.value("file",        std::string{});
            cd.sourceFrame = c.value("sourceFrame", int64_t{0});
            cd.opacity     = c.value("opacity",     1.f);
            cd.blendMode   = c.value("blendMode",   0);

            if (c.contains("transform")) {
                auto& t = c["transform"];
                cd.transform.x        = t.value("x",        0.f);
                cd.transform.y        = t.value("y",        0.f);
                cd.transform.scaleX   = t.value("scaleX",   1.f);
                cd.transform.scaleY   = t.value("scaleY",   1.f);
                cd.transform.rotation = t.value("rotation", 0.f);
                cd.transform.anchorX  = t.value("anchorX",  0.f);
                cd.transform.anchorY  = t.value("anchorY",  0.f);
            }

            std::string typeStr = c.value("type", std::string{"video"});
            if      (typeStr == "image")  cd.type = ClipDesc::Type::Image;
            else if (typeStr == "solid")  cd.type = ClipDesc::Type::Solid;
            else if (typeStr == "shape")  cd.type = ClipDesc::Type::Shape;
            else                          cd.type = ClipDesc::Type::Video;

            if (cd.type == ClipDesc::Type::Solid && c.contains("color")) {
                auto& col = c["color"];
                cd.solidR = col.value("r", 0.5f);
                cd.solidG = col.value("g", 0.5f);
                cd.solidB = col.value("b", 0.5f);
                cd.solidA = col.value("a", 1.0f);
            }

            for (const auto& e : c.value("effects", nlohmann::json::array())) {
                EffectParam ep;
                ep.typeId = e.value("typeId", std::string{});
                for (const auto& u : e.value("uniforms", nlohmann::json::array())) {
                    EffectParam::UniformValue uv;
                    uv.id = u.value("id", std::string{});
                    uv.values = u.value("values", std::vector<float>{});
                    ep.uniforms.push_back(std::move(uv));
                }
                cd.effects.push_back(std::move(ep));
            }
            fd.clips.push_back(std::move(cd));
        }
        fd.valid = true;
    } catch (const std::exception& e) {
        std::cerr << "[FrameDescriptor] Parse error: " << e.what() << "\n";
        fd.valid = false;
    }
    return fd;
}
