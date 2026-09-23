# FADE Image Editor Tools API Contract

This document outlines the API contract for the frontend to integrate with the backend's newly implemented image editor tools (Selection, Crop, Brush, Eraser).

## General Concepts

### Coordinate System & Units
- All coordinates (`x`, `y`, `width`, `height`, point positions) must be provided in **canonical design-space pixels** (typically mapping to a 1920x1080 canvas).
- Do **not** send raw screen, viewport, or CSS coordinates. The frontend must normalize pan, zoom, and display density offsets before transmitting the geometry.

### Undo/Redo Integration
- All operations documented below (`POST /editor/selection`, `/editor/crop`, `/editor/brush`, `/editor/eraser`) automatically push `Command` instances to the canonical FADE `CommandStack`.
- If the frontend triggers `POST /history/undo` or `POST /history/redo`, the backend will flawlessly restore the prior state or timeline configuration. The frontend should subsequently refetch active selections or composition visuals.

---

## 1. Selection Management

### Create or Update Selection
- **Endpoint**: `/editor/selection`
- **HTTP Method**: `POST`
- **Request Schema**:
  - `shape_type` (Required, string): Must be one of `rect`, `ellipse`, `lasso`, `polygon`.
  - `data` (Required, object): The geometry payload corresponding to the `shape_type`.
    - For `rect` and `ellipse`: `{"x": float, "y": float, "w": float, "h": float}`
    - For `lasso` and `polygon`: `{"points": [{"x": float, "y": float}, ...]}`
- **Validation Rules**: Missing or malformed payloads will yield a standard FastAPI 422 Validation Error.
- **Undo/Redo**: Pushes a `SetSelectionCommand`.
- **Example Request**:
  ```json
  {
    "shape_type": "rect",
    "data": { "x": 100, "y": 200, "w": 500, "h": 300 }
  }
  ```
- **Example Response**:
  ```json
  {
    "status": "ok",
    "selection": {
      "shape_type": "rect",
      "data": { "x": 100, "y": 200, "w": 500, "h": 300 }
    }
  }
  ```

### Get Current Selection
- **Endpoint**: `/editor/selection`
- **HTTP Method**: `GET`
- **Response Schema**: Returns the active selection or `null` if none exists.
- **Example Response**:
  ```json
  {
    "selection": null
  }
  ```

### Clear Selection
- **Endpoint**: `/editor/selection`
- **HTTP Method**: `DELETE`
- **Response Schema**: `{"status": "ok", "selection": null}`
- **Undo/Redo**: Pushes a `SetSelectionCommand` targeting `None`.

---

## 2. Crop Composition

### Crop Project
- **Endpoint**: `/editor/crop`
- **HTTP Method**: `POST`
- **Request Schema**:
  - `x` (Required, float): Top-left origin X of the crop box.
  - `y` (Required, float): Top-left origin Y of the crop box.
  - `width` (Required, float): Width of the crop box.
  - `height` (Required, float): Height of the crop box.
- **Validation Rules**: `width` and `height` must be > 0.
- **Undo/Redo**: Pushes a `CropProjectCommand`. Undoing restores previous global timeline dimensions and reverts clip translations.
- **Behavior**: Translates the active `Timeline` bounding dimensions and natively offsets all existing `clip` positions by `-x` and `-y`, executing a non-destructive crop that forces the compositor to generate updated Skia dimensions.
- **Example Request**:
  ```json
  {
    "x": 120, "y": 60, "width": 1080, "height": 720
  }
  ```
- **Example Response**:
  ```json
  {
    "status": "ok",
    "width": 1080, "height": 720
  }
  ```
- **Error Response**:
  ```json
  {
    "status": "error",
    "message": "Invalid crop dimensions"
  }
  ```

---

## 3. Brush Stroke

### Add Brush Stroke
- **Endpoint**: `/editor/brush`
- **HTTP Method**: `POST`
- **Request Schema**:
  - `points` (Required, array): Ordered list of `{"x": float, "y": float}` defining the stroke path.
  - `size` (Required, float): Stroke width.
  - `color` (Optional, array): RGBA float list `[r, g, b, a]`. Defaults to `[1.0, 1.0, 1.0, 1.0]`.
  - `opacity` (Optional, float): Stroke opacity scalar (0.0 - 1.0). Defaults to `1.0`.
- **Validation Rules**: `points` array must not be empty.
- **Undo/Redo**: Pushes an `AddBrushStrokeCommand`.
- **Behavior**: Commits a custom path via FADE's `PenClip` injected into the top track, which instructs the Skia `Compositor` to rasterize the stroke non-destructively over the video frame.
- **Example Request**:
  ```json
  {
    "points": [{"x": 10, "y": 10}, {"x": 50, "y": 60}],
    "size": 15.5,
    "color": [1.0, 0.0, 0.0, 1.0],
    "opacity": 0.8
  }
  ```
- **Example Response**:
  ```json
  {
    "status": "ok"
  }
  ```

---

## 4. Eraser Stroke

### Add Eraser Stroke
- **Endpoint**: `/editor/eraser`
- **HTTP Method**: `POST`
- **Request Schema**: Same parameters as `/editor/brush`. (`color` is ignored).
  - `points` (Required, array)
  - `size` (Required, float)
  - `opacity` (Optional, float)
- **Validation Rules**: `points` array must not be empty.
- **Undo/Redo**: Pushes an `AddBrushStrokeCommand` flagged as an eraser.
- **Behavior / Limitations**: 
  - Submits a stroke bounded to a `PenClip` appended to the top track. The backend configures this clip's style property to use `skia.BlendMode.kClear`.
  - **IMPORTANT LIMITATION**: Because FADE processes this as a timeline overlay utilizing the `kClear` blend mode, the eraser natively **punches through all existing layers/clips beneath it**, exposing the composition's background. It currently does not target a specific image layer exclusively.
- **Example Request**:
  ```json
  {
    "points": [{"x": 100, "y": 100}, {"x": 200, "y": 200}],
    "size": 40.0
  }
  ```
- **Example Response**:
  ```json
  {
    "status": "ok"
  }
  ```
