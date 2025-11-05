
import torch
import torch.nn as nn
import torchvision.models as models


# MesoNet Model Definition (PyTorch)
class MesoNet(nn.Module):
    def __init__(self):
        super(MesoNet, self).__init__()
        # Convolutional layers
        self.conv1 = nn.Conv2d(3, 8, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm2d(8)
        self.pool1 = nn.MaxPool2d(2)
        self.conv2 = nn.Conv2d(8, 8, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm2d(8)
        self.pool2 = nn.MaxPool2d(2)
        self.conv3 = nn.Conv2d(8, 16, kernel_size=3, padding=1)
        self.bn3 = nn.BatchNorm2d(16)
        self.pool3 = nn.MaxPool2d(2)
        self.conv4 = nn.Conv2d(16, 16, kernel_size=3, padding=1)
        self.bn4 = nn.BatchNorm2d(16)
        self.pool4 = nn.MaxPool2d(2)
        # Fully connected layers
        self.flatten = nn.Flatten()
        self.fc1 = nn.Linear(16 * 16 * 16, 16)  # After four max pools, 256/16 = 16
        self.dropout = nn.Dropout(0.5)
        self.fc2 = nn.Linear(16, 2)  # 2 classes: real or fake

    def forward(self, x):
        x = self.pool1(nn.ReLU()(self.bn1(self.conv1(x))))
        x = self.pool2(nn.ReLU()(self.bn2(self.conv2(x))))
        x = self.pool3(nn.ReLU()(self.bn3(self.conv3(x))))
        x = self.pool4(nn.ReLU()(self.bn4(self.conv4(x))))
        x = self.flatten(x)
        x = nn.ReLU()(self.fc1(x))
        x = self.dropout(x)
        x = self.fc2(x)
        return x



# 1. VGG-based Deepfake Detector
class VGGDeepfakeDetector(nn.Module):
    def __init__(self, pretrained=True, freeze_base=True):
        super(VGGDeepfakeDetector, self).__init__()
        # Load pre-trained VGG16 model
        vgg = models.vgg16(pretrained=pretrained)

        # Use VGG features (all convolutional and pooling layers)
        self.features = vgg.features

        # Freeze base model weights if specified
        if freeze_base:
            for param in self.features.parameters():
                param.requires_grad = False

        # Replace classifier for binary classification
        self.classifier = nn.Sequential(
            nn.Linear(512 * 7 * 7, 512),
            nn.ReLU(True),
            nn.Dropout(0.5),
            nn.Linear(512, 128),
            nn.ReLU(True),
            nn.Dropout(0.5),
            nn.Linear(128, 2)  # 2 classes: real or fake
        )

    def forward(self, x):
        x = self.features(x)
        x = x.view(x.size(0), -1)  # Flatten
        x = self.classifier(x)
        return x

# 2. MobileNet-based Deepfake Detector
class MobileNetDeepfakeDetector(nn.Module):
    def __init__(self, pretrained=True, freeze_base=True):
        super(MobileNetDeepfakeDetector, self).__init__()
        # Load pre-trained MobileNetV2
        mobilenet = models.mobilenet_v2(pretrained=pretrained)

        # Use all layers except the classifier
        self.features = mobilenet.features

        # Freeze base model weights if specified
        if freeze_base:
            for param in self.features.parameters():
                param.requires_grad = False

        # Classification head
        self.classifier = nn.Sequential(
            nn.Dropout(0.2),
            nn.Linear(1280, 256),
            nn.ReLU(True),
            nn.Dropout(0.2),
            nn.Linear(256, 2)  # 2 classes: real or fake
        )

        # Average pooling as in the original MobileNetV2
        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))

    def forward(self, x):
        x = self.features(x)
        x = self.avgpool(x)
        x = torch.flatten(x, 1)
        x = self.classifier(x)
        return x

# 3. Xception-based Deepfake Detector (simplified version)
class SeparableConv2d(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size=1, stride=1, padding=0, dilation=1, bias=False):
        super(SeparableConv2d, self).__init__()
        self.depthwise = nn.Conv2d(in_channels, in_channels, kernel_size, stride, padding, dilation, groups=in_channels, bias=bias)
        self.pointwise = nn.Conv2d(in_channels, out_channels, 1, 1, 0, 1, 1, bias=bias)

    def forward(self, x):
        x = self.depthwise(x)
        x = self.pointwise(x)
        return x

class XceptionBlock(nn.Module):
    def __init__(self, in_channels, out_channels, stride=1, downsample=False, start_with_relu=True):
        super(XceptionBlock, self).__init__()

        self.downsample = downsample

        if downsample:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_channels, out_channels, kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm2d(out_channels)
            )

        self.conv1 = SeparableConv2d(in_channels, out_channels, 3, stride=1, padding=1)
        self.bn1 = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU(inplace=True)

        self.conv2 = SeparableConv2d(out_channels, out_channels, 3, stride=1, padding=1)
        self.bn2 = nn.BatchNorm2d(out_channels)

        self.conv3 = SeparableConv2d(out_channels, out_channels, 3, stride=stride, padding=1)
        self.bn3 = nn.BatchNorm2d(out_channels)

        self.start_with_relu = start_with_relu

    def forward(self, x):
        residual = x

        if self.start_with_relu:
            x = self.relu(x)

        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)

        x = self.conv2(x)
        x = self.bn2(x)
        x = self.relu(x)

        x = self.conv3(x)
        x = self.bn3(x)

        if self.downsample:
            residual = self.shortcut(residual)

        x += residual
        return x

class XceptionNet(nn.Module):
    def __init__(self, num_classes=2):
        super(XceptionNet, self).__init__()

        # Entry flow
        self.conv1 = nn.Conv2d(3, 32, 3, stride=2, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(32)
        self.relu = nn.ReLU(inplace=True)

        self.conv2 = nn.Conv2d(32, 64, 3, stride=1, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(64)

        # Xception blocks in entry flow
        self.block1 = XceptionBlock(64, 128, stride=2, downsample=True, start_with_relu=True)
        self.block2 = XceptionBlock(128, 256, stride=2, downsample=True, start_with_relu=True)
        self.block3 = XceptionBlock(256, 728, stride=2, downsample=True, start_with_relu=True)

        # Middle flow (repeated blocks)
        self.middle_blocks = nn.Sequential(*[
            XceptionBlock(728, 728, stride=1, downsample=False, start_with_relu=True) for _ in range(8)
        ])

        # Exit flow
        self.block4 = XceptionBlock(728, 1024, stride=2, downsample=True, start_with_relu=True)

        self.conv3 = SeparableConv2d(1024, 1536, 3, stride=1, padding=1)
        self.bn3 = nn.BatchNorm2d(1536)

        self.conv4 = SeparableConv2d(1536, 2048, 3, stride=1, padding=1)
        self.bn4 = nn.BatchNorm2d(2048)

        # Global average pooling and classifier
        self.global_pool = nn.AdaptiveAvgPool2d((1, 1))
        self.fc = nn.Linear(2048, num_classes)

    def forward(self, x):
        # Entry flow
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)

        x = self.conv2(x)
        x = self.bn2(x)
        x = self.relu(x)

        x = self.block1(x)
        x = self.block2(x)
        x = self.block3(x)

        # Middle flow
        x = self.middle_blocks(x)

        # Exit flow
        x = self.block4(x)

        x = self.conv3(x)
        x = self.bn3(x)
        x = self.relu(x)

        x = self.conv4(x)
        x = self.bn4(x)
        x = self.relu(x)

        x = self.global_pool(x)
        x = x.view(x.size(0), -1)
        x = self.fc(x)

        return x

# 4. Shallow Design Layer with 1 Hidden Layer
class ShallowDeepfakeDetector(nn.Module):
    def __init__(self):
        super(ShallowDeepfakeDetector, self).__init__()

        # Simple feedforward network with a single hidden layer
        # Based on the error, the actual input size is 150528
        self.classifier = nn.Sequential(
            nn.Flatten(),  # Flatten the input image
            nn.Linear(150528, 128),  # Single hidden layer with 128 neurons
            nn.ReLU(),
            nn.Linear(128, 2)  # Output layer for binary classification
        )

    def forward(self, x):
        return self.classifier(x)

# 5. MesoInception Network
class InceptionBlock(nn.Module):
    def __init__(self, in_channels, out_channels):
        super(InceptionBlock, self).__init__()

        # 1x1 convolution branch
        self.conv1x1 = nn.Conv2d(in_channels, out_channels//4, kernel_size=1)

        # 3x3 convolution branch
        self.conv3x3_1 = nn.Conv2d(in_channels, out_channels//4, kernel_size=1)
        self.conv3x3_2 = nn.Conv2d(out_channels//4, out_channels//4, kernel_size=3, padding=1)

        # 5x5 convolution branch (implemented as two 3x3 convs)
        self.conv5x5_1 = nn.Conv2d(in_channels, out_channels//4, kernel_size=1)
        self.conv5x5_2 = nn.Conv2d(out_channels//4, out_channels//4, kernel_size=3, padding=1)
        self.conv5x5_3 = nn.Conv2d(out_channels//4, out_channels//4, kernel_size=3, padding=1)

        # Max pooling branch
        self.pool = nn.MaxPool2d(kernel_size=3, stride=1, padding=1)
        self.pool_conv = nn.Conv2d(in_channels, out_channels//4, kernel_size=1)

    def forward(self, x):
        # 1x1 branch
        branch1 = self.conv1x1(x)

        # 3x3 branch
        branch2 = self.conv3x3_1(x)
        branch2 = self.conv3x3_2(branch2)

        # 5x5 branch
        branch3 = self.conv5x5_1(x)
        branch3 = self.conv5x5_2(branch3)
        branch3 = self.conv5x5_3(branch3)

        # Pooling branch
        branch4 = self.pool(x)
        branch4 = self.pool_conv(branch4)

        # Concatenate branches
        output = torch.cat([branch1, branch2, branch3, branch4], dim=1)
        return output

class MesoInceptionNet(nn.Module):
    def __init__(self, input_size=(256, 256)):
        super(MesoInceptionNet, self).__init__()

        # Initial convolution
        self.conv1 = nn.Conv2d(3, 8, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm2d(8)
        self.relu = nn.ReLU(inplace=True)
        self.pool1 = nn.MaxPool2d(2)

        # First inception block
        self.inception1 = InceptionBlock(8, 16)
        self.bn2 = nn.BatchNorm2d(16)
        self.pool2 = nn.MaxPool2d(2)

        # Second inception block
        self.inception2 = InceptionBlock(16, 32)
        self.bn3 = nn.BatchNorm2d(32)
        self.pool3 = nn.MaxPool2d(2)

        # Final convolution
        self.conv2 = nn.Conv2d(32, 16, kernel_size=3, padding=1)
        self.bn4 = nn.BatchNorm2d(16)
        self.pool4 = nn.MaxPool2d(2)

        # Calculate the size after all pooling operations
        h, w = input_size
        feature_h, feature_w = h // 16, w // 16  # After 4 max-pool layers (2^4 = 16)
        self.feature_size = 16 * feature_h * feature_w

        # Fully connected layers
        self.flatten = nn.Flatten()
        self.fc1 = nn.Linear(self.feature_size, 16)
        self.dropout = nn.Dropout(0.5)
        self.fc2 = nn.Linear(16, 2)

    def forward(self, x):
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.pool1(x)

        x = self.inception1(x)
        x = self.bn2(x)
        x = self.relu(x)
        x = self.pool2(x)

        x = self.inception2(x)
        x = self.bn3(x)
        x = self.relu(x)
        x = self.pool3(x)

        x = self.conv2(x)
        x = self.bn4(x)
        x = self.relu(x)
        x = self.pool4(x)

        x = self.flatten(x)
        x = self.fc1(x)
        x = self.relu(x)
        x = self.dropout(x)
        x = self.fc2(x)

        return x
