from __future__ import annotations
import uuid

class imageLayer : 
    TRACK_TYPE = "image-layer"

    def __init__(self , name:str = "Layer") -> None:
        self.trackId = str(uuid.uuid4())
        self.name = name
        self.zIndex = 0
        self.visible = True
        self.locked = False
        self.opacity :float = 1.0
        self.blendMode = "normal"

        self.element:dict | None = None


    def toDict(self)-> dict :
        return{
            "trackId" :self.trackId,
            "name" : self.name, 
            "type":self.TRACK_TYPE,
            "z_index":self.zIndex,
            "locked" : self.locked,
            "opacity" : self.opacity,
            "blendMode" : self.blendMode,
            "element" : self.element
        }

    @classmethod
    def fromDict(cls,data:dict) -> "ImageLayer":
        lyr = cls(name=data.get("name","Layer"))
        lyr.trackId = data.get("trackId" , str(uuid.uuid4()))
        lyr.zIndex = data.get("z_index" , 0)
        lyr.visible = data.get("visible" , True)
        lyr.locked = data.get("locked", False)
        lyr.opacity = data.get("opcity" ,1.0 )
        lyr.blendMode = data.get("blendMode" , "normal")
        lyr.element = data.get("element")
        return lyr


    