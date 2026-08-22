#include "core/api/Logger.hpp"
#include "video/baseDecoder.hpp"
#include <iostream>

extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/hwcontext_vulkan.h>
#include <libavutil/imgutils.h>
#include <libswscale/swscale.h>

}

class videoDecoder : public baseDecoder {
private:
  std::string m_filepath;
  int m_height = 0, m_width = 0, m_channels = 4;
  double m_duration;
  double m_fps = 0.0;
  AVRational m_timeBase = {0, 1};

  AVFormatContext *m_formatCtx = nullptr;
  AVCodecContext *m_codecCtx = nullptr;
  const AVCodec *m_videoCodex = nullptr;

  // Get raw packet from strem and store in this
  AVPacket *m_packet = nullptr;

  // Decompressed it and store in this
  AVFrame *m_frame = nullptr;

  // YUV to RGBA engine
  SwsContext *m_swsCtx = nullptr;

  // hold converted rgpa frame
  AVFrame *m_rgbFrame = nullptr;

  // The raw memory array
  uint8_t *m_rgbBuffer = nullptr;

  int64_t m_lastDecodedFrame = -1;

  // Tracks the last sws context
  int m_lastSwsFmt = -1;
  int m_lastSwsW = 0;
  int m_lastSwsH = 0;

  int m_videoStreamIndex = -1;

public:
  videoDecoder(const std::string &filePath);
  ~videoDecoder() override;

  std::shared_ptr<DecodedFrame> decodeFrame(int64_t frameNumber) override;
  int getWidth() const override;
  int getHeight() const override;
  double getDuration() const override;
  double getFps() const override;
};
