#pragma once
#include "core/animation/AnimatableProperty.hpp"
#include "core/api/logger.hpp"
#include "core/gpu/vulkan/data/DecodedFrame.hpp"
#include "core/gpu/vulkan/data/RenderableTexture.hpp"
#include "core/media/BaseAsset.hpp"
#include "core/media/MediaAsset.hpp"
#include "core/rendering/clips/mask/MaskGroupComponent.hpp"
#include "core/rendering/components/TransformComponent.hpp"
#include "core/rendering/data/clipParam.hpp"
#include "core/rendering/data/trackMateDef.hpp"
#include "core/rendering/effects/EffectInstance.hpp"
#include "glm/glm.hpp"
#include <iostream>
#include <limits>

class Timeline;

class baseClip {

protected:
  std::vector<EffectParameter> m_effectParameters;
  std::vector<std::unique_ptr<EffectInstance>> m_effects;
  std::shared_ptr<BaseAsset> m_sourceAsset;
  std::optional<std::string> m_parentGroupId;

private:
  std::string m_id;
  int64_t m_startFrame;
  int64_t m_endFrame;
  int64_t m_duration;
  std::string m_blendModeName = "Normal";
  int m_trackIndex;
  int64_t m_inPoint;
  int64_t m_outPoint;
  std::string m_assetId;
  TrackMate::TrackMatteType m_trackMatteType = TrackMate::TrackMatteType::None;
  std::string m_trackMatteClipId;
  bool m_isUsedAsMatte = false;
  bool m_isSelected = false;
  std::string m_name;
  glm::vec4 m_color = glm::vec4(0.29f, 0.56f, 0.88f, 1.0f);

public:
  baseClip(const std::string &id, const std::string &assetId,
           std::shared_ptr<BaseAsset> asset, int64_t startFrame,
           int64_t endFrame, int trackIndex, int64_t inPoint)
      : m_id(id), m_startFrame(startFrame), m_endFrame(endFrame),
        m_trackIndex(trackIndex), m_inPoint(inPoint), m_assetId(assetId),
        m_sourceAsset(asset) {}

  baseClip(const baseClip &other)
      : m_effectParameters(other.m_effectParameters),
        m_sourceAsset(other.m_sourceAsset),
        m_parentGroupId(other.m_parentGroupId), m_id(other.m_id),
        m_startFrame(other.m_startFrame), m_endFrame(other.m_endFrame),
        m_duration(other.m_duration), m_trackIndex(other.m_trackIndex),
        m_inPoint(other.m_inPoint), m_assetId(other.m_assetId),
        m_isSelected(other.m_isSelected), m_name(other.m_name),
        m_color(other.m_color) {}

  virtual ~baseClip() = default;

  const std::string &getId() const { return m_id; }
  int64_t getDuration() const { return m_endFrame - m_startFrame; }

  virtual void evaluateAll(int64_t currentFrame) = 0;
  virtual std::vector<EffectParameter> getUIProperties() = 0;

  virtual void markDirty() {}
  TrackMate::TrackMatteType getTrackMatteType() const {
    return m_trackMatteType;
  }
  const std::string &getTrackMatteClipId() const { return m_trackMatteClipId; }
  void setTrackMatteType(TrackMate::TrackMatteType t) { m_trackMatteType = t; }
  void setTrackMatteClipId(const std::string &id) { m_trackMatteClipId = id; }
  bool isUsedAsMatte() const { return m_isUsedAsMatte; }
  void setUsedAsMatte(bool v) { m_isUsedAsMatte = v; }

  int64_t getStartFrame() const { return m_startFrame; };
  int64_t getEndFrame() const { return m_endFrame; };
  int getTrackIndex() const { return m_trackIndex; };
  int64_t getInPoint() const { return m_inPoint; };
  virtual int64_t getLocalFrame(int64_t timelineFrame) const {
    return timelineFrame - m_startFrame + m_inPoint;
  }

  int getBlendMode() const {
    static const char *kNames[] = {
        "Normal",     "Multiply",   "Screen",      "Overlay",
        "Darken",     "Lighten",    "Color Dodge", "Color Burn",
        "Hard Light", "Soft Light", "Difference",  "Exclusion",
        "Hue",        "Saturation", "Color",       "Luminosity"};
    for (int i = 0; i < 16; ++i)
      if (m_blendModeName == kNames[i])
        return i;
    return 0;
  }
  void setBlendMode(int modeIndex) {
    static const char *kNames[] = {
        "Normal",     "Multiply",   "Screen",      "Overlay",
        "Darken",     "Lighten",    "Color Dodge", "Color Burn",
        "Hard Light", "Soft Light", "Difference",  "Exclusion",
        "Hue",        "Saturation", "Color",       "Luminosity"};
    if (modeIndex >= 0 && modeIndex < 16)
      m_blendModeName = kNames[modeIndex];
  }

  std::string *getBlendModeNamePtr() { return &m_blendModeName; }
  int64_t getOutPoint() const { return m_inPoint + getDuration(); };
  std::string getAssetId() const { return m_assetId; };
  bool getisSelected() const { return m_isSelected; }

  virtual ClipType getType() const = 0;

  virtual glm::vec2 getIntrinsicSize() const { return glm::vec2(0.f, 0.f); }

  virtual glm::mat4 getWorldTransform() const { return glm::mat4(1.f); }

  virtual const MaskGroupComponent *getMaskGroup() const { return nullptr; }
  virtual MaskGroupComponent *getMaskGroup() { return nullptr; }

  virtual glm::vec2 getExprPosition() const { return glm::vec2(0.f); }
  virtual glm::vec2 getExprScale() const { return glm::vec2(1.f); }
  virtual float getExprRotation() const { return 0.f; }
  virtual float getExprOpacity() const { return 1.f; }
  virtual glm::vec2 getExprAnchor() const { return glm::vec2(0.f); }

  virtual void bindExprContext(Timeline *tl, double fps) {
    auto params = getUIProperties();
    for (auto &p : params) {
      if (!p.animTrack)
        continue;
      switch (p.type) {
      case ParamType::FloatSlider:
        static_cast<AnimatableProperty<float> *>(p.animTrack)
            ->bindContext(this, tl, fps);
        break;
      case ParamType::IntSlider:
        static_cast<AnimatableProperty<int> *>(p.animTrack)
            ->bindContext(this, tl, fps);
        break;
      case ParamType::ToggleBool:
        static_cast<AnimatableProperty<bool> *>(p.animTrack)
            ->bindContext(this, tl, fps);
        break;
      case ParamType::Vec2Input:
        static_cast<AnimatableProperty<glm::vec2> *>(p.animTrack)
            ->bindContext(this, tl, fps);
        break;
      case ParamType::Vec4Input:
        static_cast<AnimatableProperty<glm::vec4> *>(p.animTrack)
            ->bindContext(this, tl, fps);
        break;
      default:
        break;
      }
    }
  }

  //   Expression API

  virtual bool setExpression(const std::string &paramId, const std::string &src,
                             std::string &outError) {
    auto params = getUIProperties();
    for (auto &p : params) {
      if (p.id != paramId || !p.animTrack)
        continue;
      switch (p.type) {
      case ParamType::FloatSlider:
        return static_cast<AnimatableProperty<float> *>(p.animTrack)
            ->setExpression(src, outError);
      case ParamType::IntSlider:
        return static_cast<AnimatableProperty<int> *>(p.animTrack)
            ->setExpression(src, outError);
      case ParamType::ToggleBool:
        return static_cast<AnimatableProperty<bool> *>(p.animTrack)
            ->setExpression(src, outError);
      case ParamType::Vec2Input:
        return static_cast<AnimatableProperty<glm::vec2> *>(p.animTrack)
            ->setExpression(src, outError);
      case ParamType::Vec4Input:
        return static_cast<AnimatableProperty<glm::vec4> *>(p.animTrack)
            ->setExpression(src, outError);
      default:
        outError = "Expression not supported for this param type";
        return false;
      }
    }
    outError = "Parameter '" + paramId + "' not found";
    return false;
  }

  virtual void clearExpression(const std::string &paramId) {
    auto params = getUIProperties();
    for (auto &p : params) {
      if (p.id != paramId || !p.animTrack)
        continue;
      switch (p.type) {
      case ParamType::FloatSlider:
        static_cast<AnimatableProperty<float> *>(p.animTrack)
            ->clearExpression();
        return;
      case ParamType::IntSlider:
        static_cast<AnimatableProperty<int> *>(p.animTrack)->clearExpression();
        return;
      case ParamType::ToggleBool:
        static_cast<AnimatableProperty<bool> *>(p.animTrack)->clearExpression();
        return;
      case ParamType::Vec2Input:
        static_cast<AnimatableProperty<glm::vec2> *>(p.animTrack)
            ->clearExpression();
        return;
      case ParamType::Vec4Input:
        static_cast<AnimatableProperty<glm::vec4> *>(p.animTrack)
            ->clearExpression();
        return;
      default:
        return;
      }
    }
  }

  virtual ExpressionState getExpressionState(const std::string &paramId) const {
    auto params = const_cast<baseClip *>(this)->getUIProperties();
    for (auto &p : params) {
      if (p.id != paramId || !p.animTrack)
        continue;
      switch (p.type) {
      case ParamType::FloatSlider:
        return static_cast<AnimatableProperty<float> *>(p.animTrack)
            ->getExpressionState();
      case ParamType::IntSlider:
        return static_cast<AnimatableProperty<int> *>(p.animTrack)
            ->getExpressionState();
      case ParamType::ToggleBool:
        return static_cast<AnimatableProperty<bool> *>(p.animTrack)
            ->getExpressionState();
      case ParamType::Vec2Input:
        return static_cast<AnimatableProperty<glm::vec2> *>(p.animTrack)
            ->getExpressionState();
      case ParamType::Vec4Input:
        return static_cast<AnimatableProperty<glm::vec4> *>(p.animTrack)
            ->getExpressionState();
      default:
        return ExpressionState::None;
      }
    }
    return ExpressionState::None;
  }

  virtual std::string getExpressionSource(const std::string &paramId) const {
    auto params = const_cast<baseClip *>(this)->getUIProperties();
    for (auto &p : params) {
      if (p.id != paramId || !p.animTrack)
        continue;
      switch (p.type) {
      case ParamType::FloatSlider:
        return static_cast<AnimatableProperty<float> *>(p.animTrack)
            ->getExpressionSource();
      case ParamType::IntSlider:
        return static_cast<AnimatableProperty<int> *>(p.animTrack)
            ->getExpressionSource();
      case ParamType::ToggleBool:
        return static_cast<AnimatableProperty<bool> *>(p.animTrack)
            ->getExpressionSource();
      case ParamType::Vec2Input:
        return static_cast<AnimatableProperty<glm::vec2> *>(p.animTrack)
            ->getExpressionSource();
      case ParamType::Vec4Input:
        return static_cast<AnimatableProperty<glm::vec4> *>(p.animTrack)
            ->getExpressionSource();
      default:
        return {};
      }
    }
    return {};
  }

  const std::vector<EffectParameter> &getEffectsParameters() const {
    return m_effectParameters;
  };

  void setStartFrame(int64_t frame) { m_startFrame = frame; };
  void setInPoint(int64_t framePoint) { m_inPoint = framePoint; };
  void setEndFrame(int64_t frame) { m_endFrame = frame; };
  void setTrackIndex(int index) { m_trackIndex = index; };
  // virtual void setTrackIndex(int trackIndex) = 0;

  void setSelected(bool state) { m_isSelected = state; };
  void addEffectParam(const EffectParameter &param) {
    m_effectParameters.push_back(param);
  }

  void addEffect(std::unique_ptr<EffectInstance> effect) {
    if (effect)
      m_effects.push_back(std::move(effect));
  }
  std::unique_ptr<EffectInstance> removeEffect(size_t index) {
    if (index >= m_effects.size())
      return nullptr;
    auto removed = std::move(m_effects[index]);
    m_effects.erase(m_effects.begin() + static_cast<ptrdiff_t>(index));
    return removed;
  }
  void moveEffect(size_t from, size_t to) {
    if (from >= m_effects.size() || to >= m_effects.size())
      return;
    auto tmp = std::move(m_effects[from]);
    m_effects.erase(m_effects.begin() + static_cast<ptrdiff_t>(from));
    m_effects.insert(m_effects.begin() + static_cast<ptrdiff_t>(to),
                     std::move(tmp));
  }
  const std::vector<std::unique_ptr<EffectInstance>> &getEffects() const {
    return m_effects;
  }
  std::vector<std::unique_ptr<EffectInstance>> &getEffects() {
    return m_effects;
  }
  void setId(std::string id) { m_id = id; };

  // Clone this
  virtual std::shared_ptr<baseClip> clone() const = 0;

  virtual int64_t getSourceMaxFrames() const { return INT64_MAX; }

  virtual bool isInfinite() const { return true; }

  EffectParameter *getEffectParamByParamID(const std::string &id) {
    for (auto &param : m_effectParameters) {
      if (param.id == id) {
        return &param;
      }
    }
    return nullptr;
  }

  virtual IPropertyAccessor *
  getPropertyAccessorByParamId(const std::string &id) {
    //  Fast lookup
    if (id.size() > 2 && id[0] == 'f' && id[1] == 'x') {
      size_t underscore = id.find('_');
      if (underscore != std::string::npos) {
        int instanceId = -1;
        try {
          instanceId = std::stoi(id.substr(2, underscore - 2));
        } catch (...) {
        }

        if (instanceId >= 0) {
          std::string localId = id.substr(underscore + 1);
          for (auto &eff : m_effects) {
            if (eff && eff->getInstanceId() == instanceId) {
              if (auto *acc = eff->getPropertyAccessorByParamId(localId))
                return acc;
            }
          }
        }
      }
    }

    //   Fallback
    auto params = getUIProperties();
    for (auto &p : params) {
      if ((p.id == id || p.displayName == id) && p.animTrack) {
        switch (p.type) {
        case ParamType::FloatSlider:
          return static_cast<AnimatableProperty<float> *>(p.animTrack)
              ->getAccessor();
        case ParamType::IntSlider:
          return static_cast<AnimatableProperty<int> *>(p.animTrack)
              ->getAccessor();
        case ParamType::ToggleBool:
          return static_cast<AnimatableProperty<bool> *>(p.animTrack)
              ->getAccessor();
        case ParamType::Vec2Input:
          return static_cast<AnimatableProperty<glm::vec2> *>(p.animTrack)
              ->getAccessor();
        case ParamType::Vec4Input:
          return static_cast<AnimatableProperty<glm::vec4> *>(p.animTrack)
              ->getAccessor();
        default:
          break;
        }
      }
    }
    return nullptr;
  }

  std::shared_ptr<BaseAsset> getSourceAsset() const { return m_sourceAsset; }

  template <typename T> std::shared_ptr<T> getSourceAssetAs() const {
    return std::dynamic_pointer_cast<T>(m_sourceAsset);
  }

  glm::vec4 getColor() const { return m_color; }
  void setColor(glm::vec4 newColor) { m_color = newColor; }

  std::string getName() const { return m_name; }
  void setName(std::string name) { m_name = name; }

  bool hasGroup() { return m_parentGroupId.has_value(); }

  void setGroup(const std::string &groupId) {
    m_parentGroupId.emplace(groupId);
  }

  std::string getGroupId() { return m_parentGroupId.value(); }

  bool operator<(const baseClip &other) const {
    return m_startFrame < other.m_startFrame;
  }

  bool operator<(int64_t frame) const { return m_startFrame < frame; }

  friend bool operator<(int64_t frame, const baseClip &clip) {
    return frame < clip.m_startFrame;
  }

  bool operator>(const baseClip &other) const {
    return m_startFrame > other.m_startFrame;
  }

  bool operator==(const baseClip &other) const { return m_id == other.m_id; }

  bool operator<=(const baseClip &other) const {
    return m_startFrame <= other.m_startFrame;
  }
};