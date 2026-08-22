#include "EffectInstance.hpp"
#include "EffectRegistry.hpp"
#include "core/api/logger.hpp"
#include "effects/SkImageFilters.h"
#include "gpu/ganesh/GrDirectContext.h"
#include "include/core/SkCanvas.h"
#include "include/core/SkData.h"
#include "include/core/SkSurface.h"
#include "include/gpu/ganesh/SkSurfaceGanesh.h"

std::atomic<int> EffectInstance::s_nextId{0};

EffectInstance::EffectInstance(const EffectDef &def, AnimationEngine &engine)
    : m_def(def), m_engine(engine), m_instanceId(s_nextId++) {

  for (const auto &pd : def.params) {
    DynParam dp;
    dp.def = pd;

    if (pd.uiType == ParamType::Vec2Input) {
      auto val = std::get<glm::vec2>(pd.defaultVal);
      dp.prop = std::make_unique<AnimatableProperty<glm::vec2>>(engine, val);
    } else if (pd.uiType == ParamType::Vec4Input) {
      auto val = std::get<glm::vec4>(pd.defaultVal);
      dp.prop = std::make_unique<AnimatableProperty<glm::vec4>>(engine, val);
    } else if (pd.uiType == ParamType::IntSlider) {
      auto val = std::get<int>(pd.defaultVal);
      dp.prop = std::make_unique<AnimatableProperty<int>>(engine, val);
    } else if (pd.uiType == ParamType::ToggleBool) {
      float fval = 0.f;
      if (auto *f = std::get_if<float>(&pd.defaultVal))
        fval = *f;
      dp.prop =
          std::make_unique<AnimatableProperty<bool>>(engine, fval >= 0.5f);
    } else {
      auto val = std::get<float>(pd.defaultVal);
      dp.prop = std::make_unique<AnimatableProperty<float>>(engine, val);
    }

    m_params.push_back(std::move(dp));
  }
}

void EffectInstance::evaluateAll(int64_t frame) {
  std::lock_guard<std::recursive_mutex> lk(m_paramsMutex);
  for (auto &dp : m_params) {
    std::visit(
        [frame](auto &propPtr) {
          if (propPtr)
            propPtr->update(frame);
        },
        dp.prop);
  }
}

void EffectInstance::fillUniforms(SkRuntimeShaderBuilder &builder) {

  for (auto &dp : m_params) {
    const char *name = dp.def.id.c_str();

    if (!builder.effect()->findUniform(name))
      continue;

    if (auto *fp =
            std::get_if<std::unique_ptr<AnimatableProperty<float>>>(&dp.prop)) {
      builder.uniform(name) = (*fp)->get();
    } else if (auto *bp =
                   std::get_if<std::unique_ptr<AnimatableProperty<bool>>>(
                       &dp.prop)) {
      builder.uniform(name) = (*bp)->get() ? 1.f : 0.f;
    } else if (auto *ip = std::get_if<std::unique_ptr<AnimatableProperty<int>>>(
                   &dp.prop)) {
      builder.uniform(name) = static_cast<float>((*ip)->get());
    } else if (auto *v2p =
                   std::get_if<std::unique_ptr<AnimatableProperty<glm::vec2>>>(
                       &dp.prop)) {
      glm::vec2 v = (*v2p)->get();
      builder.uniform(name) = SkV2{v.x, v.y};
    } else if (auto *v4p =
                   std::get_if<std::unique_ptr<AnimatableProperty<glm::vec4>>>(
                       &dp.prop)) {
      glm::vec4 v = (*v4p)->get();
      builder.uniform(name) = SkV4{v.x, v.y, v.z, v.w};
    }
  }
}

sk_sp<SkImage> EffectInstance::applyDeepGlow(sk_sp<SkImage> input,
                                             GrDirectContext *grCtx) {

  float radius = 40.f, intensity = 2.f, blendMode = 0.f, opacity = 1.f;
  float threshold = 0.5f, softness = 0.2f, useColorTint = 0.f;
  glm::vec4 glowColorA{1.f, 1.f, 1.f, 1.f}, glowColorB{0.5f, 0.5f, 1.f, 1.f};

  {
    std::lock_guard<std::recursive_mutex> lk(m_paramsMutex);
    for (const auto &dp : m_params) {
      if (const auto *fp =
              std::get_if<std::unique_ptr<AnimatableProperty<float>>>(
                  &dp.prop)) {
        const float v = (*fp)->get();
        if (dp.def.id == "radius")
          radius = v;
        else if (dp.def.id == "intensity")
          intensity = v;
        else if (dp.def.id == "blendMode")
          blendMode = v;
        else if (dp.def.id == "opacity")
          opacity = v;
        else if (dp.def.id == "threshold")
          threshold = v;
        else if (dp.def.id == "softness")
          softness = v;
        else if (dp.def.id == "useColorTint")
          useColorTint = v;
      } else if (const auto *v4p = std::get_if<
                     std::unique_ptr<AnimatableProperty<glm::vec4>>>(
                     &dp.prop)) {
        const glm::vec4 v = (*v4p)->get();
        if (dp.def.id == "glowColorA")
          glowColorA = v;
        else if (dp.def.id == "glowColorB")
          glowColorB = v;
      }
    }
  }

  const int W = input->width();
  const int H = input->height();
  auto info =
      SkImageInfo::Make(W, H, kRGBA_8888_SkColorType, kPremul_SkAlphaType);

  // Threshold extract
  SkRuntimeShaderBuilder threshBuilder(m_def.compiled);
  threshBuilder.child("source") =
      input->makeShader(SkSamplingOptions(SkFilterMode::kLinear));
  if (m_def.compiled->findUniform("threshold"))
    threshBuilder.uniform("threshold") = threshold;
  if (m_def.compiled->findUniform("softness"))
    threshBuilder.uniform("softness") = softness;
  if (m_def.compiled->findUniform("useColorTint"))
    threshBuilder.uniform("useColorTint") = useColorTint;
  if (m_def.compiled->findUniform("glowColorA"))
    threshBuilder.uniform("glowColorA") =
        SkV4{glowColorA.x, glowColorA.y, glowColorA.z, glowColorA.w};
  if (m_def.compiled->findUniform("glowColorB"))
    threshBuilder.uniform("glowColorB") =
        SkV4{glowColorB.x, glowColorB.y, glowColorB.z, glowColorB.w};

  auto threshSurf =
      SkSurfaces::RenderTarget(grCtx, skgpu::Budgeted::kYes, info);
  if (!threshSurf)
    return input;

  SkPaint threshPaint;
  threshPaint.setShader(threshBuilder.makeShader());
  threshSurf->getCanvas()->drawPaint(threshPaint);
  sk_sp<SkImage> brightPixels = threshSurf->makeImageSnapshot();
  if (!brightPixels)
    return input;

  // Gaussian blur on the extracted bright pixels
  const float sigma = std::max(radius / 3.f, 0.5f);
  auto blurFilter =
      SkImageFilters::Blur(sigma, sigma, SkTileMode::kClamp, nullptr);

  auto blurSurf = SkSurfaces::RenderTarget(grCtx, skgpu::Budgeted::kYes, info);
  if (!blurSurf)
    return input;

  SkPaint blurPaint;
  blurPaint.setImageFilter(std::move(blurFilter));
  blurSurf->getCanvas()->drawImage(
      brightPixels, 0, 0, SkSamplingOptions(SkFilterMode::kLinear), &blurPaint);
  sk_sp<SkImage> bloom = blurSurf->makeImageSnapshot();
  if (!bloom)
    return input;

  //  Screen / Add composite
  const EffectDef *compDef =
      EffectRegistry::instance().getDef("deep_glow_composite");
  if (!compDef || !compDef->compiled) {
    // Fallback: native Skia Screen blend
    auto fallbackSurf =
        SkSurfaces::RenderTarget(grCtx, skgpu::Budgeted::kYes, info);
    if (!fallbackSurf)
      return input;
    fallbackSurf->getCanvas()->drawImage(input, 0, 0);
    SkPaint screenPaint;
    screenPaint.setAlphaf(std::min(intensity * 0.25f, 1.f));
    screenPaint.setBlendMode(SkBlendMode::kScreen);
    fallbackSurf->getCanvas()->drawImage(bloom, 0, 0, SkSamplingOptions(),
                                         &screenPaint);
    return fallbackSurf->makeImageSnapshot();
  }

  SkRuntimeShaderBuilder compBuilder(compDef->compiled);
  compBuilder.child("source") =
      input->makeShader(SkSamplingOptions(SkFilterMode::kLinear));
  compBuilder.child("bloom") =
      bloom->makeShader(SkSamplingOptions(SkFilterMode::kLinear));
  compBuilder.uniform("intensity") = intensity;
  compBuilder.uniform("blendMode") = blendMode;
  compBuilder.uniform("opacity") = opacity;

  auto compSurf = SkSurfaces::RenderTarget(grCtx, skgpu::Budgeted::kYes, info);
  if (!compSurf)
    return input;

  SkPaint compPaint;
  compPaint.setShader(compBuilder.makeShader());
  compSurf->getCanvas()->drawPaint(compPaint);
  return compSurf->makeImageSnapshot();
}

sk_sp<SkImage> EffectInstance::apply(sk_sp<SkImage> input, int64_t frame,
                                     GrDirectContext *grCtx,
                                     glm::vec2 clipOrigin,
                                     sk_sp<SkImage> originalSource,
                                     glm::vec2 clipSize) {
  if (!m_enabled || !input || !grCtx)
    return input;

  // 3-pass pipeline
  if (m_def.typeId == "deep_glow") {
    if (!m_def.compiled)
      return input;
    return applyDeepGlow(input, grCtx);
  }

  if (!m_def.compiled)
    return input;

  std::lock_guard<std::recursive_mutex> lk(m_paramsMutex);

  SkRuntimeShaderBuilder builder(m_def.compiled);

  builder.child("source") =
      input->makeShader(SkSamplingOptions(SkFilterMode::kLinear));

  fillUniforms(builder);

  if (m_def.compiled->findUniform("_frame"))
    builder.uniform("_frame") = static_cast<float>(frame);

  if (m_def.compiled->findUniform("_clipOriginX"))
    builder.uniform("_clipOriginX") = clipOrigin.x;
  if (m_def.compiled->findUniform("_clipOriginY"))
    builder.uniform("_clipOriginY") = clipOrigin.y;

  if (m_def.compiled->findUniform("_clipWidth"))
    builder.uniform("_clipWidth") = clipSize.x;
  if (m_def.compiled->findUniform("_clipHeight"))
    builder.uniform("_clipHeight") = clipSize.y;

  if (originalSource) {
    for (const auto &child : builder.effect()->children()) {
      if (child.name == "_originalSource") {
        builder.child("_originalSource") = originalSource->makeShader(
            SkSamplingOptions(SkFilterMode::kLinear));
        break;
      }
    }
  }

  auto info = SkImageInfo::Make(input->width(), input->height(),
                                kRGBA_8888_SkColorType, kPremul_SkAlphaType);
  auto surface = SkSurfaces::RenderTarget(grCtx, skgpu::Budgeted::kYes, info);
  if (!surface)
    return input;

  SkPaint paint;
  paint.setShader(builder.makeShader());
  surface->getCanvas()->drawPaint(paint);

  return surface->makeImageSnapshot();
}

void EffectInstance::drawViewOverlay(SkCanvas *canvas, float clipW,
                                     float clipH) const {
  std::lock_guard<std::recursive_mutex> lk(m_paramsMutex);
  float overlayEnabled = 0.f;
  for (const auto &dp : m_params) {
    if (dp.def.id == "viewOverlay") {
      if (const auto *fp =
              std::get_if<std::unique_ptr<AnimatableProperty<float>>>(&dp.prop))
        overlayEnabled = (*fp)->get();
      else if (const auto *bp =
                   std::get_if<std::unique_ptr<AnimatableProperty<bool>>>(
                       &dp.prop))
        overlayEnabled = (*bp)->get() ? 1.f : 0.f;
      break;
    }
  }
  if (overlayEnabled <= 0.5f)
    return;

  for (int i = 1; i <= 4; ++i) {
    const std::string ptId = "point" + std::to_string(i);
    const std::string colId = "color" + std::to_string(i);

    glm::vec2 pt(0.f);
    glm::vec4 col(1.f, 1.f, 1.f, 1.f);
    bool hasPt = false;

    for (const auto &dp : m_params) {
      if (dp.def.id == ptId) {
        if (const auto *v2p =
                std::get_if<std::unique_ptr<AnimatableProperty<glm::vec2>>>(
                    &dp.prop)) {
          pt = (*v2p)->get();
          hasPt = true;
        }
      }
      if (dp.def.id == colId) {
        if (const auto *v4p =
                std::get_if<std::unique_ptr<AnimatableProperty<glm::vec4>>>(
                    &dp.prop)) {
          col = (*v4p)->get();
        }
      }
    }
    if (!hasPt)
      continue;

    const float cx = pt.x;
    const float cy = pt.y;

    SkPaint outerPaint;
    outerPaint.setAntiAlias(true);
    outerPaint.setStyle(SkPaint::kFill_Style);
    outerPaint.setColor(SK_ColorWHITE);
    canvas->drawCircle(cx, cy, 12.f, outerPaint);

    SkPaint ringPaint;
    ringPaint.setAntiAlias(true);
    ringPaint.setStyle(SkPaint::kFill_Style);
    ringPaint.setColor(SK_ColorBLACK);
    canvas->drawCircle(cx, cy, 9.f, ringPaint);

    SkPaint fillPaint;
    fillPaint.setAntiAlias(true);
    fillPaint.setStyle(SkPaint::kFill_Style);
    fillPaint.setColor(SkColorSetARGB(
        static_cast<uint8_t>(glm::clamp(col.a, 0.f, 1.f) * 255.f),
        static_cast<uint8_t>(glm::clamp(col.r, 0.f, 1.f) * 255.f),
        static_cast<uint8_t>(glm::clamp(col.g, 0.f, 1.f) * 255.f),
        static_cast<uint8_t>(glm::clamp(col.b, 0.f, 1.f) * 255.f)));
    canvas->drawCircle(cx, cy, 7.f, fillPaint);
  }
}

void EffectInstance::appendUIProperties(std::vector<EffectParameter> &out,
                                        ClipType clipType) {
  std::lock_guard<std::recursive_mutex> lk(m_paramsMutex);
  std::string prefix = "fx" + std::to_string(m_instanceId) + "_";

  out.emplace_back(clipType, prefix + "__header", m_def.displayName,
                   ParamType::Header);

  for (auto &dp : m_params) {
    std::string uniqueId = prefix + dp.def.id;
    if (auto *fp =
            std::get_if<std::unique_ptr<AnimatableProperty<float>>>(&dp.prop)) {
      out.emplace_back(clipType, uniqueId, dp.def.displayName, dp.def.uiType,
                       dp.def.hint, dp.def.minVal, dp.def.maxVal, fp->get(),
                       &(*fp)->getTrack());
    } else if (auto *bp =
                   std::get_if<std::unique_ptr<AnimatableProperty<bool>>>(
                       &dp.prop)) {
      out.emplace_back(clipType, uniqueId, dp.def.displayName, dp.def.uiType,
                       dp.def.hint, dp.def.minVal, dp.def.maxVal, bp->get(),
                       &(*bp)->getTrack());
    } else if (auto *ip = std::get_if<std::unique_ptr<AnimatableProperty<int>>>(
                   &dp.prop)) {
      out.emplace_back(clipType, uniqueId, dp.def.displayName, dp.def.uiType,
                       dp.def.hint, dp.def.minVal, dp.def.maxVal, ip->get(),
                       &(*ip)->getTrack());
    } else if (auto *v2p =
                   std::get_if<std::unique_ptr<AnimatableProperty<glm::vec2>>>(
                       &dp.prop)) {
      out.emplace_back(clipType, uniqueId, dp.def.displayName, dp.def.uiType,
                       dp.def.hint, dp.def.minVal, dp.def.maxVal, v2p->get(),
                       &(*v2p)->getTrack());
    } else if (auto *v4p =
                   std::get_if<std::unique_ptr<AnimatableProperty<glm::vec4>>>(
                       &dp.prop)) {
      out.emplace_back(clipType, uniqueId, dp.def.displayName, dp.def.uiType,
                       dp.def.hint, dp.def.minVal, dp.def.maxVal, v4p->get(),
                       &(*v4p)->getTrack());
    }
  }

  out.emplace_back(clipType, prefix + "__mask_selector", "Mask Selector",
                   ParamType::OptionMenu, ParamDisplayHint::Default,
                   std::string(""), std::string(""), // min/max unused
                   nullptr,                          // no anim track
                   nullptr,                          // no uiDataPtr
                   nullptr);                         // options filled by model

  out.back().minVal = m_maskSelectorId;
}

IPropertyAccessor *
EffectInstance::getPropertyAccessorByParamId(const std::string &identifier) {
  std::lock_guard<std::recursive_mutex> lk(m_paramsMutex);
  for (auto &dp : m_params) {
    if (dp.def.id == identifier || dp.def.displayName == identifier) {
      return std::visit(
          [](auto &propPtr) -> IPropertyAccessor * {
            return propPtr ? propPtr->getAccessor() : nullptr;
          },
          dp.prop);
    }
  }
  return nullptr;
}
