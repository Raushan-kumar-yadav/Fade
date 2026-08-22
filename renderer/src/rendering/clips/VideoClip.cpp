#include "VideoClip.hpp"
#include "core/rendering/data/BlendModeMap.hpp"

VideoClip::VideoClip(AnimationEngine &engine, std::shared_ptr<MediaAsset> asset,
                     std::string id, std::string assetId, int64_t startFrame,
                     int64_t endFrame, int trackIndex, int64_t inPoint)
    : baseClip(id, assetId, asset, startFrame, endFrame, trackIndex, inPoint),
      m_transform(engine), m_cropLeft(engine, 0.0f), m_cropRight(engine, 0.0f),
      m_cropTop(engine, 0.0f), m_cropBottom(engine, 0.0f),
      m_blendMode(engine, 0) {
  // m_pushConstants.isRGBA = 0;

  if (asset && asset->getType() == MediaType::image) {
    setColor(glm::vec4(0.60f, 0.40f, 0.80f, 1.0f));
  } else {
    setColor(glm::vec4(0.29f, 0.56f, 0.88f, 1.0f));
  }
}

void VideoClip::evaluateAll(int64_t currentFrame) {
  if (currentFrame != m_lastEvaluatedFrame) {
    m_isDirty = true;
    m_lastEvaluatedFrame = currentFrame;
  }
  if (!m_isDirty)
    return;

  int64_t localFrame = currentFrame - getStartFrame();

  m_transform.evaluateMath(localFrame);
  m_cropLeft.update(localFrame);
  m_cropRight.update(localFrame);
  m_cropTop.update(localFrame);
  m_cropBottom.update(localFrame);
  m_blendMode.update(localFrame);
  m_maskGroup.update(localFrame); // evaluate all masks
  for (auto &fx : m_effects)
    fx->evaluateAll(localFrame);

  m_pushConstants.model = m_transform.getModelMatrix();
  m_pushConstants.opacity = m_transform.getOpacity();
  m_pushConstants.blendMode = getBlendMode();

  m_isDirty = false;
}

std::vector<EffectParameter> VideoClip::getUIProperties() {
  std::vector<EffectParameter> uiParams;
  m_transform.appendUIProperties(uiParams);

  uiParams.emplace_back(ClipType::video, "crop_left", "Crop Left",
                        ParamType::FloatSlider, 0.0f, 1.0f, &m_cropLeft,
                        &m_cropLeft.getTrack());

  uiParams.emplace_back(ClipType::video, "crop_right", "Crop Right",
                        ParamType::FloatSlider, 0.0f, 1.0f, &m_cropRight,
                        &m_cropRight.getTrack());

  uiParams.emplace_back(ClipType::video, "crop_top", "Crop Top",
                        ParamType::FloatSlider, 0.0f, 1.0f, &m_cropTop,
                        &m_cropTop.getTrack());

  uiParams.emplace_back(ClipType::video, "crop_bottom", "Crop Bottom",
                        ParamType::FloatSlider, 0.0f, 1.0f, &m_cropBottom,
                        &m_cropBottom.getTrack());

  m_maskGroup.appendUIProperties(uiParams, ClipType::video);
  {
    EffectParameter p(
        ClipType::video, "blend_mode", "Blend Mode", ParamType::comboBox,
        ParamDisplayHint::Default, std::string(""), std::string(""), nullptr,
        getBlendModeNamePtr(), [this]() { return BlendModeMap::names(); });
    p.isConstantOnly = true;
    uiParams.push_back(std::move(p));
  }
  for (auto &fx : m_effects) {
    fx->appendUIProperties(uiParams, ClipType::video);
  }

  // Blend Mode

  return uiParams;
}