#pragma once
#include "EffectRegistry.hpp"
#include "core/animation/AnimatableProperty.hpp"
#include "core/expression/IPropertyAccessor.hpp"
#include "core/rendering/data/clipParam.hpp"
#include <glm/glm.hpp>
#include <memory>
#include <mutex>
#include <variant>
#include <vector>

#include "effects/SkRuntimeEffect.h"
#include "include/core/SkCanvas.h"
#include "include/core/SkImage.h"
#include "include/core/SkSurface.h"

#include <atomic>

class GrDirectContext;

class EffectInstance {
  static std::atomic<int> s_nextId;

public:
  EffectInstance(const EffectDef &def, AnimationEngine &engine);
  ~EffectInstance() = default;

  EffectInstance(const EffectInstance &) = delete;
  EffectInstance &operator=(const EffectInstance &) = delete;

  const std::string &getTypeId() const { return m_def.typeId; }
  const std::string &getDisplayName() const { return m_def.displayName; }
  bool isEnabled() const { return m_enabled; }
  void setEnabled(bool e) { m_enabled = e; }
  int getInstanceId() const { return m_instanceId; }

  // Effect mask selector
  // id
  const std::string &getMaskSelectorId() const { return m_maskSelectorId; }
  void setMaskSelectorId(const std::string &id) { m_maskSelectorId = id; }

  sk_sp<SkImage> apply(sk_sp<SkImage> input, int64_t frame,
                       GrDirectContext *grCtx,
                       glm::vec2 clipOrigin = glm::vec2(0.f),
                       sk_sp<SkImage> originalSource = nullptr,
                       glm::vec2 clipSize = glm::vec2(0.f));

  void evaluateAll(int64_t frame);

  void drawViewOverlay(SkCanvas *canvas, float clipW, float clipH) const;

  void appendUIProperties(std::vector<EffectParameter> &out, ClipType clipType);

  IPropertyAccessor *getPropertyAccessorByParamId(const std::string &id);

private:
  const EffectDef &m_def;
  AnimationEngine &m_engine;
  bool m_enabled = true;
  int m_instanceId;
  std::string m_maskSelectorId;

  using PropVariant =
      std::variant<std::unique_ptr<AnimatableProperty<float>>,
                   std::unique_ptr<AnimatableProperty<bool>>,
                   std::unique_ptr<AnimatableProperty<int>>,
                   std::unique_ptr<AnimatableProperty<glm::vec2>>,
                   std::unique_ptr<AnimatableProperty<glm::vec4>>>;

  struct DynParam {
    ParamDef def;
    PropVariant prop;
  };

  mutable std::recursive_mutex m_paramsMutex;
  std::vector<DynParam> m_params;

  void fillUniforms(SkRuntimeShaderBuilder &builder);

  sk_sp<SkImage> applyDeepGlow(sk_sp<SkImage> input, GrDirectContext *grCtx);
};
