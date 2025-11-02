from app.models.backbone import *
import os
# Factory function to get model by name

# Factory function to get model by name
def get_model(model_name, num_classes=2, pretrained=True, freeze_base=True, input_size=(256, 256)):
    if model_name.lower() == 'mesonet':
        return MesoNet()
    if model_name.lower() == 'meso':
        return MesoNet()
    elif model_name.lower() == 'mesoinception':
        return MesoInceptionNet()
    elif model_name.lower() == 'vgg':
        return VGGDeepfakeDetector(pretrained=pretrained, freeze_base=freeze_base)
    elif model_name.lower() == 'mobilenet':
        return MobileNetDeepfakeDetector(pretrained=pretrained, freeze_base=freeze_base)
    elif model_name.lower() == 'xception':
        return XceptionNet(num_classes=num_classes)
    elif model_name.lower() == 'shallow':
        return ShallowDeepfakeDetector()
    elif model_name.lower() == 'mesoinception4mhsa':
        return MesoInception4MHSA(num_classes=num_classes)
    else:
        raise ValueError(f"Model {model_name} not supported. Choose from: meso, mesoinception, vgg, mobilenet, xception, shallow")

def save_model(model, save_path, epoch=None, optimizer=None, val_accuracy=None):
    """
    Save the trained model with optional metadata.

    Args:
        model: The PyTorch model to save
        save_path: Path where to save the model
        epoch: Current training epoch (optional)
        optimizer: Optimizer state (optional)
        val_accuracy: Validation accuracy (optional)
    """
    # Create directory if it doesn't exist
    save_dir = os.path.dirname(save_path)
    if save_dir and not os.path.exists(save_dir):
        os.makedirs(save_dir)

    # Determine the architecture name
    if isinstance(model, MesoNet):
        architecture = 'meso'
    elif isinstance(model, MesoInceptionNet):
        architecture = 'mesoinception'
    elif isinstance(model, VGGDeepfakeDetector):
        architecture = 'vgg'
    elif isinstance(model, MobileNetDeepfakeDetector):
        architecture = 'mobilenet'
    elif isinstance(model, XceptionNet):
        architecture = 'xception'
    elif isinstance(model, ShallowDeepfakeDetector):
        architecture = 'shallow'
    elif isinstance(model, MesoInception4MHSA):
        architecture = 'mesoinception4mhsa'
    else:
        architecture = model.__class__.__name__

    # Prepare save dictionary
    save_dict = {
        'model_state_dict': model.state_dict(),
        'architecture': architecture,
        'input_size': (256, 256),  # Default input size
    }

    # Add optional metadata
    if epoch is not None:
        save_dict['epoch'] = epoch
    if optimizer is not None:
        save_dict['optimizer_state_dict'] = optimizer.state_dict()
    if val_accuracy is not None:
        save_dict['val_accuracy'] = val_accuracy

    # Save the model
    torch.save(save_dict, save_path)
    print(f"Model saved to {save_path}")

def load_model(model_path, model_class=None, device='cpu'):
    """
    Load a saved model.

    Args:
        model_path: Path to the saved model
        model_class: Model class to instantiate (if None, determined from saved architecture)
        device: Device to load model to ('cpu' or 'cuda')

    Returns:
        Loaded model
    """
    # Convert device to torch.device if it's a string
    device = torch.device(device) if isinstance(device, str) else device

    # Load the save dictionary
    checkpoint = torch.load(model_path, map_location=device)

    # Determine model class if not provided
    if model_class is None:
        if 'architecture' in checkpoint:
            architecture = checkpoint['architecture'].lower()
            # Use the get_model function to create the appropriate model instance
            model = get_model(architecture)
        else:
            # Default to MesoNet for backward compatibility
            model = MesoNet()
    else:
        # If model_class is provided directly, use it
        model = model_class()

    # Load the state dictionary
    if 'model_state_dict' in checkpoint:
        model.load_state_dict(checkpoint['model_state_dict'])
    else:
        # For backward compatibility with older saved models
        model.load_state_dict(checkpoint)

    # Move model to the specified device - use .to() method with device directly
    model = model.to(device)

    # Return model and any additional info that might be useful
    metadata = {k: v for k, v in checkpoint.items() if k != 'model_state_dict'}

    return model, metadata

