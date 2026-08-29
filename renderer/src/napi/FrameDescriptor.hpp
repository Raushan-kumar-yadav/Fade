#pragma once
#include <cstdint>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

struct FrameDescriptor;

struct ClipTransform {
  float x = 0.f;
  float y = 0.f;
  float scaleX = 1.f;
  float scaleY = 1.f;
  float rotation = 0.f;
  float anchorX = 0.f;
  float anchorY = 0.f;
};

struct EffectParam {
  std::string typeId;
  struct UniformValue {
    std::string id;
    std::vector<float> values;
  };
  std::vector<UniformValue> uniforms;
};

struct ClipDesc {
  std::string clipId;
  std::string file;
  int64_t sourceFrame = 0;
  float opacity = 1.f;
  int blendMode = 0;
  ClipTransform transform;
  std::vector<EffectParam> effects;

  enum class Type {
    Video,
    Image,
    Solid,
    Shape,
    Text,
    Pen,
    Svg,
    Comp,
    WebComp
  } type = Type::Video;

  // Solid color
  float solidR = 0.5f, solidG = 0.5f, solidB = 0.5f, solidA = 1.f;

  // Text style
  struct TextDesc {
    std::string text = "New Text";
    std::string fontFamily = "Arial";
    float fontSize = 48.f;
    bool bold = false;
    bool italic = false;
    std::string alignment = "left";
    float lineHeight = 1.2f;
    float letterSpacing = 0.f;
    bool allCaps = false;
    float fillR = 1.f, fillG = 1.f, fillB = 1.f, fillA = 1.f;
    float strokeR = 0.f, strokeG = 0.f, strokeB = 0.f, strokeA = 1.f;
    float strokeWidth = 0.f;
    bool shadowEnabled = false;
    float shadowR = 0.f, shadowG = 0.f, shadowB = 0.f, shadowA = 0.6f;
    float shadowOffsetX = 4.f, shadowOffsetY = 4.f, shadowBlur = 6.f;
    bool bgEnabled = false;
    float bgR = 0.f, bgG = 0.f, bgB = 0.f, bgA = 0.5f;
    float bgPaddingX = 20.f, bgPaddingY = 10.f, bgCornerRadius = 0.f;
    // Text Animator
    bool animEnabled = false;
    int animMode = 0;
    int animProperty = 0;
    float animFrom = 0.f;
    float animTo = 1.f;
    int animEasing = 3;
    float animStartOff = 0.f; // 0-1
    float animEndOff = 1.f;   // 0-1
  } text;

  // Shape style
  struct ShapeDesc {
    std::string shapeType = "rect";
    float width = 200.f, height = 120.f, cornerRadius = 0.f;
    float radiusX = 100.f, radiusY = 80.f;
    float outerRadius = 100.f, innerRadius = 40.f;
    int numPoints = 5;
    int numSides = 6;
    float polygonRadius = 100.f;
    float x1 = -100.f, y1 = 0.f, x2 = 100.f, y2 = 0.f;
    float arcStartAngle = 0.f, arcSweepAngle = 180.f, arcRadius = 100.f;
    float fillR = 0.4f, fillG = 0.4f, fillB = 1.f, fillA = 1.f;
    float fillOpacity = 1.f;
    float strokeR = 1.f, strokeG = 1.f, strokeB = 1.f, strokeA = 1.f;
    float strokeWidth = 0.f;
    bool shadowEnabled = false;
    float shadowR = 0.f, shadowG = 0.f, shadowB = 0.f, shadowA = 0.75f;
    float shadowAngle = 135.f, shadowDistance = 10.f, shadowBlur = 5.f;
  } shape;

  // Bezier pen path
  struct BezierPt {
    float x = 0.f, y = 0.f;
    float inX = 0.f, inY = 0.f;
    float outX = 0.f, outY = 0.f;
  };
  struct PenDesc {
    bool isClosed = false;
    std::vector<BezierPt> points;
    float fillR = 0.4f, fillG = 0.4f, fillB = 1.f, fillA = 1.f;
    float fillOpacity = 1.f;
    float strokeR = 1.f, strokeG = 1.f, strokeB = 1.f, strokeA = 1.f;
    float strokeWidth = 2.f;
    bool shadowEnabled = false;
    float shadowR = 0.f, shadowG = 0.f, shadowB = 0.f, shadowA = 0.75f;
    float shadowAngle = 135.f, shadowDistance = 10.f, shadowBlur = 5.f;
  } pen;

  // SVG style
  struct SvgDesc {
    float displayW = 0.f;
    float displayH = 0.f;
    bool tintEnabled = false;
    float tintR = 1.f, tintG = 1.f, tintB = 1.f, tintA = 1.f;
  } svg;

  // Nested composition
  struct CompDesc {
    std::string compId;
    std::shared_ptr<FrameDescriptor> innerFd;
  } comp;

  const uint8_t *rawRGBA = nullptr;
  size_t rawRGBASize = 0;
};

struct TransitionDesc {
  std::string typeId;
  std::string transId;
  std::string clipA_id;
  std::string clipB_id;
  float progress = 0.f;
  struct UniformValue {
    std::string id;
    std::vector<float> values;
  };
  std::vector<UniformValue> uniforms;
  bool valid = false;
};

struct FrameDescriptor {
  int64_t frame = 0;
  float fps = 30.f;
  int width = 1920;
  int height = 1080;
  std::vector<ClipDesc> clips;
  TransitionDesc transition;
  bool valid = false;
  std::string compId; // set for nested composition frames
};

#include <nlohmann/json.hpp>

inline FrameDescriptor parseFrameDescriptorFromJson(const nlohmann::json &j,
                                                    int depth = 0);

inline FrameDescriptor parseFrameDescriptorFromJson(const nlohmann::json &j,
                                                    int depth) {
  FrameDescriptor fd;
  fd.frame = j.value("frame", int64_t{0});
  fd.fps = j.value("fps", 30.f);
  fd.width = j.value("width", 1920);
  fd.height = j.value("height", 1080);
  fd.compId = j.value("compId", std::string{});

  for (const auto &c : j.value("clips", nlohmann::json::array())) {
    ClipDesc cd;
    cd.clipId = c.value("clipId", std::string{});
    cd.file = c.value("file", std::string{});
    cd.sourceFrame = c.value("sourceFrame", int64_t{0});
    cd.opacity = c.value("opacity", 1.f);
    cd.blendMode = c.value("blendMode", 0);

    if (c.contains("transform")) {
      auto &t = c["transform"];
      cd.transform.x = t.value("x", 0.f);
      cd.transform.y = t.value("y", 0.f);
      cd.transform.scaleX = t.value("scaleX", 1.f);
      cd.transform.scaleY = t.value("scaleY", 1.f);
      cd.transform.rotation = t.value("rotation", 0.f);
      cd.transform.anchorX = t.value("anchorX", 0.f);
      cd.transform.anchorY = t.value("anchorY", 0.f);
    }

    std::string typeStr = c.value("type", std::string{"video"});
    if (typeStr == "image")
      cd.type = ClipDesc::Type::Image;
    else if (typeStr == "solid")
      cd.type = ClipDesc::Type::Solid;
    else if (typeStr == "shape")
      cd.type = ClipDesc::Type::Shape;
    else if (typeStr == "text")
      cd.type = ClipDesc::Type::Text;
    else if (typeStr == "pen")
      cd.type = ClipDesc::Type::Pen;
    else if (typeStr == "svg")
      cd.type = ClipDesc::Type::Svg;
    else if (typeStr == "comp")
      cd.type = ClipDesc::Type::Comp;
    else if (typeStr == "webcomp")
      cd.type = ClipDesc::Type::WebComp;
    else
      cd.type = ClipDesc::Type::Video;

    if (cd.type == ClipDesc::Type::Solid && c.contains("color")) {
      auto &col = c["color"];
      cd.solidR = col.value("r", 0.5f);
      cd.solidG = col.value("g", 0.5f);
      cd.solidB = col.value("b", 0.5f);
      cd.solidA = col.value("a", 1.0f);
    }

    if (cd.type == ClipDesc::Type::Text && c.contains("textStyle")) {
      auto &s = c["textStyle"];
      auto &t = cd.text;
      t.text = s.value("text", std::string{"New Text"});
      t.fontFamily = s.value("fontFamily", std::string{"Arial"});
      t.fontSize = s.value("fontSize", 48.f);
      t.bold = s.value("bold", false);
      t.italic = s.value("italic", false);
      t.alignment = s.value("alignment", std::string{"left"});
      t.lineHeight = s.value("lineHeight", 1.2f);
      t.letterSpacing = s.value("letterSpacing", 0.f);
      t.allCaps = s.value("allCaps", false);
      auto fill = s.value("color", nlohmann::json::array({1, 1, 1, 1}));
      t.fillR = fill.size() > 0 ? float(fill[0]) : 1.f;
      t.fillG = fill.size() > 1 ? float(fill[1]) : 1.f;
      t.fillB = fill.size() > 2 ? float(fill[2]) : 1.f;
      t.fillA = fill.size() > 3 ? float(fill[3]) : 1.f;
      t.strokeWidth = s.value("strokeWidth", 0.f);
      auto sc = s.value("strokeColor", nlohmann::json::array({0, 0, 0, 1}));
      t.strokeR = sc.size() > 0 ? float(sc[0]) : 0.f;
      t.strokeG = sc.size() > 1 ? float(sc[1]) : 0.f;
      t.strokeB = sc.size() > 2 ? float(sc[2]) : 0.f;
      t.strokeA = sc.size() > 3 ? float(sc[3]) : 1.f;
      t.shadowEnabled = s.value("shadowEnabled", false);
      t.shadowOffsetX = s.value("shadowOffsetX", 4.f);
      t.shadowOffsetY = s.value("shadowOffsetY", 4.f);
      t.shadowBlur = s.value("shadowBlur", 6.f);
      auto shc = s.value("shadowColor", nlohmann::json::array({0, 0, 0, 0.6}));
      t.shadowR = shc.size() > 0 ? float(shc[0]) : 0.f;
      t.shadowG = shc.size() > 1 ? float(shc[1]) : 0.f;
      t.shadowB = shc.size() > 2 ? float(shc[2]) : 0.f;
      t.shadowA = shc.size() > 3 ? float(shc[3]) : 0.6f;
      t.bgEnabled = s.value("bgEnabled", false);
      t.bgPaddingX = s.value("bgPaddingX", 20.f);
      t.bgPaddingY = s.value("bgPaddingY", 10.f);
      t.bgCornerRadius = s.value("bgCornerRadius", 0.f);
      auto bgc = s.value("bgColor", nlohmann::json::array({0, 0, 0, 0.5}));
      t.bgR = bgc.size() > 0 ? float(bgc[0]) : 0.f;
      t.bgG = bgc.size() > 1 ? float(bgc[1]) : 0.f;
      t.bgB = bgc.size() > 2 ? float(bgc[2]) : 0.f;
      t.bgA = bgc.size() > 3 ? float(bgc[3]) : 0.5f;
      if (s.contains("animator")) {
        auto &a = s["animator"];
        t.animEnabled = a.value("enabled", false);
        std::string mode = a.value("mode", std::string{"characters"});
        t.animMode = (mode == "words") ? 1 : (mode == "lines") ? 2 : 0;
        std::string prop = a.value("property", std::string{"opacity"});
        t.animProperty = (prop == "offset_y")   ? 1
                         : (prop == "offset_x") ? 2
                         : (prop == "scale")    ? 3
                                                : 0;
        t.animFrom = a.value("from", 0.f);
        t.animTo = a.value("to", 1.f);
        std::string eas = a.value("easing", std::string{"ease_both"});
        t.animEasing = (eas == "linear")     ? 0
                       : (eas == "ease_in")  ? 1
                       : (eas == "ease_out") ? 2
                                             : 3;
        t.animStartOff = a.value("startOffset", 0.f);
        t.animEndOff = a.value("endOffset", 1.f);
      }
    }

    if (cd.type == ClipDesc::Type::Shape && c.contains("shapeStyle")) {
      auto &s = c["shapeStyle"];
      auto &sh = cd.shape;
      sh.shapeType = s.value("shapeType", std::string{"rect"});
      sh.width = s.value("width", 200.f);
      sh.height = s.value("height", 120.f);
      sh.cornerRadius = s.value("cornerRadius", 0.f);
      sh.radiusX = s.value("radiusX", 100.f);
      sh.radiusY = s.value("radiusY", 80.f);
      sh.outerRadius = s.value("outerRadius", 100.f);
      sh.innerRadius = s.value("innerRadius", 40.f);
      sh.numPoints = s.value("numPoints", 5);
      sh.numSides = s.value("numSides", 6);
      sh.polygonRadius = s.value("polygonRadius", 100.f);
      sh.x1 = s.value("x1", -100.f);
      sh.y1 = s.value("y1", 0.f);
      sh.x2 = s.value("x2", 100.f);
      sh.y2 = s.value("y2", 0.f);
      sh.arcStartAngle = s.value("arcStartAngle", 0.f);
      sh.arcSweepAngle = s.value("arcSweepAngle", 180.f);
      sh.arcRadius = s.value("arcRadius", 100.f);
      auto fc = s.value("fillColor", nlohmann::json::array({0.4, 0.4, 1, 1}));
      sh.fillR = fc.size() > 0 ? float(fc[0]) : 0.4f;
      sh.fillG = fc.size() > 1 ? float(fc[1]) : 0.4f;
      sh.fillB = fc.size() > 2 ? float(fc[2]) : 1.f;
      sh.fillA = fc.size() > 3 ? float(fc[3]) : 1.f;
      sh.fillOpacity = s.value("fillOpacity", 1.f);
      sh.strokeWidth = s.value("strokeWidth", 0.f);
      auto stc = s.value("strokeColor", nlohmann::json::array({1, 1, 1, 1}));
      sh.strokeR = stc.size() > 0 ? float(stc[0]) : 1.f;
      sh.strokeG = stc.size() > 1 ? float(stc[1]) : 1.f;
      sh.strokeB = stc.size() > 2 ? float(stc[2]) : 1.f;
      sh.strokeA = stc.size() > 3 ? float(stc[3]) : 1.f;
      sh.shadowEnabled = s.value("shadowEnabled", false);
      sh.shadowAngle = s.value("shadowAngle", 135.f);
      sh.shadowDistance = s.value("shadowDistance", 10.f);
      sh.shadowBlur = s.value("shadowBlur", 5.f);
      auto shc = s.value("shadowColor", nlohmann::json::array({0, 0, 0, 0.75}));
      sh.shadowR = shc.size() > 0 ? float(shc[0]) : 0.f;
      sh.shadowG = shc.size() > 1 ? float(shc[1]) : 0.f;
      sh.shadowB = shc.size() > 2 ? float(shc[2]) : 0.f;
      sh.shadowA = shc.size() > 3 ? float(shc[3]) : 0.75f;
    }

    if (cd.type == ClipDesc::Type::Pen && c.contains("penStyle")) {
      auto &s = c["penStyle"];
      auto &p = cd.pen;
      p.isClosed = s.value("isClosed", false);
      for (const auto &jpt : s.value("points", nlohmann::json::array())) {
        ClipDesc::BezierPt bp;
        bp.x = jpt.value("x", 0.f);
        bp.y = jpt.value("y", 0.f);
        bp.inX = jpt.value("inX", 0.f);
        bp.inY = jpt.value("inY", 0.f);
        bp.outX = jpt.value("outX", 0.f);
        bp.outY = jpt.value("outY", 0.f);
        p.points.push_back(bp);
      }
      auto fc = s.value("fillColor", nlohmann::json::array({0.4, 0.4, 1, 1}));
      p.fillR = fc.size() > 0 ? float(fc[0]) : 0.4f;
      p.fillG = fc.size() > 1 ? float(fc[1]) : 0.4f;
      p.fillB = fc.size() > 2 ? float(fc[2]) : 1.f;
      p.fillA = fc.size() > 3 ? float(fc[3]) : 1.f;
      p.fillOpacity = s.value("fillOpacity", 1.f);
      p.strokeWidth = s.value("strokeWidth", 2.f);
      auto stc = s.value("strokeColor", nlohmann::json::array({1, 1, 1, 1}));
      p.strokeR = stc.size() > 0 ? float(stc[0]) : 1.f;
      p.strokeG = stc.size() > 1 ? float(stc[1]) : 1.f;
      p.strokeB = stc.size() > 2 ? float(stc[2]) : 1.f;
      p.strokeA = stc.size() > 3 ? float(stc[3]) : 1.f;
      p.shadowEnabled = s.value("shadowEnabled", false);
      p.shadowAngle = s.value("shadowAngle", 135.f);
      p.shadowDistance = s.value("shadowDistance", 10.f);
      p.shadowBlur = s.value("shadowBlur", 5.f);
      auto shc = s.value("shadowColor", nlohmann::json::array({0, 0, 0, 0.75}));
      p.shadowR = shc.size() > 0 ? float(shc[0]) : 0.f;
      p.shadowG = shc.size() > 1 ? float(shc[1]) : 0.f;
      p.shadowB = shc.size() > 2 ? float(shc[2]) : 0.f;
      p.shadowA = shc.size() > 3 ? float(shc[3]) : 0.75f;
    }

    if (cd.type == ClipDesc::Type::Svg && c.contains("svgStyle")) {
      auto &s = c["svgStyle"];
      auto &sv = cd.svg;
      sv.displayW = s.value("displayW", 0.f);
      sv.displayH = s.value("displayH", 0.f);
      sv.tintEnabled = s.value("tintEnabled", false);
      auto tc = s.value("tintColor", nlohmann::json::array({1, 1, 1, 1}));
      sv.tintR = tc.size() > 0 ? float(tc[0]) : 1.f;
      sv.tintG = tc.size() > 1 ? float(tc[1]) : 1.f;
      sv.tintB = tc.size() > 2 ? float(tc[2]) : 1.f;
      sv.tintA = tc.size() > 3 ? float(tc[3]) : 1.f;
    }

    // recursion
    if (cd.type == ClipDesc::Type::Comp && c.contains("compFrameDescriptor") &&
        depth < 8) {
      cd.comp.compId = c.value("compId", std::string{});
      cd.comp.innerFd = std::make_shared<FrameDescriptor>(
          parseFrameDescriptorFromJson(c["compFrameDescriptor"], depth + 1));
    }

    for (const auto &e : c.value("effects", nlohmann::json::array())) {
      EffectParam ep;
      ep.typeId = e.value("typeId", std::string{});
      for (const auto &u : e.value("uniforms", nlohmann::json::array())) {
        EffectParam::UniformValue uv;
        uv.id = u.value("id", std::string{});
        uv.values = u.value("values", std::vector<float>{});
        ep.uniforms.push_back(std::move(uv));
      }
      cd.effects.push_back(std::move(ep));
    }
    fd.clips.push_back(std::move(cd));
  }

  if (j.contains("transition")) {
    const auto &jt = j["transition"];
    TransitionDesc &td = fd.transition;
    td.typeId = jt.value("typeId", std::string{});
    td.transId = jt.value("transId", std::string{});
    td.clipA_id = jt.value("clipA_id", std::string{});
    td.clipB_id = jt.value("clipB_id", std::string{});
    td.progress = jt.value("progress", 0.f);
    for (const auto &u : jt.value("uniforms", nlohmann::json::array())) {
      TransitionDesc::UniformValue uv;
      uv.id = u.value("id", std::string{});
      uv.values = u.value("values", std::vector<float>{});
      td.uniforms.push_back(std::move(uv));
    }
    td.valid = !td.typeId.empty();
  }

  fd.valid = true;
  return fd;
}

inline FrameDescriptor parseFrameDescriptor(const std::string &jsonStr) {
  try {
    auto j = nlohmann::json::parse(jsonStr);
    return parseFrameDescriptorFromJson(j, 0);
  } catch (const std::exception &e) {
    std::cerr << "[FrameDescriptor] Parse error: " << e.what() << "\n";
    FrameDescriptor fd;
    fd.valid = false;
    return fd;
  }
}
