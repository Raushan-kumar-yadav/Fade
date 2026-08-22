#pragma once
#include "include/core/SkImage.h"
#include "include/core/SkPath.h"
#include <cstdint>
#include <glm/glm.hpp>
#include <memory>
#include <string>
#include <vector>

class baseClip;
class MaskGroupComponent;

enum class SnapshotClipType { Video, Image, Lottie, Text, Solid, Shape, Svg };

struct ShapeLayerSnapshot {
  SkPath path;
  glm::mat4 shapeModel{1.f};
  glm::vec4 fillColor{1.f};
  glm::vec4 strokeColor{0.f};
  glm::vec4 shadowColor{0.f};
  float fillOpacity = 1.f;
  float strokeWidth = 0.f;
  float shadowAngle = 0.f;
  float shadowDistance = 0.f;
  float shadowBlur = 0.f;
  bool hasShadow = false;
};

// One active clip frozen at a single frame
struct ClipSnapshot {
  std::string clipId;
  SnapshotClipType type = SnapshotClipType::Video;
  int64_t localFrame = 0; // globalFrame - startFrame
  glm::mat4 model{1.f};   // transform matrix
  glm::vec2 size{1920, 1080};
  float opacity = 1.f; // already-evaluated

  std::string assetId;

  // GPU image from m_gpuTextureCache
  sk_sp<SkImage> gpuImage;

  // Text
  std::string text;
  std::string fontName;
  float fontSize = 36.f;
  glm::vec4 textColor{1.f};

  // Solid
  glm::vec4 solidColor{1.f};

  // Shape
  std::vector<ShapeLayerSnapshot> shapes;

  std::shared_ptr<baseClip> clipOwner;
  const MaskGroupComponent *masks = nullptr;
};

struct FrameSnapshot {
  int64_t frame = 0;
  float fps = 30.f;
  int compWidth = 1920;
  int compHeight = 1080;
  std::vector<ClipSnapshot> clips;
};
