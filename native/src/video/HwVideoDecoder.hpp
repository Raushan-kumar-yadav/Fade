#pragma once
#include "gpu/vulkan/device/DeviceContext.hpp"
#include "video/baseDecoder.hpp"


#include <chrono>
#include <iostream>

extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/hwcontext.h>
#include <libavutil/hwcontext_vulkan.h>
#include <libavutil/imgutils.h>
#include <libswscale/swscale.h>
}
class HWVideoDecoder : public baseDecoder {
public:
  HWVideoDecoder(const std::string &filepath, DeviceContext *context,
                 float previewScale = 1.0f);
  ~HWVideoDecoder() override;

  std::shared_ptr<DecodedFrame> decodeFrame(int64_t targetFrame) override;

  bool decodeFrameDirect(int64_t targetFrame, uint8_t *dstBuffer, int dstW,
                         int dstH) override;

  int getWidth() const override { return m_width; }
  int getHeight() const override { return m_height; }
  double getFps() const override { return m_fps; }
  double getDuration() const override { return m_duration; }

private:
  void initHardwareContext();
  static AVPixelFormat getHwFormat(AVCodecContext *ctx,
                                   const AVPixelFormat *pix_fmts);
  static AVPixelFormat get_format_callback(AVCodecContext *ctx,
                                           const AVPixelFormat *pix_fmts);
  int m_height = 0, m_width = 0, m_channels = 4;
  int m_srcWidth = 0, m_srcHeight = 0; // native video dimensions
  float m_previewScale = 1.0f;         // 0.5 = decode at half res
  double m_duration;

  DeviceContext *m_context = nullptr;
  AVFormatContext *m_formatCtx = nullptr;
  AVCodecContext *m_codecCtx = nullptr;
  AVBufferRef *m_hwDeviceCtx = nullptr;
  double m_fps = 0.0;
  AVRational m_timeBase{0, 1};
  int m_lastDecodedFrame = -1;
  int m_videoStreamIndex = -1;
  bool m_hwaccelFailed = false;

  SwsContext *m_swsCtx = nullptr;
  AVFrame *m_rgbFrame = nullptr;
  uint8_t *m_rgbBuffer = nullptr;
};
