import cv2
video_path = r"C:\Users\ariji\OneDrive\Desktop\fade test video.mp4"
cap = cv2.VideoCapture(video_path)
cap.set(cv2.CAP_PROP_POS_FRAMES, 3.0)
ret, frame = cap.read()
if ret:
    cv2.imwrite("frame3.png", frame)
    print("Saved frame3.png")
else:
    print("Could not read frame 3")
