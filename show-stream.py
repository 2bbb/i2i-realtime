import zmq
import json
import base64
import cv2
import numpy as np
import argparse
import time

parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, help="Port number")
parser.add_argument("--fullscreen", action="store_true", help="Enable fullscreen")
parser.add_argument("--resolution", type=int, help="Image width for resizing")
args = parser.parse_args()

context = zmq.Context()
img_subscriber = context.socket(zmq.SUB)
img_subscriber.connect(f"tcp://127.0.0.1:{args.port}")
img_subscriber.setsockopt(zmq.SUBSCRIBE, b"")

fullscreen = args.fullscreen
window_name = f"Port {args.port}"
cv2.namedWindow(window_name, cv2.WINDOW_GUI_NORMAL)
if fullscreen:
    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

try:
    while True:
        msg = img_subscriber.recv()
        dropped_count = 0
        while True:
            try:
                msg = img_subscriber.recv(flags=zmq.NOBLOCK)
                dropped_count += 1
            except zmq.Again:
                break
            
        if dropped_count > 0:
            print("Dropped messages:", dropped_count)

        data = json.loads(msg)
        index = data['index']
        jpg_b64 = data['data']
        jpg = base64.b64decode(jpg_b64)
        img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_UNCHANGED)

        if args.resolution:
            h,w = img.shape[:2]
            h_new = int(args.resolution * h / w)
            w_new = args.resolution
            img = cv2.resize(img, (w_new, h_new), interpolation=cv2.INTER_LANCZOS4)

        # write index to image using putText
        
        if 'timestamp' in data:
            msg_timestamp = data["timestamp"]
            cur_timestamp = int(time.time() * 1000)
            latency = f"latency {cur_timestamp - msg_timestamp} ms"
            cv2.putText(img, latency, (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2, cv2.LINE_AA)

        cv2.imshow(window_name, img)

        key = cv2.waitKey(1)
        if key == 27:
            break
        # toggle fullscreen when user presses 'f' key
        elif key == ord('f'):
            fullscreen = not fullscreen
            if fullscreen:
                cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
            else:
                cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_KEEPRATIO)

except Exception as e:
    print(e)
    img_subscriber.close()
    context.term()