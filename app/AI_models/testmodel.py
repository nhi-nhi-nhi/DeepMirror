from videotester import DeepfakeVideoTester
from Preprocess import DeepfakePreprocessor
import torch

model_path = r"checkpoints\meso_net_epoch_40-50.pth"
# model_type = model_path.split("\\")[-1].split("_")[0]

# Determine image size based on model
# if model_type == 'vgg':
#     img_size = 224
# elif model_type == 'xception':
#     img_size = 299
# elif model_type == 'mobilenet':
#     img_size = 224
# elif model_type == 'meso':
#     img_size = 256
# elif model_type == 'shallow':
#     img_size = 224  # Default input image size

model_type = 'meso'
output_size = (256, 256)

# Initialize preprocessor
preprocessor = DeepfakePreprocessor(output_size=output_size)

# Use CUDA if available
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

# Initialize video tester
tester = DeepfakeVideoTester(
    model_path=model_path,
    preprocessor=preprocessor,
    device=device,
    confidence_threshold=0.2
)

# Analyze video
input_video = r"testing\testvideo.mp4"
output_video = r"testing\result.mp4"

results = tester.analyze_video(
    input_video_path=input_video,
    output_video_path=output_video,
    display_results=False,
    save_frames=False
)

print(f"Analysis complete. Video saved to {output_video}")