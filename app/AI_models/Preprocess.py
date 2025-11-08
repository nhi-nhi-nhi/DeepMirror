# import torch.nn as nn
# import torch.optim as optim
# from torch.utils.data import Dataset, DataLoader
# from sklearn.model_selection import train_test_split
import cv2
import numpy as np
# import torch
# import torchvision.transforms as transforms
# from PIL import Image
# import time
# import os
# Import MediaPipe for BlazeFace
import mediapipe as mp
# import torchvision.AI_models as AI_models
# import torch.nn.functional as F


# Preprocessing Class
class DeepfakePreprocessor:
    def __init__(self, output_size=(150, 150), min_detection_confidence=0.5):
        """Initialize the preprocessor with the desired output size."""
        self.output_size = output_size
        # Initialize MediaPipe Face Detection
        self.mp_face_detection = mp.solutions.face_detection
        self.face_detector = self.mp_face_detection.FaceDetection(
            model_selection=0,  # 0 for short range, 1 for full range
            min_detection_confidence=min_detection_confidence
        )
        self.mp_drawing = mp.solutions.drawing_utils

    def crop_face(self, image):
        """
        Detect and crop the face from the image using MediaPipe BlazeFace.

        Args:
            image: Input image in BGR format (from cv2.imread).

        Returns:
            Cropped face image in RGB format, or None if no face is detected.
        """
        # Convert to RGB for MediaPipe
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        # Process the image and get face detections
        results = self.face_detector.process(image_rgb)

        # Check if any faces are detected
        if not results.detections:
            return None

        # Get the first detected face
        detection = results.detections[0]

        # Get bounding box coordinates
        bboxC = detection.location_data.relative_bounding_box
        ih, iw, _ = image.shape

        # Convert relative coordinates to absolute pixel coordinates
        x = int(bboxC.xmin * iw)
        y = int(bboxC.ymin * ih)
        w = int(bboxC.width * iw)
        h = int(bboxC.height * ih)

        # Add a small margin around the face
        margin = int(0.1 * min(w, h))
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(iw, x + w + margin)
        y2 = min(ih, y + h + margin)

        # Crop the face region
        cropped = image[y1:y2, x1:x2]

        # Resize to the specified output size
        if cropped.size == 0:
            return None

        resized = cv2.resize(cropped, self.output_size)
        # Convert to RGB for consistency with deep learning AI_models
        resized_rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        return resized_rgb

    def apply_gradient_transform(self, image):
        """
        Apply the gradient transformation as per the paper.

        Args:
            image: Input image in RGB format.

        Returns:
            Gradient-transformed image in uint8 format.
        """
        H, W, _ = image.shape
        gradient_img = np.zeros_like(image, dtype=np.float32)
        for c in range(3):  # Process each color channel
            channel = image[:, :, c].astype(np.float32)
            # Compute differences with neighboring pixels
            diff_y = channel[:-1, :-1] - channel[1:, :-1]  # Vertical difference
            diff_x = channel[:-1, :-1] - channel[:-1, 1:]  # Horizontal difference
            # Compute gradient magnitude
            magnitude = np.sqrt(diff_y**2 + diff_x**2)
            # Assign to output (last row and column remain zero)
            gradient_img[:-1, :-1, c] = magnitude
        # Normalize to 0-255 range
        gradient_img = cv2.normalize(gradient_img, None, 0, 255, cv2.NORM_MINMAX)
        return gradient_img.astype(np.uint8)

    def preprocess_image(self, image_path):
        """
        Preprocess a single image by cropping the face and applying the gradient transform.

        Args:
            image_path: Path to the input image.

        Returns:
            Preprocessed image, or None if preprocessing fails.
        """
        image = cv2.imread(image_path)
        if image is None:
            return None
        # face = self.crop_face(image)
        # if face is None:
        #     return None
        face = image
        preprocessed = self.apply_gradient_transform(face)
        return preprocessed
