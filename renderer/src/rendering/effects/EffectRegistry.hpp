#pragma once
#include "core/animation/AnimatableProperty.hpp"
#include "core/rendering/data/clipParam.hpp"
#include <glm/glm.hpp>
#include <memory>
#include <string>
#include <unordered_map>
#include <variant>
#include <vector>

#include "effects/SkRuntimeEffect.h"
#include "include/core/SkImage.h"

class GrDirectContext;
class AnimationEngine;

struct ParamDef {
  std::string id;
  std::string displayName;
  ParamType uiType = ParamType::FloatSlider;
  ParamDisplayHint hint = ParamDisplayHint::Default;
  ParamValue defaultVal = 0.0f;
  ParamValue minVal = 0.0f;
  ParamValue maxVal = 1.0f;
};

struct EffectDef {
  std::string typeId;
  std::string displayName;
  std::string category;
  bool internal = false;
  sk_sp<SkRuntimeEffect> compiled;
  std::vector<ParamDef> params;
};

class EffectInstance;

class EffectRegistry {
public:
  static EffectRegistry &instance();

  void scanEffectsDir(const std::string &path);

  const EffectDef *getDef(const std::string &typeId) const;
  std::vector<const EffectDef *> getAllDefs() const;

  std::unique_ptr<EffectInstance> create(const std::string &typeId,
                                         AnimationEngine &engine);

private:
  EffectRegistry() = default;
  std::unordered_map<std::string, EffectDef> m_defs;

  void loadEffect(const std::string &jsonPath);
  ParamType parseParamType(const std::string &str);
  ParamDisplayHint parseHint(const std::string &str);
};
