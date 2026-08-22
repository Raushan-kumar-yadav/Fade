#pragma once
#include <functional>
#include <glm/glm.hpp>
#include <string>
#include <variant>
#include <vector>

enum class ClipType {
  video,
  audio,
  image,
  text,
  subtitle,
  unknown,
  solid,
  SVG,
  shape,
  Lottie,
  comp,
  adjustment
};
using ParamValue = std::variant<float, int, bool, glm::vec2, glm::vec3,
                                glm::vec4, glm::mat3, glm::mat4, std::string>;

enum class ParamType {
  FloatSlider,
  IntSlider,
  ToggleBool,
  Vec2Input,
  Mat3Grid,
  Vec4Input,
  TextInput,
  comboBox,
  Header,
  ActionButton,
  MaskPath,
  adjustment,

  ShapePath,
  OptionMenu,

};

enum class ParamDisplayHint {
  Default,    // fall back to ParamType behaviour
  Color,      // vec4  → RGBA color picker
  Vec4Value,  // vec4  → four independent float fields
  Vec2Value,  // vec2  → two independent float fields
  Vec3Value,  // vec3  → three independent float fields
  FloatValue, // float → plain number field (no slider chrome needed)
  IntValue,   // int   → plain integer field
};

enum class ExpressionState : int {
  None = 0,   // no expression set
  Active = 1, // expression compiled and running
  Error = 2,  // expression has a compile or runtime error
};

struct EffectParameter {
  ClipType clipType;
  std::string id;
  std::string displayName;
  ParamType type;
  ParamDisplayHint hint = ParamDisplayHint::Default;
  ParamValue minVal;
  ParamValue maxVal;

  void *animTrack = nullptr;
  void *uiDataPtr = nullptr;
  std::function<std::vector<std::string>()> getOptions = nullptr;
  bool isConstantOnly = false;

  ExpressionState exprState = ExpressionState::None;
  std::string expressionSource;
  int blendMode = 0;
  bool isDisabled = false;
  std::string disabledHint;
  // Full constructor with hint
  EffectParameter(ClipType cType, const std::string &i, const std::string &name,
                  ParamType t, ParamDisplayHint h, ParamValue minV,
                  ParamValue maxV, void *trackControl, void *dataPtr,
                  std::function<std::vector<std::string>()> options = nullptr)
      : clipType(cType), id(i), displayName(name), type(t), hint(h),
        minVal(minV), maxVal(maxV), animTrack(trackControl), uiDataPtr(dataPtr),
        getOptions(options) {}

  EffectParameter(ClipType cType, const std::string &i, const std::string &name,
                  ParamType t, ParamValue minV, ParamValue maxV,
                  void *trackControl, void *dataPtr,
                  std::function<std::vector<std::string>()> options = nullptr)
      : clipType(cType), id(i), displayName(name), type(t),
        hint(ParamDisplayHint::Default), minVal(minV), maxVal(maxV),
        animTrack(trackControl), uiDataPtr(dataPtr), getOptions(options) {}

  EffectParameter(ClipType cType, const std::string &i, const std::string &name,
                  ParamType t, ParamValue minV, ParamValue maxV, void *dataPtr,
                  std::function<std::vector<std::string>()> options = nullptr)
      : clipType(cType), id(i), displayName(name), type(t),
        hint(ParamDisplayHint::Default), minVal(minV), maxVal(maxV),
        animTrack(nullptr), uiDataPtr(dataPtr), getOptions(options) {}

  // Header-only constructor

  EffectParameter(ClipType cType, const std::string &id,
                  const std::string &displayName, ParamType headerType)
      : clipType(cType), id(id), displayName(displayName), type(headerType),
        hint(ParamDisplayHint::Default), minVal(0.0f), maxVal(0.0f),
        animTrack(nullptr), uiDataPtr(nullptr) {}
};