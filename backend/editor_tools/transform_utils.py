import math

def get_inverse_transform(transform):
    px, py = transform.position.get()
    sx, sy = transform.scale.get()
    if sx == 0: sx = 0.0001
    if sy == 0: sy = 0.0001
    rot = math.radians(transform.rotation.get())
    ax, ay = transform.anchor.get()
    return px, py, sx, sy, rot, ax, ay

def comp_to_local(pt, px, py, sx, sy, rot, ax, ay):
    # Translate(-x, -y)
    x = pt['x'] - px
    y = pt['y'] - py
    
    # Rotate(-rot)
    cosA = math.cos(-rot)
    sinA = math.sin(-rot)
    rx = x * cosA - y * sinA
    ry = x * sinA + y * cosA
    
    # Scale(1/sx, 1/sy)
    rx /= sx
    ry /= sy
    
    # Translate(anchorX, anchorY)
    rx += ax
    ry += ay
    
    return {'x': rx, 'y': ry}

def local_to_comp(pt, px, py, sx, sy, rot, ax, ay):
    # Translate(-ax, -ay)
    x = pt['x'] - ax
    y = pt['y'] - ay
    
    # Scale(sx, sy)
    x *= sx
    y *= sy
    
    # Rotate(rot)
    cosA = math.cos(rot)
    sinA = math.sin(rot)
    rx = x * cosA - y * sinA
    ry = x * sinA + y * cosA
    
    # Translate(px, py)
    rx += px
    ry += py
    return {'x': rx, 'y': ry}
