#pragma once
#include <QWindow>
#include <functional>
#include <memory>
#include <vector>
#include <vulkan/vulkan.h>

#include "camera/camera.hpp"
#include "core/SkSurface.h"
#include "core/gpu/vulkan/command/CommandPool.hpp"
#include "core/gpu/vulkan/data/Mesh.hpp"
#include "core/gpu/vulkan/data/RenderableTexture.hpp"
#include "core/gpu/vulkan/data/Vertex.hpp"
#include "core/gpu/vulkan/device/DeviceContext.hpp"
#include "core/gpu/vulkan/memory/UniformBuffer.hpp"
#include "core/gpu/vulkan/pipeline/Descriptor.hpp"
#include "core/gpu/vulkan/pipeline/DescriptorPool.hpp"
#include "core/gpu/vulkan/pipeline/DescriptorSetLayout.hpp"
#include "core/gpu/vulkan/pipeline/Pipeline.hpp"
#include "core/gpu/vulkan/rendering/RenderPass.hpp"
#include "core/gpu/vulkan/rendering/VulkanFrame.hpp"
#include "core/gpu/vulkan/swapchain/Swapchain.hpp"
#include "core/rendering/clips/TextClip.hpp"
#include "core/rendering/clips/solidClip.hpp"
#include "core/rendering/text/TextRenderer.hpp"

class GrDirectContext;

struct RenderableObject {
  std::shared_ptr<RenderableTexture> texture; // GPU texture
  ClipPushConstants pushConstants;            // model matrix, opacity, layer
};

enum class RenderNodeType { MEDIA, TEXT, SOLID };

struct VulkanRenderNode {
  RenderNodeType type;
  RenderableObject mediaObj;
  TextClip *textClip = nullptr;
  solidClip *solidObj = nullptr;
};

class Renderer {
public:
  explicit Renderer(QWindow *window, DeviceContext *context);
  ~Renderer();

  // non-copyable — owns GPU resources
  Renderer(const Renderer &) = delete;
  Renderer &operator=(const Renderer &) = delete;

  using SkiaCallback = std::function<void(uint32_t, VkSemaphore, VkSemaphore)>;
  void setSkiaCallback(SkiaCallback cb) { m_skiaCallback = std::move(cb); }

  void render(float width, float height, float panX, float panY, float zoom,
              const std::vector<VulkanRenderNode> &renderQueue,
              const std::vector<VkSemaphore> &waitSemaphores,
              const std::vector<uint64_t> &waitSemaphoreValues);

  void updateCanvasUBO(float width, float height, float panX, float panY,
                       float zoom);

  using SwapchainRecreateCallback = std::function<void()>;
  void setSwapchainRecreateCallback(SwapchainRecreateCallback cb) {
    m_swapchainRecreateCallback = std::move(cb);
  }

  // swapchain
  void recreateSwapchain();

  // Force vulkan
  void waitIdle();

  CommandPool *getCommandPool() const { return m_commandPool; }
  DescriptorPool *getDescriptorPool() const { return m_descriptorPool; }
  DescriptorSetLayout *getClipDescriptorSetLayout() const {
    return m_clipDescriptorSetLayout;
  }
  VkSampler getDefaultSampler() const { return m_defaultSampler; }

  TextRenderer *getTextRenderer() const { return m_textRenderer.get(); }
  std::shared_ptr<Texture> getDummyTexture() const { return m_dummyTexture; }

  std::vector<VkImage> getSwapchainImages() const {
    return m_swapchain->getImages();
  }

  VkFormat getSwapchainFormat() const { return m_swapchain->getImageFormat(); }

  Swapchain *getSwapchain() const { return m_swapchain; }

  VkExtent2D getSwapchainExtent() const { return m_swapchain->getExtent(); }

private:
  void init();
  void cleanup();

  void recordCommandBuffer(VkCommandBuffer cmd, uint32_t imageIndex,
                           const std::vector<VulkanRenderNode> &renderQueue);

  QWindow *m_window;
  DeviceContext *m_context = nullptr;

  Swapchain *m_swapchain = nullptr;
  RenderPass *m_renderPass = nullptr;
  Pipeline *m_graphicsPipeline = nullptr;
  Pipeline *m_solidPipeline = nullptr;
  CommandPool *m_commandPool = nullptr;
  DescriptorPool *m_descriptorPool = nullptr;
  Mesh *m_mesh = nullptr;

  DescriptorSetLayout *m_descriptorSetLayout = nullptr; // set 0 CanvasUBO
  DescriptorSetLayout *m_clipDescriptorSetLayout =
      nullptr; // set 1 per-clip texture
  VkSampler m_defaultSampler = VK_NULL_HANDLE;

  std::vector<VulkanFrame *> m_frames;
  std::vector<UniformBuffer *> m_uniformBuffers;
  std::vector<Descriptor *> m_globalDescriptors;

  std::vector<VkSemaphore> m_presentSemaphores;

  std::shared_ptr<Texture> m_dummyTexture; // dummy texture

  VkExtent2D m_swapchainExtent{};
  int currentFrame = 0;

  static constexpr int MAX_FRAMES_IN_FLIGHT = 2;

  camera m_camera;
  std::unique_ptr<TextRenderer> m_textRenderer;

  SkiaCallback m_skiaCallback;
  SwapchainRecreateCallback m_swapchainRecreateCallback;
};