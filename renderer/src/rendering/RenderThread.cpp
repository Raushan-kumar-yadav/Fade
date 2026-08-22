#include "RenderThread.hpp"
#include "Renderer.hpp"
#include "compositor/Compositor.hpp"
#include <algorithm>
#include <chrono>

using namespace std::chrono;

RenderThread::RenderThread() : m_compositor(nullptr) {}

RenderThread::~RenderThread() { stop(); }

void RenderThread::setViewportParam(int w, int h, float panX, float panY,
                                    float zoom) {
  int newW = std::max(1, w);
  int newH = std::max(1, h);

  if (newW != m_width.load() || newH != m_height.load())
    m_resizePending = true;

  m_width = newW;
  m_height = newH;
  m_panX = panX;
  m_panY = panY;
  m_zoom = zoom;
}

void RenderThread::start() {
  if (m_running.load())
    return;
  m_running = true;
  m_thread = std::thread(&RenderThread::loop, this);
}

void RenderThread::stop() {
  if (!m_running.load())
    return;
  m_running = false;
  if (m_thread.joinable())
    m_thread.join();
}

void RenderThread::loop() {
  constexpr auto kTargetFrame = duration_cast<nanoseconds>(milliseconds(16));

  while (m_running.load()) {
    auto frameStart = high_resolution_clock::now();

    if (!m_compositor) {
      std::this_thread::sleep_for(milliseconds(4));
      continue;
    }

    if (m_resizePending.exchange(false)) {
      Renderer *r = m_compositor->getRenderer();
      if (r)
        r->recreateSwapchain();
    }

    m_compositor->tick(static_cast<float>(m_width.load()),
                       static_cast<float>(m_height.load()), m_panX.load(),
                       m_panY.load(), m_zoom.load());

    auto elapsed = high_resolution_clock::now() - frameStart;
    if (elapsed < kTargetFrame)
      std::this_thread::sleep_for(kTargetFrame - elapsed);
  }
}
