from __future__ import annotations


class Compositor:
 

    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        self.width  = width
        self.height = height
        self._surface = None    

    def _getSurface(self):
        """Lazy-init so skia import only happens when actually needed."""
        if self._surface is None:
            import skia
            self._surface = skia.Surface(self.width, self.height)
        return self._surface

    #   Frame output  

    def compositeFrame(self, timeline, frame: int) -> bytes:
        """
        Render all tracks for `frame` and return raw RGBA bytes.
        `timeline` is a Timeline instance.

        Returns: bytes of length (width * height * 4) — raw RGBA8888
        """
        import skia

        surface = self._getSurface()
        canvas  = surface.getCanvas()

         
        canvas.clear(skia.ColorBLACK)

         
        for track in reversed(timeline.tracks):
            if track.muted:
                continue
            clip = track.clipAt(frame)
            if clip is None:
                continue

             
            canvas.saveLayer(None, None)
            clip.render(canvas, frame)
            canvas.restore()    

         
        image = surface.makeImageSnapshot()
        info  = skia.ImageInfo.MakeN32Premul(self.width, self.height)
        buf   = bytearray(self.width * self.height * 4)
        image.readPixels(info, buf, self.width * 4, 0, 0)
        return bytes(buf)

    def compositeFrameJpeg(self, timeline, frame: int, quality: int = 80) -> bytes:
         
        import skia

        surface = self._getSurface()
        canvas  = surface.getCanvas()
        canvas.clear(skia.ColorBLACK)

        for track in reversed(timeline.tracks):
            if track.muted:
                continue
            clip = track.clipAt(frame)
            if clip:
                canvas.saveLayer(None, None)
                clip.render(canvas, frame)
                canvas.restore()

        image = surface.makeImageSnapshot()
        return image.encodeToData(skia.kJPEG, quality).bytes()

    # Thumbnail  

    def renderThumbnail(
        self,
        timeline,
        frame: int,
        thumbW: int = 320,
        thumbH: int = 180,
    ) -> bytes:
        
        import skia

        thumbSurface = skia.Surface(thumbW, thumbH)
        canvas       = thumbSurface.getCanvas()
        canvas.clear(skia.ColorBLACK)

         
        scaleX = thumbW / self.width
        scaleY = thumbH / self.height
        canvas.scale(scaleX, scaleY)

        for track in reversed(timeline.tracks):
            if track.muted:
                continue
            clip = track.clipAt(frame)
            if clip:
                canvas.saveLayer(None, None)
                clip.render(canvas, frame)
                canvas.restore()

        image = thumbSurface.makeImageSnapshot()
        return image.encodeToData(skia.kJPEG, 75).bytes()

    def __repr__(self) -> str:
        return f"Compositor({self.width}x{self.height})"
