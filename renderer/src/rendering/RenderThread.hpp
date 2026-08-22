#pragma once
#include <atomic>
#include <thread>

class Compositor;
class Renderer;

class RenderThread {
public:
  RenderThread();
  ~RenderThread();

  // Non-copyable
  RenderThread(const RenderThread &) = delete;
  RenderThread &operator=(const RenderThread &) = delete;

  void setCompositor(Compositor *c) { m_compositor = c; }

  void setViewportParam(int w, int h, float panX, float panY, float zoom);

  void start();
  void stop();

  bool isRunning() const { return m_running.load(); }

private:
  void loop();

  Compositor *m_compositor;
  std::thread m_thread;
  std::atomic<bool> m_running{false};
  std::atomic<int> m_width{1};
  std::atomic<int> m_height{1};
  std::atomic<float> m_panX{0.f};
  std::atomic<float> m_panY{0.f};
  std::atomic<float> m_zoom{1.f};
  std::atomic<bool> m_resizePending{false};
};
