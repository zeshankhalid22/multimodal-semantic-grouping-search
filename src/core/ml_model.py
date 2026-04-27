from __future__ import annotations

import os
from typing import Any

from src.core.config import get_settings

_model: Any = None
_preprocess: Any = None
_tokenizer: Any = None

_torch: Any | None = None
_Image: Any | None = None
_device: str | None = None


def load_model() -> None:
    """Load the fine-tuned OpenCLIP model. Called once at app startup.

    This function imports `open_clip`, `torch` and `PIL.Image` lazily so that
    modules depending on heavy native extensions are not imported during
    top-level module import (which previously caused runtime failures).
    """
    global _model, _preprocess, _tokenizer, _torch, _Image, _device

    # Import here to avoid import-time side effects
    import open_clip
    import torch
    from PIL import Image

    _torch = torch
    _Image = Image
    _device = "cuda" if torch.cuda.is_available() else "cpu"

    settings = get_settings()

    model, _, preprocess = open_clip.create_model_and_transforms(
        settings.model_name, pretrained=None
    )

    checkpoint = torch.load(settings.model_path, map_location=_device)

    if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
        model.load_state_dict(checkpoint["model_state_dict"])
        print(f"Loaded model on (device: {_device})")
    else:
        model.load_state_dict(checkpoint)
        print(f"Loaded model from bare state-dict (device: {_device})")

    model.to(_device).eval()

    _model = model
    _preprocess = preprocess
    _tokenizer = open_clip.get_tokenizer(settings.model_name)


def _require_model() -> None:
    if _model is None:
        raise RuntimeError("ML model is not loaded..")


def generate_fused_embedding(image_path: str, title: str) -> list[float]:
    """
    Return a normalised 512-d fusion embedding combining image and title features.

    Raises:
        RuntimeError: If the model has not been loaded.
        FileNotFoundError: If the image file does not exist.
    """
    _require_model()

    # Ensure torch and PIL were loaded via load_model()
    if _torch is None or _Image is None or _device is None:
        raise RuntimeError("ML runtime not initialised. Call load_model() first.")

    settings = get_settings()
    full_path = (
        os.path.join(settings.image_root, image_path)
        if settings.image_root
        else image_path
    )

    if not os.path.isfile(full_path):
        raise FileNotFoundError(f"Image not found: {full_path!r}")

    torch = _torch
    Image = _Image

    with torch.no_grad():
        img_tensor = _preprocess(Image.open(full_path).convert("RGB"))
        img_tensor = img_tensor.unsqueeze(0).to(_device)
        img_feat = _model.encode_image(img_tensor)
        img_feat = img_feat / img_feat.norm(dim=-1, keepdim=True)

        txt_tokens = _tokenizer([title]).to(_device)
        txt_feat = _model.encode_text(txt_tokens)
        txt_feat = txt_feat / txt_feat.norm(dim=-1, keepdim=True)

        fused = (img_feat + txt_feat) / 2.0
        fused = fused / fused.norm(dim=-1, keepdim=True)

    return fused.cpu().numpy()[0].tolist()
