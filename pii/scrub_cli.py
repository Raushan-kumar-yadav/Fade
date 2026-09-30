import sys, json
from pathlib import Path
from scrubber import scrub_text, scrub_image, scrub_video

TEXT = {".txt", ".md", ".log", ".csv", ".json"}
IMG = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
VID = {".mp4", ".avi", ".mov", ".mkv"}

def main(path, mode="pseudonym"):
    src = Path(path).resolve()
    ext = src.suffix.lower()
    out_ext = '.mp4' if ext in VID else ext
    out = src.parent / f"sanitized_{src.stem}{out_ext}"

    if ext in TEXT:
        clean, report = scrub_text(src.read_text(encoding="utf-8", errors="ignore"), mode)
        out.write_text(clean, encoding="utf-8")
    elif ext in IMG:
        report = scrub_image(src, out)
    elif ext in VID:
        report = scrub_video(src, out)
    else:
        sys.exit(f"Unsupported file type: {ext}")

    # Report saved next to sanitized file
    report_out = src.parent / f"sanitized_{src.stem}.report.json"
    report_out.write_text(json.dumps(report, indent=2))
    print(f"Sanitized file: {out}\nReport: {report_out}\nFindings: {len(report)}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "pseudonym")
