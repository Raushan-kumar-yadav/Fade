 
import sys, time, statistics

VIDEO = r"C:\Users\raush\Videos\2026-03-09 21-45-10.mp4"
FRAMES_TO_TEST = 30         # decode this many sequential frames per run
SCALE = 0.5                 # match production scale factor
RUNS = 3                    # repeat N times and take average

sys.path.insert(0, ".")

#   Helpers  

def bench_decoder(name, decoder, start_frame=0):
    times = []
    for _ in range(RUNS):
        t0 = time.perf_counter()
        for f in range(start_frame, start_frame + FRAMES_TO_TEST):
            frame = decoder.decodeFrame(f)
            if frame is None or not frame.valid:
                print(f"  [{name}] Frame {f} failed!")
                break
        elapsed = time.perf_counter() - t0
        fps_achieved = FRAMES_TO_TEST / elapsed
        times.append(elapsed)

    avg   = statistics.mean(times)
    best  = min(times)
    fps   = FRAMES_TO_TEST / avg
    bfps  = FRAMES_TO_TEST / best
    ms_pf = avg / FRAMES_TO_TEST * 1000

    print(f"\n{'='*55}")
    print(f"  {name}")
    print(f"{'='*55}")
    print(f" Frames decoded  : {FRAMES_TO_TEST} x {RUNS} runs")
    print(f" Avg total time  : {avg*1000:.1f} ms  ({fps:.1f} fps)")
    print(f" Best run : {best*1000:.1f} ms  ({bfps:.1f} fps)")
    print(f" Per-frame avg : {ms_pf:.2f} ms/frame")
    print(f" 60fps target : {'[PASS]' if fps >= 60 else '[FAIL]'}")
    print(f" 30fps target : {'[PASS]' if fps >= 30 else '[FAIL]'}")

    return {"name": name, "fps": fps, "ms_per_frame": ms_pf, "best_fps": bfps}


# FFmpeg Subprocess  

print(f"\nBenchmarking video: {VIDEO}")
print(f"Scale: {SCALE}  |  Frames per run: {FRAMES_TO_TEST}  |  Runs: {RUNS}\n")

from backend.media.decoder.ffmpegDecoder import FFmpegVideoDecoder
ffmpeg_dec = FFmpegVideoDecoder(VIDEO, scale_factor=SCALE)
r_ffmpeg = bench_decoder("FFmpeg Subprocess (current)", ffmpeg_dec, start_frame=0)
ffmpeg_dec.close()

#   PyAV In-Process  

try:
    from backend.media.decoder.pyavDecoder import PyAVDecoder
    pyav_dec = PyAVDecoder(VIDEO, scale_factor=SCALE)
    r_pyav = bench_decoder("PyAV In-Process (new)", pyav_dec, start_frame=0)
    pyav_dec.close()
    pyav_ok = True
except Exception as e:
    print(f"\n[PyAV] FAILED: {e}")
    r_pyav = None
    pyav_ok = False

#   Comparison  

print(f"\n{'='*55}")
print("  COMPARISON SUMMARY")
print(f"{'='*55}")
if pyav_ok and r_pyav:
    speedup = r_pyav["fps"] / r_ffmpeg["fps"]
    saved   = r_ffmpeg["ms_per_frame"] - r_pyav["ms_per_frame"]
    print(f" FFmpeg subprocess : {r_ffmpeg['fps']:.1f} fps  ({r_ffmpeg['ms_per_frame']:.2f} ms/frame)")
    print(f" PyAV in-process : {r_pyav['fps']:.1f} fps  ({r_pyav['ms_per_frame']:.2f} ms/frame)")
    print(f" Speedup : {speedup:.2f}x faster")
    print(f" Time saved : {saved:.2f} ms per frame")
    winner = "PyAV" if r_pyav["fps"] > r_ffmpeg["fps"] else "FFmpeg"
    print(f" Winner : {winner}")
else:
    print(f" FFmpeg subprocess : {r_ffmpeg['fps']:.1f} fps  ({r_ffmpeg['ms_per_frame']:.2f} ms/frame)")
    print(f" PyAV : FAILED (see above)")
print()

