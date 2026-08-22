#include "Renderer.hpp"
#include "core/api/Logger.hpp"
#include "core/rendering/clips/solidClip.hpp"

#include "core/SkCanvas.h"
#include "gpu/MutableTextureState.h"
#include "gpu/ganesh/GrBackendSemaphore.h"
#include "gpu/ganesh/GrDirectContext.h"
#include "gpu/ganesh/vk/GrVkBackendSemaphore.h"
#include "gpu/vk/VulkanMutableTextureState.h"

#include <glm/glm.hpp>
#include <glm/gtc/matrix_transform.hpp>
#include <stdexcept>

Renderer::Renderer(QWindow *window, DeviceContext *context)
    : m_window(window), m_context(context) {
  init();
}

Renderer::~Renderer() { cleanup(); }

void Renderer::init() {

  LOG_INFO("Starting Rendere");

  // Core Vulkan
  m_swapchain = new Swapchain(m_context, m_window->width(), m_window->height());
  m_renderPass = new RenderPass(m_context, m_swapchain->getImageFormat());
  m_swapchain->setupFramebuffers(m_renderPass->getHandle());
  m_swapchainExtent = m_swapchain->getExtent();
  m_presentSemaphores.resize(m_swapchain->getImageCount());

  VkSemaphoreCreateInfo semaphoreInfo{};
  semaphoreInfo.sType = VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO;
  for (size_t i = 0; i < m_presentSemaphores.size(); i++) {
    if (vkCreateSemaphore(m_context->getLogicalDevice(), &semaphoreInfo,
                          nullptr, &m_presentSemaphores[i]) != VK_SUCCESS) {
      throw std::runtime_error("Failed to create present semaphores!");
    }
  }

  VkPushConstantRange pushConstant{};
  pushConstant.stageFlags =
      VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT;
  pushConstant.offset = 0;
  pushConstant.size = sizeof(ClipPushConstants);

  // Set 0 layout â€” global CanvasUBO
  std::vector<VkDescriptorSetLayoutBinding> globalBindings = {
      {0, VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, 1, VK_SHADER_STAGE_VERTEX_BIT,
       nullptr}};

  // Set 1 layout â€” per-clip texture sampler
  std::vector<VkDescriptorSetLayoutBinding> clipBindings = {
      // Binding 0: Y Plane
      {0, VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 1,
       VK_SHADER_STAGE_FRAGMENT_BIT, nullptr},
      // Binding 1: U Plane
      {1, VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 1,
       VK_SHADER_STAGE_FRAGMENT_BIT, nullptr},
      // Binding 2: V Plane
      {2, VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 1,
       VK_SHADER_STAGE_FRAGMENT_BIT, nullptr}};

  m_descriptorSetLayout = new DescriptorSetLayout(m_context, globalBindings);
  m_clipDescriptorSetLayout = new DescriptorSetLayout(m_context, clipBindings);

  // Pipeline
  std::vector<VkDescriptorSetLayout> allLayouts = {
      m_descriptorSetLayout->getHandle(),
      m_clipDescriptorSetLayout->getHandle()};

  PipelineConfig clipConfig;
  clipConfig.enableBlending = true;
  clipConfig.cullMode = VK_CULL_MODE_NONE;

  // Alpha-over
  clipConfig.srcColor = VK_BLEND_FACTOR_SRC_ALPHA;
  clipConfig.dstColor = VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA;
  clipConfig.srcAlpha = VK_BLEND_FACTOR_ONE;
  clipConfig.dstAlpha = VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA;

  m_graphicsPipeline = new Pipeline(
      m_context, m_renderPass->getHandle(), "resources/shaders/vert.spv",
      "resources/shaders/frag.spv", allLayouts, {pushConstant}, clipConfig);

  // --- SOLID PIPELINE ---
  VkPushConstantRange solidPushConstant{};
  solidPushConstant.stageFlags =
      VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT;
  solidPushConstant.offset = 0;
  solidPushConstant.size = sizeof(SolidPushConstants);

  std::vector<VkDescriptorSetLayout> solidLayouts = {
      m_descriptorSetLayout->getHandle()};

  PipelineConfig solidConfig;
  solidConfig.enableBlending = true;
  solidConfig.cullMode = VK_CULL_MODE_NONE;
  solidConfig.srcColor = VK_BLEND_FACTOR_SRC_ALPHA;
  solidConfig.dstColor = VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA;
  solidConfig.srcAlpha = VK_BLEND_FACTOR_ONE;
  solidConfig.dstAlpha = VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA;

  m_solidPipeline = new Pipeline(
      m_context, m_renderPass->getHandle(), "resources/shaders/solid_vert.spv",
      "resources/shaders/solid_frag.spv", solidLayouts, {solidPushConstant},
      solidConfig);

  // Command pool + frames
  m_commandPool =
      new CommandPool(m_context, m_context->getGraphicsQueueFamilyIndex(),
                      VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT);

  m_frames.reserve(MAX_FRAMES_IN_FLIGHT);
  for (int i = 0; i < MAX_FRAMES_IN_FLIGHT; i++)
    m_frames.push_back(new VulkanFrame(m_context, m_commandPool));

  // Descriptor pool
  std::vector<VkDescriptorPoolSize> poolSizes = {
      {VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, 100},
      {VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 3000}};
  m_descriptorPool = new DescriptorPool(m_context, 1100, poolSizes);

  // Set 0: CanvasUBO descriptor per frame
  m_uniformBuffers.resize(MAX_FRAMES_IN_FLIGHT);
  m_globalDescriptors.resize(MAX_FRAMES_IN_FLIGHT);

  for (int i = 0; i < MAX_FRAMES_IN_FLIGHT; i++) {
    m_uniformBuffers[i] = new UniformBuffer(m_context, sizeof(CanvasUBO));

    m_globalDescriptors[i] =
        new Descriptor(m_context, m_descriptorPool, m_descriptorSetLayout);
    m_globalDescriptors[i]->updateBufferDescriptor(
        m_uniformBuffers[i]->getHandle(), 0, sizeof(CanvasUBO), 0);
  }

  // Quad mesh â€” shared by ALL clips, bound once per frame
  std::vector<Vertex> vertices = {
      {{-0.5f, -0.5f, 0.0f}, {1.0f, 1.0f, 1.0f}, {0.0f, 0.0f}},
      {{0.5f, -0.5f, 0.0f}, {1.0f, 1.0f, 1.0f}, {1.0f, 0.0f}},
      {{0.5f, 0.5f, 0.0f}, {1.0f, 1.0f, 1.0f}, {1.0f, 1.0f}},
      {{-0.5f, 0.5f, 0.0f}, {1.0f, 1.0f, 1.0f}, {0.0f, 1.0f}}};
  std::vector<uint32_t> indices = {0, 3, 2, 2, 1, 0};

  m_mesh = new Mesh(m_context, m_context->getGraphicQueue(),
                    m_commandPool->getHandle(), &vertices, &indices);

  VkSamplerCreateInfo samplerInfo{};
  samplerInfo.sType = VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO;
  samplerInfo.magFilter = VK_FILTER_LINEAR;
  samplerInfo.minFilter = VK_FILTER_LINEAR;
  samplerInfo.addressModeU = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE;
  samplerInfo.addressModeV = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE;
  samplerInfo.addressModeW = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE;
  samplerInfo.anisotropyEnable = VK_FALSE;
  samplerInfo.borderColor = VK_BORDER_COLOR_INT_OPAQUE_BLACK;
  samplerInfo.unnormalizedCoordinates = VK_FALSE;
  samplerInfo.compareEnable = VK_FALSE;
  samplerInfo.compareOp = VK_COMPARE_OP_ALWAYS;
  samplerInfo.mipmapMode = VK_SAMPLER_MIPMAP_MODE_LINEAR;

  if (vkCreateSampler(m_context->getLogicalDevice(), &samplerInfo, nullptr,
                      &m_defaultSampler) != VK_SUCCESS) {
    throw std::runtime_error("Failed to create default hardware sampler!");
  }

  m_textRenderer = std::make_unique<TextRenderer>(
      m_context, m_renderPass->getHandle(), m_descriptorSetLayout->getHandle());

  uint8_t dummyPixels[4] = {0, 0, 0, 0}; // 1x1 Transparent Black Pixel

  m_dummyTexture = std::make_shared<Texture>(
      m_context, *m_commandPool, m_context->getGraphicQueue(), dummyPixels, 4,
      1, // width
      1, // height
      4);

  LOG_INFO("Renderer initialized.");
}

void Renderer::render(float width, float height, float panX, float panY,
                      float zoom,
                      const std::vector<VulkanRenderNode> &renderQueue,
                      const std::vector<VkSemaphore> &waitSemaphores,
                      const std::vector<uint64_t> &waitSemaphoreValues) {
  VulkanFrame *frame = m_frames[currentFrame];
  frame->waitForReady();

  uint32_t imageIndex;
  VkResult result = vkAcquireNextImageKHR(
      m_context->getLogicalDevice(), m_swapchain->getHandle(), UINT64_MAX,
      frame->getImageAvailableSemaphore(), VK_NULL_HANDLE, &imageIndex);

  if (result == VK_ERROR_OUT_OF_DATE_KHR) {
    recreateSwapchain();
    return;
  }

  frame->reset();

  if (m_skiaCallback) {

    m_skiaCallback(imageIndex, frame->getImageAvailableSemaphore(),
                   m_presentSemaphores[imageIndex]);

    VkCommandBuffer cmd = frame->getCommandBuffer()->getHandle();
    VkCommandBufferBeginInfo beginInfo{};
    beginInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
    vkBeginCommandBuffer(cmd, &beginInfo);
    vkEndCommandBuffer(cmd);

    VkSubmitInfo fenceSubmit{};
    fenceSubmit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
    fenceSubmit.commandBufferCount = 1;
    fenceSubmit.pCommandBuffers = &cmd;

    m_context->lockGraphicsQueue();
    vkQueueSubmit(m_context->getGraphicQueue(), 1, &fenceSubmit,
                  frame->getInFlightFence());

    VkSwapchainKHR swapchains[] = {m_swapchain->getHandle()};
    VkPresentInfoKHR presentInfo{};
    presentInfo.sType = VK_STRUCTURE_TYPE_PRESENT_INFO_KHR;
    presentInfo.waitSemaphoreCount = 1;
    presentInfo.pWaitSemaphores = &m_presentSemaphores[imageIndex];
    presentInfo.swapchainCount = 1;
    presentInfo.pSwapchains = swapchains;
    presentInfo.pImageIndices = &imageIndex;
    vkQueuePresentKHR(m_context->getPresentQueue(), &presentInfo);
    m_context->unlockGraphicsQueue();

    currentFrame = (currentFrame + 1) % MAX_FRAMES_IN_FLIGHT;
    return;
  }

  //  OLD VULKAN PIPELINE PATH
  VkCommandBuffer cmd = frame->getCommandBuffer()->getHandle();
  recordCommandBuffer(cmd, imageIndex, renderQueue);

  // SEMAPHORE WAITING
  std::vector<VkSemaphore> submitWaitSemaphores;
  std::vector<VkPipelineStageFlags> submitWaitStages;

  //  Wait for the Monitor
  submitWaitSemaphores.push_back(frame->getImageAvailableSemaphore());
  submitWaitStages.push_back(VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT);

  // Wait for FFmpeg Hardware Decoders
  for (VkSemaphore sem : waitSemaphores) {
    if (sem != VK_NULL_HANDLE) {
      submitWaitSemaphores.push_back(sem);
      submitWaitStages.push_back(VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT);
    }
  }

  VkSemaphore signalSems[] = {m_presentSemaphores[imageIndex]};

  std::vector<uint64_t> waitValues;
  waitValues.push_back(0); // imageAvailable is binary, value ignored
  for (size_t i = 0; i < waitSemaphores.size(); ++i) {
    if (i < waitSemaphoreValues.size()) {
      waitValues.push_back(waitSemaphoreValues[i]);
    } else {
      waitValues.push_back(0);
    }
  }
  uint64_t signalValue = 0; // signal semaphore is binary

  VkTimelineSemaphoreSubmitInfo timelineInfo{};
  timelineInfo.sType = VK_STRUCTURE_TYPE_TIMELINE_SEMAPHORE_SUBMIT_INFO;
  timelineInfo.waitSemaphoreValueCount =
      static_cast<uint32_t>(waitValues.size());
  timelineInfo.pWaitSemaphoreValues = waitValues.data();
  timelineInfo.signalSemaphoreValueCount = 1;
  timelineInfo.pSignalSemaphoreValues = &signalValue;

  VkSubmitInfo submitInfo{};
  submitInfo.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
  submitInfo.pNext = &timelineInfo;
  submitInfo.waitSemaphoreCount =
      static_cast<uint32_t>(submitWaitSemaphores.size());
  submitInfo.pWaitSemaphores = submitWaitSemaphores.data();
  submitInfo.pWaitDstStageMask = submitWaitStages.data();
  submitInfo.commandBufferCount = 1;
  submitInfo.pCommandBuffers = &cmd;
  submitInfo.signalSemaphoreCount = 1;
  submitInfo.pSignalSemaphores = signalSems;

  m_context->lockGraphicsQueue();
  if (vkQueueSubmit(m_context->getGraphicQueue(), 1, &submitInfo,
                    frame->getInFlightFence()) != VK_SUCCESS) {
    m_context->unlockGraphicsQueue();
    throw std::runtime_error("Failed to submit draw command buffer!");
  }

  VkSwapchainKHR swapchains[] = {m_swapchain->getHandle()};
  VkPresentInfoKHR presentInfo{};
  presentInfo.sType = VK_STRUCTURE_TYPE_PRESENT_INFO_KHR;
  presentInfo.waitSemaphoreCount = 1;
  presentInfo.pWaitSemaphores = signalSems;
  presentInfo.swapchainCount = 1;
  presentInfo.pSwapchains = swapchains;
  presentInfo.pImageIndices = &imageIndex;

  vkQueuePresentKHR(m_context->getPresentQueue(), &presentInfo);
  m_context->unlockGraphicsQueue();

  currentFrame = (currentFrame + 1) % MAX_FRAMES_IN_FLIGHT;
}

// RECORD COMMAND BUFFER
void Renderer::recordCommandBuffer(
    VkCommandBuffer cmd, uint32_t imageIndex,
    const std::vector<VulkanRenderNode>
        &renderQueue) // Changed parameter to unified queue
{
  VkCommandBufferBeginInfo beginInfo{};
  beginInfo.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
  vkBeginCommandBuffer(cmd, &beginInfo);

  //   TRANSITION FFMPEG VRAM TO SHADER-READABLE LAYOUT
  std::vector<VkImageMemoryBarrier> barriers;

  for (const auto &node : renderQueue) {
    // Only check barriers for Media objects
    if (node.type == RenderNodeType::MEDIA) {
      const auto &obj = node.mediaObj;
    }
  }

  if (!barriers.empty()) {
    vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
                         VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT, 0, 0, nullptr,
                         0, nullptr, static_cast<uint32_t>(barriers.size()),
                         barriers.data());
  }

  // 2. BEGIN RENDER PASS
  VkClearValue clearColor = {{{0.0f, 0.0f, 0.0f, 1.0f}}};

  VkRenderPassBeginInfo renderPassInfo{};
  renderPassInfo.sType = VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO;
  renderPassInfo.renderPass = m_renderPass->getHandle();
  renderPassInfo.framebuffer = m_swapchain->getFramebuffer(imageIndex);
  renderPassInfo.renderArea.offset = {0, 0};
  renderPassInfo.renderArea.extent = m_swapchain->getExtent();
  renderPassInfo.clearValueCount = 1;
  renderPassInfo.pClearValues = &clearColor;

  vkCmdBeginRenderPass(cmd, &renderPassInfo, VK_SUBPASS_CONTENTS_INLINE);

  // Viewport + scissor (Shared across all pipelines)
  VkViewport viewport{};
  viewport.x = 0.0f;
  viewport.y = 0.0f;
  viewport.width = static_cast<float>(m_swapchain->getExtent().width);
  viewport.height = static_cast<float>(m_swapchain->getExtent().height);
  viewport.minDepth = 0.0f;
  viewport.maxDepth = 1.0f;
  vkCmdSetViewport(cmd, 0, 1, &viewport);

  VkRect2D scissor{};
  scissor.offset = {0, 0};
  scissor.extent = m_swapchain->getExtent();
  vkCmdSetScissor(cmd, 0, 1, &scissor);

  VkDescriptorSet globalSet = m_globalDescriptors[currentFrame]->getHandle();

  RenderNodeType currentPipeline = RenderNodeType::TEXT;
  bool firstBind = true;

  for (const auto &node : renderQueue) {

    if (node.type == RenderNodeType::MEDIA) {
      if (currentPipeline != RenderNodeType::MEDIA || firstBind) {
        m_graphicsPipeline->bind(cmd);

        VkBuffer vertexBuffers[] = {m_mesh->getVertexBuffer()};
        VkDeviceSize offsets[] = {0};
        vkCmdBindVertexBuffers(cmd, 0, 1, vertexBuffers, offsets);
        vkCmdBindIndexBuffer(cmd, m_mesh->getIndexBuffer(), 0,
                             VK_INDEX_TYPE_UINT32);

        // Bind Canvas UBO
        vkCmdBindDescriptorSets(cmd, VK_PIPELINE_BIND_POINT_GRAPHICS,
                                m_graphicsPipeline->getLayoutHandle(), 0, 1,
                                &globalSet, 0, nullptr);

        currentPipeline = RenderNodeType::MEDIA;
        firstBind = false;
      }

      // Draw the media clip
      if (node.mediaObj.texture && node.mediaObj.texture->descriptor) {
        vkCmdPushConstants(
            cmd, m_graphicsPipeline->getLayoutHandle(),
            VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT, 0,
            sizeof(ClipPushConstants), &node.mediaObj.pushConstants);

        VkDescriptorSet clipSet =
            node.mediaObj.texture->descriptor->getHandle();
        vkCmdBindDescriptorSets(cmd, VK_PIPELINE_BIND_POINT_GRAPHICS,
                                m_graphicsPipeline->getLayoutHandle(), 1, 1,
                                &clipSet, 0, nullptr);

        vkCmdDrawIndexed(cmd, m_mesh->getIndexCount(), 1, 0, 0, 0);
      }

    } else if (node.type == RenderNodeType::TEXT) {
      if (currentPipeline != RenderNodeType::TEXT || firstBind) {
        if (m_textRenderer) {
          m_textRenderer->bindPipeline(cmd, globalSet);
        }
        currentPipeline = RenderNodeType::TEXT;
        firstBind = false;
      }

      if (m_textRenderer && node.textClip) {
        m_textRenderer->drawSingleClip(cmd, node.textClip);
      }

    } else if (node.type == RenderNodeType::SOLID) {
      // -- SOLID PIPELINE STATE --
      if (currentPipeline != RenderNodeType::SOLID || firstBind) {
        m_solidPipeline->bind(cmd);

        VkBuffer vertexBuffers[] = {m_mesh->getVertexBuffer()};
        VkDeviceSize offsets[] = {0};
        vkCmdBindVertexBuffers(cmd, 0, 1, vertexBuffers, offsets);
        vkCmdBindIndexBuffer(cmd, m_mesh->getIndexBuffer(), 0,
                             VK_INDEX_TYPE_UINT32);

        vkCmdBindDescriptorSets(cmd, VK_PIPELINE_BIND_POINT_GRAPHICS,
                                m_solidPipeline->getLayoutHandle(), 0, 1,
                                &globalSet, 0, nullptr);

        currentPipeline = RenderNodeType::SOLID;
        firstBind = false;
      }

      if (node.solidObj) {
        const SolidPushConstants &pc = node.solidObj->getPushConstants();
        vkCmdPushConstants(cmd, m_solidPipeline->getLayoutHandle(),
                           VK_SHADER_STAGE_VERTEX_BIT |
                               VK_SHADER_STAGE_FRAGMENT_BIT,
                           0, sizeof(SolidPushConstants), &pc);

        vkCmdDrawIndexed(cmd, m_mesh->getIndexCount(), 1, 0, 0, 0);
      }
    }
  }

  // 4. END RENDER PASS
  vkCmdEndRenderPass(cmd);
  vkEndCommandBuffer(cmd);
}

// UPDATE CANVAS UBO
void Renderer::updateCanvasUBO(float width, float height, float panX,
                               float panY, float zoom) {
  m_camera.updateViewport(width, height);
  m_camera.setZoom(zoom);
  m_camera.setPosition(glm::vec3(panX, panY, 500.0f));

  CanvasUBO ubo{};
  ubo.view = m_camera.getViewMatrix();
  ubo.orthoProj = m_camera.getOrthoProjection();
  ubo.perspProj = m_camera.getPerspProjection();

  m_uniformBuffers[currentFrame]->update(&ubo, sizeof(ubo));
}

void Renderer::recreateSwapchain() {
  vkDeviceWaitIdle(m_context->getLogicalDevice());

  for (auto sem : m_presentSemaphores) {
    vkDestroySemaphore(m_context->getLogicalDevice(), sem, nullptr);
  }
  m_presentSemaphores.clear();

  if (m_window->width() == 0 || m_window->height() == 0)
    return;

  delete m_swapchain;
  m_swapchain = new Swapchain(m_context, m_window->width(), m_window->height());
  m_swapchain->setupFramebuffers(m_renderPass->getHandle());
  m_swapchainExtent = m_swapchain->getExtent();

  m_presentSemaphores.resize(m_swapchain->getImageCount());
  VkSemaphoreCreateInfo semaphoreInfo{};
  semaphoreInfo.sType = VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO;
  for (size_t i = 0; i < m_presentSemaphores.size(); i++) {
    vkCreateSemaphore(m_context->getLogicalDevice(), &semaphoreInfo, nullptr,
                      &m_presentSemaphores[i]);
  }

  LOG_INFO("Swapchain recreated.");
  if (m_swapchainRecreateCallback) {
    m_swapchainRecreateCallback();
  }
}

void Renderer::waitIdle() { vkDeviceWaitIdle(m_context->getLogicalDevice()); }

// CLEANUP
void Renderer::cleanup() {
  vkDeviceWaitIdle(m_context->getLogicalDevice());

  delete m_mesh;

  for (auto *d : m_globalDescriptors)
    delete d;
  m_globalDescriptors.clear();

  for (auto *u : m_uniformBuffers)
    delete u;
  m_uniformBuffers.clear();

  delete m_descriptorPool;
  delete m_descriptorSetLayout;
  delete m_clipDescriptorSetLayout;

  for (auto *f : m_frames)
    delete f;
  m_frames.clear();

  if (m_defaultSampler != VK_NULL_HANDLE) {
    vkDestroySampler(m_context->getLogicalDevice(), m_defaultSampler, nullptr);
  }
  for (auto sem : m_presentSemaphores) {
    vkDestroySemaphore(m_context->getLogicalDevice(), sem, nullptr);
  }
  m_presentSemaphores.clear();

  delete m_commandPool;
  delete m_graphicsPipeline;
  delete m_solidPipeline;
  delete m_renderPass;
  delete m_swapchain;
}
