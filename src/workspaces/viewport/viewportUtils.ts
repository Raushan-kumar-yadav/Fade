/**
 * viewportUtils.ts
 *
 * Shared utilities for coordinate conversions between the renderer viewport
 * and the actual composition space.
 */

/**
 * Maps a pointer coordinate from the fixed 1920x1080 renderer viewport
 * to the actual backend composition coordinate space.
 * 
 * The C++ renderer hardcodes its output to 1920x1080 and letterboxes
 * (object-fit: contain) any compositions that don't match that aspect ratio.
 * This function reverses that transformation so that backend tools (like
 * Brush or Vector Pen) receive coordinates relative to the composition itself.
 * 
 * @param viewportX The X coordinate in the 1920x1080 viewport
 * @param viewportY The Y coordinate in the 1920x1080 viewport
 * @param compW The actual composition width (e.g. 1080)
 * @param compH The actual composition height (e.g. 1920)
 * @param clamp If true, out-of-bounds (letterbox) coordinates are clamped to the edge. If false, they are returned as-is (they can be negative or exceed compW/H).
 * @returns { x, y } in composition space, or null if clamp is true and the point is completely outside the composition.
 */
export function viewportToComposition(
  viewportX: number,
  viewportY: number,
  compW: number,
  compH: number,
  ignoreOutside: boolean = true
): { x: number; y: number } | null {
  // Renderer viewport is hardcoded to 1920x1080
  const VIEWPORT_W = 1920;
  const VIEWPORT_H = 1080;

  // The C++ renderer uses object-fit: contain
  const scale = Math.min(VIEWPORT_W / compW, VIEWPORT_H / compH);
  
  // Calculate the centered offset
  const offsetX = (VIEWPORT_W - compW * scale) / 2;
  const offsetY = (VIEWPORT_H - compH * scale) / 2;

  // Inverse map the point
  let compX = (viewportX - offsetX) / scale;
  let compY = (viewportY - offsetY) / scale;

  // Boundary behavior
  if (ignoreOutside) {
    if (compX < 0 || compX > compW || compY < 0 || compY > compH) {
      return null;
    }
  }

  return { x: compX, y: compY };
}

/**
 * Maps a coordinate from the actual composition space back to the
 * fixed 1920x1080 renderer viewport.
 * 
 * Used when the frontend needs to render backend composition coordinates
 * (like loaded mask points or paths) inside a 1920x1080 overlay.
 */
export function compositionToViewport(
  compX: number,
  compY: number,
  compW: number,
  compH: number
): { x: number; y: number } {
  const VIEWPORT_W = 1920;
  const VIEWPORT_H = 1080;

  const scale = Math.min(VIEWPORT_W / compW, VIEWPORT_H / compH);
  const offsetX = (VIEWPORT_W - compW * scale) / 2;
  const offsetY = (VIEWPORT_H - compH * scale) / 2;

  return {
    x: compX * scale + offsetX,
    y: compY * scale + offsetY,
  };
}
