from app import app
import insightface
from app.AI_models.Preprocess import DeepfakePreprocessor
from app.AI_models.videotester import DeepfakeVideoTester
from insightface.app import FaceAnalysis
import base64
import re
import cv2
import numpy as np
import onnxruntime as ort
import torch
import os
import uuid
import base64
import time
from flask_login import login_required
from app.limits import enforce_quota
from flask import render_template, request, jsonify, send_from_directory, current_app
from datetime import datetime, timezone
from flask import jsonify, current_app
from flask_login import current_user
from app.models.auth_models import ServiceUsage, StreamSession


# Set the directory where videos are stored
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'processed_videos')  # Ensure path is correct
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# Check GPU availability at startup
print("CUDA available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU Name:", torch.cuda.get_device_name(0))
print("ONNX Runtime providers:", ort.get_available_providers())

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

# Initialize DeepfakeDetector
model_path = r"app/AI_models/checkpoints/meso_net_epoch_40-50.pth"
output_size = (256, 256)
preprocessor = DeepfakePreprocessor(output_size=output_size)

tester = DeepfakeVideoTester(
    model_path=model_path,
    preprocessor=preprocessor,
    device=device,
    confidence_threshold=0.2
)

# Load InsightFace Face Detector with GPU enforcement
face_detector = FaceAnalysis(name='buffalo_l')

face_detector.prepare(ctx_id=0, det_size=(64, 64))  # ctx_id=0 for GPU

# print("Face detector running on:", "GPU" if 'CUDAExecutionProvider' in ort.get_available_providers() else "CPU")

# Load Face Swapper with explicit GPU provider
session_options = ort.SessionOptions()
providers = ['CUDAExecutionProvider', 'CPUExecutionProvider'] if 'CUDAExecutionProvider' in ort.get_available_providers() else ['CPUExecutionProvider']
face_swapper = insightface.model_zoo.get_model(
    'app/inswapper_128.onnx',
    download=False,
    download_zip=False,
    session_options=session_options,
    providers=providers
)
# print("Face swapper running on:", providers[0])

def base64_to_image(base64_string):
    """Convert Base64 string to OpenCV image"""
    img_data = base64.b64decode(base64_string.split(',')[1])
    np_arr = np.frombuffer(img_data, np.uint8)
    return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

def image_to_base64(image):
    """Convert OpenCV image to Base64"""
    _, buffer = cv2.imencode('.jpg', image)
    return f"data:image/jpeg;base64,{base64.b64encode(buffer).decode()}"


def save_uploaded_video(base64_string):
    """ Save Base64-encoded video as a temporary file and return the file path. """
    
    video_data = base64.b64decode(base64_string.split(",")[1])  # Decode Base64
    temp_filename = f"temp_video_{uuid.uuid4().hex}.mp4"  # Generate a unique filename
    temp_filepath = os.path.join("temp_videos", temp_filename)

    os.makedirs("temp_videos", exist_ok=True)  # Ensure directory exists

    with open(temp_filepath, "wb") as video_file:
        video_file.write(video_data)

    return temp_filepath 

@app.route('/')
@app.route('/index')
def index():
    return render_template('index.html', title='Index')


@app.route('/detect')
@login_required
def detect():
    return render_template('df-detect/detect.html', title='Detect')

@app.route('/generate')
@login_required
def generate():
    return render_template('df-generate/generate.html', title='Generate')

def convertImage(imgData):
    imgstr = re.search(r'base64,(.*)', imgData).group(1)
    with open('camera.png', 'wb') as output:
        output.write(base64.b64decode(imgstr))

# Global cache variables (place these near your model initialization)
cached_source = None
cached_source_faces = None

def convert_arrays_to_lists(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {k: convert_arrays_to_lists(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_arrays_to_lists(item) for item in obj]
    else:
        return obj

@app.route("/quota_debug")
def quota_debug():
    if not current_user.is_authenticated:
        return jsonify({"error":"auth_required"}), 401

    cfg = {
        "FREE_USES": int(current_app.config.get("FREE_USES", 3)),
        "FREE_WINDOW_MIN": int(current_app.config.get("FREE_WINDOW_MIN", 30)),
        "STREAM_SESSION_MIN": int(current_app.config.get("STREAM_SESSION_MIN", 5)),
    }
    now = datetime.now(timezone.utc)

    def latest(service):
        w = (ServiceUsage.query
             .filter_by(user_id=current_user.id, service=service)
             .order_by(ServiceUsage.window_start.desc())
             .first())
        s = (StreamSession.query
             .filter_by(user_id=current_user.id, service=service)
             .order_by(StreamSession.expires_at.desc())
             .first())

        # normalize to UTC
        def as_utc(dt):
            if dt is None: return None
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

        w_start = as_utc(w.window_start) if w else None
        s_exp   = as_utc(s.expires_at)   if s else None

        # seconds left in stream + window
        stream_left = max(0, int((s_exp - now).total_seconds())) if s_exp else 0
        if w_start:
            window_total = cfg["FREE_WINDOW_MIN"] * 60
            window_left = max(0, window_total - int((now - w_start).total_seconds()))
        else:
            window_left = 0

        uses = w.uses if w else 0
        remaining = max(0, cfg["FREE_USES"] - uses)

        return {
            "window_start": w_start.isoformat() if w_start else None,
            "uses": uses,
            "remaining_tokens": remaining,
            "window_seconds_left": window_left,
            "stream_seconds_left": stream_left,
        }

    return jsonify({
        "deepfake_detect": latest("deepfake_detect"),
        "face_swap": latest("face_swap"),
        "config": cfg,
        "effective_stream_ttl_min": min(cfg["STREAM_SESSION_MIN"], cfg["FREE_WINDOW_MIN"]),
    })



@app.route('/generate_deepfake', methods=['POST'])
@login_required
@enforce_quota('face_swap')
def generate_deepfake():
    global cached_source, cached_source_faces
    try:
        data = request.json

        # Check if the source image in the request is new or else not update
        if 'source' not in data:
            return jsonify({'error': 'Source image is missing'}), 400
        
        start_time = time.time()
        if cached_source is None or data['source'] != cached_source:
            cached_source = data['source']
            source_img = base64_to_image(cached_source)
            cached_source_faces = face_detector.get(source_img)

        # Process the target image as usual
        target_img = base64_to_image(data['target'])
        target_faces = face_detector.get(target_img)

        # Check that faces were detected in the source image
        if not cached_source_faces or len(cached_source_faces) == 0:
            return jsonify({'error': 'No face detected in the source image'}), 400

        # Ignores the error
        if len(target_faces) == 0:
            return jsonify({'deepfake_image': None, 'fps': 0})

        # Calculate embeddings for source and target faces
        source_embedding = cached_source_faces[0].embedding

        # Perform face swap using the first detected face in both images
        result_img = face_swapper.get(target_img, target_faces[0], cached_source_faces[0], paste_back=True)

        # Convert the resulting deepfake image to Base64
        result_base64 = image_to_base64(result_img)

        # Extract face embeddings from the generated deepfake image
        result_faces = face_detector.get(result_img)
        if len(result_faces) > 0:
            result_face_embedding = result_faces[0].embedding
            distance = np.linalg.norm(source_embedding - result_face_embedding)
        else:
            distance = None
            result_face_embedding = None

        # Calculate FPS
        end_time = time.time()
        processing_time = end_time - start_time  # Time in seconds
        fps = 1 / processing_time if processing_time > 0 else 0

        # Return the deepfake image, FPS, distance, and the result face embedding
        return jsonify({
            'deepfake_image': result_base64,
            'fps': fps,
            'distance': distance.tolist(),
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/predict_deepfake', methods=['POST'])
@login_required
@enforce_quota('deepfake_detect')
def predict_deepfake():
    # Parse JSON safely
    data = request.get_json(silent=True) or {}
    source_type = data.get("source", None)
    action = (data.get("action") or "").lower()
    image_data = data.get("image")

    # Control pings for webcam streaming: no image required
    # The quota decorator already handled accounting/session changes.
    if source_type == "webcam" and action in ("start", "stop"):
        return jsonify({"ok": True, "action": action}), 200

    # Webcam frames
    if source_type == "webcam":
        if not image_data:
            return jsonify({"error": "No image provided"}), 400

        start_time = time.time()
        try:
            encoded_data = image_data.split(",", 1)[1]
            np_arr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError("cv2.imdecode returned None")
        except Exception as e:
            return jsonify({"error": f"Error decoding image: {str(e)}"}), 400

        try:
            frame, parameters = tester.process_frame(frame)
        except Exception as e:
            return jsonify({"error": "server_exception", "message": str(e)}), 500

        frame_b64 = image_to_base64(frame)
        fps = 1.0 / max(1e-6, (time.time() - start_time))

        return jsonify({
            "annotated_frame": frame_b64,
            "fps": fps,
            "results": convert_arrays_to_lists(parameters),
        }), 200

    # Video branch (single job => counts as one use)
    if source_type == "video":
        if not image_data:
            return jsonify({"error": "No video provided"}), 400
        try:
            video_path = save_uploaded_video(image_data)

            output_filename = f"processed_{uuid.uuid4().hex}.mp4"
            output_dir = os.path.join("app", "static", "processed_videos")
            os.makedirs(output_dir, exist_ok=True)
            output_video_path = os.path.join(output_dir, output_filename)

            results = tester.analyze_video(
                input_video_path=video_path,
                output_video_path=output_video_path,
                display_results=False,
                save_frames=False
            )
        except Exception as e:
            return jsonify({"error": f"Error processing video: {str(e)}"}), 400

        return jsonify({
            "processed_video": output_video_path,
            "results": results
        }), 200

    # Unknown source
    return jsonify({"error": "Invalid or missing 'source'"}), 400


@app.route('/processed_videos/<filename>')
def serve_video(filename):
    video_directory = os.path.join(app.root_path, 'processed_videos')
    
    # Check if the file exists before serving
    if os.path.exists(os.path.join(video_directory, filename)):
        return send_from_directory(video_directory, filename, mimetype='video/mp4')
    else:
        return "Video not found", 404


if __name__ == '__main__':
    app.run(debug=True)