from app.AI_models.utils import *
import torchvision.transforms as transforms
import cv2
import os
import time
class DeepfakeVideoTester:
    def __init__(self, model_path, preprocessor, batch_size=8, device='cpu', confidence_threshold=0.6):
        """
        Initialize the video tester with a trained model.

        Args:
            model_path: Path to the saved model weights
            preprocessor: DeepfakePreprocessor instance
            batch_size: Number of frames to process at once
            device: 'cuda' or 'cpu'
            confidence_threshold: Threshold for prediction confidence
        """

        model_type = model_path.split('/')[-1].split('_')[0]
        if model_type == 'mesonet':  # Check for 'mesonet'
            model_type = 'meso'

        if model_type == 'meso':
            self.img_size = 256
        elif model_type == 'vgg':
            self.img_size = 224
        elif model_type == 'mobilenet':
            self.img_size = 224
        else:
            self.img_size = 224

        self.preprocessor = preprocessor
        self.batch_size = batch_size
        self.device = device
        self.confidence_threshold = confidence_threshold

        # Load the trained model using the load_model function
        self.model, _ = load_model(model_path, device=device)  # Unpack the tuple
        self.model.eval()

        # Initialize transform
        self.transform = transforms.Compose([
            # transforms.Resize((self.img_size, self.img_size)),  # Resize to model-specific size
            transforms.ToTensor(),
        ])

        print(f"Model loaded from {model_path}")

    def analyze_video(self, input_video_path, output_video_path=None, display_results=False, save_frames=False):
        """
        Analyze a video file for deepfakes, showing and/or saving the results.

        Args:
            input_video_path: Path to the input video
            output_video_path: Path to save the output video (if None, won't save)
            display_results: Whether to display the results in real-time
            save_frames: Whether to save individual frames with annotations

        Returns:
            Dictionary containing analysis results
        """
        # Open the video
        cap = cv2.VideoCapture(input_video_path)
        if not cap.isOpened():
            print(f"Error: Could not open video {input_video_path}")
            return None

        # Get video properties
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Set up output video writer if needed
        if output_video_path:
            fourcc = cv2.VideoWriter_fourcc(*'H264')
            out = cv2.VideoWriter(output_video_path, fourcc, fps,
                                 (frame_width, frame_height))

        # Set up frame saving directory if needed
        if save_frames:
            frames_dir = os.path.splitext(output_video_path)[0] + "_frames"
            os.makedirs(frames_dir, exist_ok=True)

        # Statistics tracking
        frame_count = 0
        real_frames = 0
        fake_frames = 0
        no_face_frames = 0
        frame_results = []
        processing_times = []

        print(f"Analyzing video: {input_video_path}")
        print(f"Total frames: {total_frames}")

        # Process frame by frame
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            frame_count += 1
            if frame_count % 100 == 0:
                print(f"Processing frame {frame_count}/{total_frames}")

            # Process the frame
            start_time = time.time()
            result_frame, prediction = self.process_frame(frame)
            processing_time = time.time() - start_time
            processing_times.append(processing_time)

            # Update statistics
            if prediction is None:
                no_face_frames += 1
                prediction_label = "No Face"
            else:
                if prediction['label'] == 'real':
                    real_frames += 1
                else:
                    fake_frames += 1
                prediction_label = prediction['label']
                frame_results.append(prediction)

            # Display results using cv2_imshow
            if display_results and frame_count % 10 == 0:
                cv2.imshow(result_frame) # Use cv2_imshow instead of cv2.imshow
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

            # Save output video
            if output_video_path:
                out.write(result_frame)

            # Save individual frames
            if save_frames:
                frame_path = os.path.join(frames_dir, f"frame_{frame_count:06d}_{prediction_label}.jpg")
                cv2.imwrite(frame_path, result_frame)

        # Clean up
        cap.release()
        if output_video_path:
            out.release()
        if display_results:
            cv2.destroyAllWindows()

        # Compute overall statistics
        frames_with_faces = frame_count - no_face_frames
        fake_percentage = (fake_frames / frames_with_faces * 100) if frames_with_faces > 0 else 0
        avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0

        # Prepare results summary
        results = {
            'video_path': input_video_path,
            'output_path': output_video_path,
            'total_frames': frame_count,
            'frames_with_faces': frames_with_faces,
            'no_face_frames': no_face_frames,
            'real_frames': real_frames,
            'fake_frames': fake_frames,
            'fake_percentage': fake_percentage,
            'avg_processing_time': avg_processing_time,
            'verdict': 'FAKE' if fake_percentage > 50 else 'REAL',
            'confidence': max(fake_percentage, 100 - fake_percentage) / 100,
            'frame_details': frame_results
        }

        # Print summary
        print("\nAnalysis Complete")
        print(f"Total frames analyzed: {frame_count}")
        print(f"Frames with faces: {frames_with_faces}")
        print(f"Frames without faces: {no_face_frames}")
        print(f"Real frames: {real_frames} ({real_frames/frames_with_faces*100:.1f}% of frames with faces)")
        print(f"Fake frames: {fake_frames} ({fake_percentage:.1f}% of frames with faces)")
        print(f"Average processing time per frame: {avg_processing_time:.3f} seconds")
        print(f"Overall verdict: {results['verdict']} (confidence: {results['confidence']:.2f})")

        if output_video_path:
            print(f"Output video saved to: {output_video_path}")

        return results

    def process_frame(self, frame):
        """
        Process a single frame to detect and classify faces.

        Args:
            frame: Input frame from video

        Returns:
            Tuple of (annotated frame, prediction result)
        """
        original_frame = frame.copy()

        # Convert to RGB for MediaPipe processing
        image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Process the image with MediaPipe Face Detection
        with self.preprocessor.mp_face_detection.FaceDetection(
            model_selection=1,  # 0 for short range, 1 for full range
            min_detection_confidence=self.confidence_threshold
        ) as face_detection:
            results = face_detection.process(image_rgb)

        # If no face is detected, return the original frame
        if not results.detections:
            # Add text indicating no face detected
            cv2.putText(frame, "No face detected", (30, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            return frame, None

        # Process the first detected face
        detection = results.detections[0]

        # Get bounding box coordinates
        bboxC = detection.location_data.relative_bounding_box
        ih, iw, _ = frame.shape

        # Convert relative coordinates to absolute pixel coordinates
        x = int(bboxC.xmin * iw)
        y = int(bboxC.ymin * ih)
        w = int(bboxC.width * iw)
        h = int(bboxC.height * ih)

        # Add a small margin around the face
        margin = int(0.1 * min(w, h))
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(frame.shape[1], x + w + margin)
        y2 = min(frame.shape[0], y + h + margin)

        # Crop and resize the face
        face_img = frame[y1:y2, x1:x2]
        if face_img.size == 0:
            cv2.putText(frame, "Invalid face region", (30, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            return frame, None

        resized_face = cv2.resize(face_img, self.preprocessor.output_size)

        # Convert to RGB for consistency with the model training
        rgb_face = cv2.cvtColor(resized_face, cv2.COLOR_BGR2RGB)

        # Apply gradient transform as used during training
        gradient_face = self.preprocessor.apply_gradient_transform(rgb_face)

        # Convert to tensor
        tensor_face = self.transform(gradient_face).unsqueeze(0).to(self.device)

        # Make prediction
        with torch.no_grad():
            output = self.model(tensor_face)
            probabilities = torch.nn.functional.softmax(output, dim=1)[0]
            confidence, prediction = torch.max(probabilities, 0)
            confidence = confidence.item()
            prediction = prediction.item()

        # Determine the predicted label
        label = 'fake' if prediction == 1 else 'real'

        # Set color based on prediction (red for fake, green for real)
        color = (0, 255, 0) if label == 'real' else (0, 0, 255)

        # Create bounding box around the face
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        # Add text with prediction and confidence
        text = f"{label.upper()}: {confidence:.2f}"
        cv2.putText(frame, text, (x1, y1 - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        # Store prediction details
        prediction_result = {
            'face_id': 0,
            'bbox': (x1, y1, x2, y2),
            'label': label,
            'confidence': confidence,
            'is_fake': label == 'fake',
            'probabilities': probabilities.cpu().numpy().tolist()
        }

        # Add a banner with overall info
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 40), (0, 0, 0), -1)
        cv2.putText(frame, f"Prediction: {label.upper()} ({confidence:.2f})",
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

        return frame, prediction_result