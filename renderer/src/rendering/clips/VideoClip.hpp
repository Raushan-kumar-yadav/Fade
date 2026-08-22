#pragma once
#include "core/animation/AnimationEngine.hpp"
#include "core/gpu/vulkan/data/Vertex.hpp"
#include "core/rendering/clips/BaseClip.hpp"
#include "core/rendering/clips/mask/MaskGroupComponent.hpp"
#include "core/rendering/components/TransformComponent.hpp"

class VideoClip : public baseClip {
private:
  TransformComponent m_transform;
  MaskGroupComponent m_maskGroup;
  ClipPushConstants m_pushConstants;

  AnimatableProperty<float> m_cropLeft;
  AnimatableProperty<float> m_cropRight;
  AnimatableProperty<float> m_cropTop;
  AnimatableProperty<float> m_cropBottom;
  AnimatableProperty<int> m_blendMode;

  bool m_isDirty = true;
  int64_t m_lastEvaluatedFrame = -1;

public:
  VideoClip(AnimationEngine &engine, std::shared_ptr<MediaAsset> asset,
            std::string id, std::string assetId, int64_t startFrame,
            int64_t endFrame, int trackIndex, int64_t inPoint);
  ~VideoClip() override = default;

  void evaluateAll(int64_t currentFrame) override;
  std::vector<EffectParameter> getUIProperties() override;

  std::shared_ptr<baseClip> clone() const override {
    return std::make_shared<VideoClip>(*this);
  }
  int64_t getSourceMaxFrames() const override {
    auto media = getSourceAssetAs<MediaAsset>();
    return media ? media->getTotalFrames() : INT64_MAX;
  }
  bool isInfinite() const override { return false; }
  ClipType getType() const override { return ClipType::video; }
  void setIsRgba() { m_pushConstants.isRGBA = 1; };
  const ClipPushConstants &getPushConstants() const { return m_pushConstants; }
  void markAsDirty() { m_isDirty = true; }
  const MaskGroupComponent *getMaskGroup() const override { return &m_maskGroup; }
  MaskGroupComponent *getMaskGroup() override { return &m_maskGroup; }

  // Expression DOM
  glm::vec2 getExprPosition() const override {
    return m_transform.getPosition();
  }
  glm::vec2 getExprScale() const override { return m_transform.getScale(); }
  float getExprRotation() const override { return m_transform.getRotation(); }
  float getExprOpacity() const override { return m_transform.getOpacity(); }
  glm::vec2 getExprAnchor() const override { return m_transform.getAnchor(); }
};