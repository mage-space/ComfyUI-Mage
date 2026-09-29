"""The Mage nodes. Each submits one generation to the Mage API, shows its
progress on the node, and returns the result as a ComfyUI value. Runs are paid
in Gems from the account whose API key is configured."""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

import httpx
from comfy import model_management
from comfy_execution.graph_utils import ExecutionBlocker
from mage_space import AsyncMage, MageError
from mage_space.types import ARCHITECTURES
from server import PromptServer

from . import mage_media as media
from .mage_config import KEY_HELP, build_config, check_media, load_api_key, option_inputs, parse_extra_config

CATEGORY = "Mage"
MAX_SEED = 2**31 - 1
OUTPUT_NOUNS = {"image": "an image", "video": "a video", "audio": "audio"}


def prompt_input() -> tuple:
    tooltip = "What to generate. Mention saved characters and references by @handle."
    return ("STRING", {"multiline": True, "default": "", "tooltip": tooltip})


def seed_input() -> tuple:
    # Fixed by default: re-queueing the same inputs reuses the cached output
    # instead of paying for a new generation.
    return (
        "INT",
        {
            "default": 0,
            "min": 0,
            "max": MAX_SEED,
            "control_after_generate": "fixed",
            "tooltip": "The same seed and inputs reproduce an output. Change it for a new variation.",
        },
    )


def progress(node_id: str | None, text: str) -> None:
    if node_id is not None:
        PromptServer.instance.send_progress_text(text, node_id)


async def upload_all(
    mage: AsyncMage,
    architecture: str,
    images: Any = None,
    first_frame: Any = None,
    last_frame: Any = None,
    video: Any = None,
) -> dict[str, Any]:
    """Checks that the architecture takes the node's media inputs, then uploads
    them and returns their Mage URLs."""
    check_media(
        architecture,
        references=0 if images is None else len(images),
        first_frame=first_frame is not None,
        last_frame=last_frame is not None,
        video=video is not None,
    )

    async def upload(data: bytes, content_type: str) -> str:
        ticket = await mage.uploads.upload(data, content_type=content_type)
        return ticket["url"]

    async def upload_image(image: Any) -> str | None:
        return None if image is None else await upload(media.images_to_png(image[:1])[0], "image/png")

    return {
        "references": [await upload(png, "image/png") for png in media.images_to_png(images)] if images is not None else [],
        "first_frame": await upload_image(first_frame),
        "last_frame": await upload_image(last_frame),
        "video": None if video is None else await upload(media.video_to_mp4(video), "video/mp4"),
    }


async def generate(mage: AsyncMage, architecture: str, config: dict[str, Any], node_id: str | None) -> dict[str, Any]:
    """Submits a generation and waits for it. Interrupting the queue cancels the
    request (its Gems are not returned). Returns the completed request."""
    request = await mage.generate(architecture, config)
    request_id = request["request_id"]
    started = time.monotonic()
    gems = request["billing"]["gems_charged"]

    def report(current: dict[str, Any]) -> None:
        if current["status"] in ("queued", "in_progress"):
            status = current["status"].replace("_", " ")
            progress(node_id, f"Mage: {status}, {int(time.monotonic() - started)}s ({gems} gems)")

    report(request)
    waiting = asyncio.ensure_future(mage.requests.wait(request, on_update=report))
    while not waiting.done():
        await asyncio.wait({waiting}, timeout=0.5)
        if model_management.processing_interrupted():
            waiting.cancel()
            with contextlib.suppress(MageError):
                await mage.requests.cancel(request_id)
            model_management.throw_exception_if_processing_interrupted()
    final = waiting.result()
    if final["status"] != "completed":
        error = final.get("error") or {"code": "cancelled", "message": "The request was cancelled."}
        raise RuntimeError(f"Mage request {request_id} {final['status']} ({error['code']}): {error['message']}")
    progress(node_id, f"Mage: done in {int(time.monotonic() - started)}s ({gems} gems)")
    return final


async def download(url: str) -> bytes:
    async with httpx.AsyncClient(follow_redirects=True, timeout=300) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


def client() -> AsyncMage:
    api_key = load_api_key()
    if not api_key:
        raise RuntimeError(KEY_HELP)
    return AsyncMage(api_key=api_key)


class MageMangoImage:
    ARCHITECTURE = "mango"
    OPTIONS = ("model_id", "aspect_ratio", "resolution")
    DESCRIPTION = "Generate or edit an image with Mango, Mage's flagship image model. Paid in Gems."
    CATEGORY = CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "url")
    OUTPUT_TOOLTIPS = ("The generated image.", "Where Mage stores the output for 30 days.")

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {"prompt": prompt_input(), **option_inputs(cls.ARCHITECTURE, cls.OPTIONS), "seed": seed_input()},
            "optional": {"images": ("IMAGE", {"tooltip": "Reference images, or the image to edit."})},
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    async def execute(self, prompt: str, seed: int, images: Any = None, unique_id: str | None = None, **options: Any):
        async with client() as mage:
            media_urls = await upload_all(mage, self.ARCHITECTURE, images=images)
            config = build_config(self.ARCHITECTURE, prompt=prompt, seed=seed, options=options, references=media_urls["references"])
            request = await generate(mage, self.ARCHITECTURE, config, unique_id)
        url = request["result"]["url"]
        return (media.image_from_bytes(await download(url)), url)


class MageCherryVideo:
    ARCHITECTURE = "cherry"
    OPTIONS = ("model_id", "aspect_ratio", "resolution", "duration")
    DESCRIPTION = "Generate a video with sound using Cherry, Mage's flagship video model. Paid in Gems."
    CATEGORY = CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ("VIDEO", "STRING")
    RETURN_NAMES = ("video", "url")
    OUTPUT_TOOLTIPS = ("The generated video.", "Where Mage stores the output for 30 days.")

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {"prompt": prompt_input(), **option_inputs(cls.ARCHITECTURE, cls.OPTIONS), "seed": seed_input()},
            "optional": {
                "images": ("IMAGE", {"tooltip": "Reference images."}),
                "video": ("VIDEO", {"tooltip": "A source video to edit or reference."}),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    async def execute(self, prompt: str, seed: int, images: Any = None, video: Any = None, unique_id: str | None = None, **options: Any):
        async with client() as mage:
            media_urls = await upload_all(mage, self.ARCHITECTURE, images=images, video=video)
            config = build_config(
                self.ARCHITECTURE,
                prompt=prompt,
                seed=seed,
                options=options,
                references=media_urls["references"],
                video=media_urls["video"],
            )
            request = await generate(mage, self.ARCHITECTURE, config, unique_id)
        url = request["result"]["url"]
        return (media.video_from_bytes(await download(url)), url)


class MageSeedAudio:
    ARCHITECTURE = "seed_audio"
    OPTIONS = ("duration",)
    DESCRIPTION = "Generate voices, dialogue, music, or sound effects from one prompt with Seed Audio. Paid in Gems."
    CATEGORY = CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ("AUDIO", "STRING")
    RETURN_NAMES = ("audio", "url")
    OUTPUT_TOOLTIPS = ("The generated audio.", "Where Mage stores the MP3 for 30 days.")

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {"prompt": prompt_input(), **option_inputs(cls.ARCHITECTURE, cls.OPTIONS), "seed": seed_input()},
            "optional": {"image": ("IMAGE", {"tooltip": "An image the audio should match."})},
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    async def execute(self, prompt: str, seed: int, image: Any = None, unique_id: str | None = None, **options: Any):
        async with client() as mage:
            media_urls = await upload_all(mage, self.ARCHITECTURE, images=None if image is None else image[:1])
            config = build_config(self.ARCHITECTURE, prompt=prompt, seed=seed, options=options, references=media_urls["references"])
            request = await generate(mage, self.ARCHITECTURE, config, unique_id)
        url = request["result"]["url"]
        return (media.audio_from_bytes(await download(url)), url)


class MageGenerate:
    DESCRIPTION = (
        "Run any Mage model. Set its fields in extra_config as JSON; see "
        "https://docs.mage.space/api/models/overview for each model's fields. Paid in Gems."
    )
    CATEGORY = CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ("STRING", "IMAGE", "VIDEO", "AUDIO")
    RETURN_NAMES = ("url", "image", "video", "audio")
    OUTPUT_TOOLTIPS = (
        "Where Mage stores the output for 30 days.",
        "The output, when the model makes images.",
        "The output, when the model makes video.",
        "The output, when the model makes audio.",
    )

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "architecture": (list(ARCHITECTURES), {"default": "mango", "tooltip": "The model family."}),
                "prompt": prompt_input(),
                "model_id": ("STRING", {"default": "", "tooltip": "A model variant, such as mango-v3s. Empty uses the default."}),
                "extra_config": (
                    "STRING",
                    {"multiline": True, "default": "{}", "tooltip": 'Other fields as a JSON object, such as {"aspect_ratio": "16:9"}.'},
                ),
                "seed": seed_input(),
            },
            "optional": {
                "images": ("IMAGE", {"tooltip": "Reference images."}),
                "first_frame": ("IMAGE", {"tooltip": "The image a video starts from."}),
                "last_frame": ("IMAGE", {"tooltip": "The image a video ends on."}),
                "video": ("VIDEO", {"tooltip": "A source video."}),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    async def execute(
        self,
        architecture: str,
        prompt: str,
        model_id: str,
        extra_config: str,
        seed: int,
        images: Any = None,
        first_frame: Any = None,
        last_frame: Any = None,
        video: Any = None,
        unique_id: str | None = None,
    ):
        extra = parse_extra_config(extra_config)
        options = {"model_id": model_id.strip()} if model_id.strip() else {}
        async with client() as mage:
            media_urls = await upload_all(mage, architecture, images=images, first_frame=first_frame, last_frame=last_frame, video=video)
            config = build_config(architecture, prompt=prompt, seed=seed, options=options, extra=extra, **media_urls)
            request = await generate(mage, architecture, config, unique_id)
        result = request["result"]
        data = await download(result["url"])
        name = ARCHITECTURES[architecture]["name"]

        def output(kind: str, decode: Any) -> Any:
            # Only the output matching the result carries a value; a node wired
            # to another one stops with this message instead of a type error.
            if result["type"] == kind:
                return decode(data)
            made = OUTPUT_NOUNS[result["type"]]
            return ExecutionBlocker(f"{name} made {made}, so the {kind} output is empty. Connect the {result['type']} output instead.")

        return (
            result["url"],
            output("image", media.image_from_bytes),
            output("video", media.video_from_bytes),
            output("audio", media.audio_from_bytes),
        )


NODE_CLASS_MAPPINGS = {
    "MageMangoImage": MageMangoImage,
    "MageCherryVideo": MageCherryVideo,
    "MageSeedAudio": MageSeedAudio,
    "MageGenerate": MageGenerate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MageMangoImage": "Mage Mango Image",
    "MageCherryVideo": "Mage Cherry Video",
    "MageSeedAudio": "Mage Seed Audio",
    "MageGenerate": "Mage Generate (any model)",
}
