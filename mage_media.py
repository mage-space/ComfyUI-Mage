"""Conversions between ComfyUI values and the files the Mage API sends and
receives."""

from __future__ import annotations

from io import BytesIO

import av
import numpy as np
import torch
from comfy_api.input import VideoInput
from comfy_api.input_impl import VideoFromFile
from comfy_api.util import VideoCodec, VideoContainer
from PIL import Image


def images_to_png(images: torch.Tensor) -> list[bytes]:
    """Each image of an IMAGE batch ([B, H, W, C], 0 to 1) as PNG bytes."""
    files = []
    for image in images:
        pixels = (image.cpu().numpy().clip(0, 1) * 255).round().astype(np.uint8)
        buffer = BytesIO()
        Image.fromarray(pixels).save(buffer, format="PNG")
        files.append(buffer.getvalue())
    return files


def image_from_bytes(data: bytes) -> torch.Tensor:
    """A downloaded image as a one-image IMAGE batch."""
    image = Image.open(BytesIO(data)).convert("RGB")
    pixels = np.asarray(image).astype(np.float32) / 255.0
    return torch.from_numpy(pixels).unsqueeze(0)


def video_to_mp4(video: VideoInput) -> bytes:
    """A VIDEO input encoded as MP4 for upload."""
    buffer = BytesIO()
    video.save_to(buffer, format=VideoContainer.MP4, codec=VideoCodec.H264)
    return buffer.getvalue()


def video_from_bytes(data: bytes) -> VideoFromFile:
    """A downloaded video as a VIDEO output."""
    return VideoFromFile(BytesIO(data))


def audio_from_bytes(data: bytes) -> dict:
    """A downloaded MP3 as an AUDIO output: {"waveform": [1, C, T], "sample_rate"}."""
    with av.open(BytesIO(data)) as container:
        stream = container.streams.audio[0]
        channels = stream.channels or 1
        frames = []
        for frame in container.decode(stream):
            samples = torch.from_numpy(frame.to_ndarray())
            if samples.shape[0] != channels:
                # Packed formats interleave channels in one row.
                samples = samples.reshape(-1, channels).t()
            frames.append(samples)
        sample_rate = stream.codec_context.sample_rate
    waveform = torch.cat(frames, dim=1)
    if not waveform.dtype.is_floating_point:
        waveform = waveform.float() / torch.iinfo(waveform.dtype).max
    return {"waveform": waveform.unsqueeze(0).contiguous(), "sample_rate": sample_rate}
