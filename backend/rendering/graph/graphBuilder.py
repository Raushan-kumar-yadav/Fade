from __future__ import annotations
from backend.rendering.graph.renderGraph import RenderGraph
from backend.rendering.graph.clipNode import ClipNode
from backend.rendering.graph.effectNode import EffectNode
from backend.rendering.graph.mergeNode import MergeNode
from backend.rendering.graph.outputNode import OutputNode
from backend.timeline.timeline import Timeline


class GraphBuilder:
 

    @staticmethod
    def build(timeline: Timeline, frame: int) -> RenderGraph:
        graph  = RenderGraph()
        output = OutputNode()
        graph.addNode(output)

        tracks = timeline.tracks   

        for track in tracks:
            if getattr(track, 'isAudio', lambda: False)():
                continue   # skip audio tracks
            if getattr(track, 'isMuted', False):
                continue

            trackOpacity = getattr(track, 'opacity', 1.0)
            mergeNode = MergeNode(
                trackId = getattr(track, 'trackId', track.name),
                trackOpacity = trackOpacity,
            )
            graph.addNode(mergeNode)

            # All active clips on this track
            activeClips = [c for c in track.clips if c.overlaps(frame)]

            for clip in activeClips:
                clipNode = ClipNode(clip)
                graph.addNode(clipNode)

                # Chain effect nodes  
                lastNode = clipNode
                for effect in clip.effects:
                    effNode = EffectNode(effect, clip.clipId)
                    graph.addNode(effNode)
                    effNode.addInput(lastNode)    
                    lastNode = effNode

               
                mergeNode.addInput(lastNode)

            # MergeNode feeds the output  
            output.addInput(mergeNode)

        return graph
