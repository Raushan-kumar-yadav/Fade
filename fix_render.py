with open("backend/routers/render.py", "r") as f:
    text = f.read()

text = text.replace(
"""                            xform = {
                                "x": float(ipx), "y": float(ipy),
                                "scaleX": float(isx), "scaleY": float(isy),
                                "rotation": float(irot),
                                "anchorX": float(iax), "anchorY": float(iay),
                            }""",
"""                            xform = transform_dict"""
)

with open("backend/routers/render.py", "w") as f:
    f.write(text)
