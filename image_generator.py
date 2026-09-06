import asyncio
import base64
import logging
from typing import Optional

try:
    import aiohttp
except ImportError:  # pragma: no cover - generation desactivee sans dependance HTTP
    aiohttp = None

from config import (
    IMAGE_API_HOST,
    IMAGE_CFG_SCALE,
    IMAGE_HEIGHT,
    IMAGE_MODEL,
    IMAGE_NEGATIVE_PROMPT,
    IMAGE_PROMPTS,
    IMAGE_PROVIDER,
    IMAGE_SEED,
    IMAGE_STEPS,
    IMAGE_WIDTH,
    REPLICATE_API_TOKEN,
    STABILITY_API_KEY,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ImageGenerator:
    """Generate images with Replicate FLUX by default, Stability as fallback."""

    STABILITY_DEFAULT_MODEL = "stable-diffusion-xl-1024-v1-0"
    REPLICATE_DEFAULT_MODEL = "black-forest-labs/flux-1.1-pro"

    def __init__(self):
        self.provider = IMAGE_PROVIDER
        self.seed = IMAGE_SEED
        self.steps = IMAGE_STEPS
        self.cfg_scale = IMAGE_CFG_SCALE
        self.width = IMAGE_WIDTH
        self.height = IMAGE_HEIGHT
        self.negative_prompt = IMAGE_NEGATIVE_PROMPT
        if self.provider == "replicate":
            self.api_key = REPLICATE_API_TOKEN
            self.api_host = IMAGE_API_HOST or "https://api.replicate.com"
            self.model = IMAGE_MODEL or self.REPLICATE_DEFAULT_MODEL
        else:
            self.api_key = STABILITY_API_KEY
            self.api_host = IMAGE_API_HOST or "https://api.stability.ai"
            self.model = IMAGE_MODEL or self.STABILITY_DEFAULT_MODEL

    def _stability_body(self, prompt: str, negative_prompt: str) -> dict:
        text_prompts = [{"text": prompt, "weight": 1}]
        if negative_prompt:
            text_prompts.append({"text": negative_prompt, "weight": -1})
        return {
            "text_prompts": text_prompts,
            "cfg_scale": self.cfg_scale,
            "height": self.height,
            "width": self.width,
            "samples": 1,
            "steps": self.steps,
            "seed": self.seed,
        }

    def _replicate_body(self, prompt: str, negative_prompt: str) -> dict:
        return {
            "input": {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "seed": self.seed,
                "guidance_scale": self.cfg_scale,
                "num_inference_steps": self.steps,
                "aspect_ratio": "custom",
                "width": self.width,
                "height": self.height,
                "output_format": "png",
                "prompt_upsampling": False,
            }
        }

    async def generate_image(
        self, prompt: str, negative_prompt: Optional[str] = None
    ) -> Optional[bytes]:
        """Generate image from prompt."""
        try:
            negative = (
                negative_prompt if negative_prompt is not None else self.negative_prompt
            )
            if self.provider == "replicate":
                return await self._generate_with_replicate(prompt, negative)
            return await self._generate_with_stability(prompt, negative)
        except Exception as e:
            logger.error(f"Erreur génération image: {e}")
            return None

    async def _generate_with_stability(
        self, prompt: str, negative_prompt: str
    ) -> Optional[bytes]:
        if aiohttp is None:
            logger.error("aiohttp manquant")
            return None
        url = f"{self.api_host}/v1/generation/{self.model}/text-to-image"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"******",
        }
        body = self._stability_body(prompt, negative_prompt)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status == 200:
                    resp_json = await response.json()
                    image_data = base64.b64decode(resp_json["artifacts"][0]["base64"])
                    logger.info("✅ Image générée avec succès")
                    return image_data
                error = await response.text()
                logger.error(f"Erreur Stability AI: {error}")
                return None

    async def _generate_with_replicate(
        self, prompt: str, negative_prompt: str
    ) -> Optional[bytes]:
        if aiohttp is None:
            logger.error("aiohttp manquant")
            return None
        if not self.api_key:
            logger.error("REPLICATE_API_TOKEN manquant")
            return None

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"******",
        }
        url = f"{self.api_host}/v1/models/{self.model}/predictions"
        body = self._replicate_body(prompt, negative_prompt)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status not in (200, 201):
                    error = await response.text()
                    logger.error(f"Erreur Replicate: {error}")
                    return None
                prediction = await response.json()

            poll_url = prediction.get("urls", {}).get("get")
            if not poll_url and prediction.get("id"):
                poll_url = f"{self.api_host}/v1/predictions/{prediction['id']}"
            if not poll_url:
                logger.error("Réponse Replicate inattendue: URL de suivi absente")
                return None

            for _ in range(60):
                status = prediction.get("status")
                if status == "succeeded":
                    return await self._download_replicate_output(session, prediction)
                if status in {"failed", "canceled"}:
                    logger.error(f"Erreur Replicate: {prediction.get('error') or status}")
                    return None
                await asyncio.sleep(1)
                async with session.get(
                    poll_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as follow_up:
                    if follow_up.status != 200:
                        error = await follow_up.text()
                        logger.error(f"Erreur suivi Replicate: {error}")
                        return None
                    prediction = await follow_up.json()

            logger.error("Timeout Replicate: génération inachevée")
            return None

    async def _download_replicate_output(
        self, session, prediction: dict
    ) -> Optional[bytes]:
        output = prediction.get("output")
        image_url = output[0] if isinstance(output, list) and output else output
        if not isinstance(image_url, str) or not image_url:
            logger.error("Réponse Replicate inattendue: image absente")
            return None
        async with session.get(
            image_url,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as response:
            if response.status != 200:
                logger.error(f"Téléchargement image impossible: {await response.text()}")
                return None
            logger.info("✅ Image générée avec succès")
            return await response.read()

    async def get_random_prompt(self) -> str:
        """Get random image prompt."""
        import random

        return random.choice(IMAGE_PROMPTS)

    async def generate_and_save(self, filename: str) -> Optional[str]:
        """Generate image and save locally."""
        try:
            prompt = await self.get_random_prompt()
            image_data = await self.generate_image(prompt)

            if image_data:
                import os

                os.makedirs("generated_images", exist_ok=True)
                filepath = f"generated_images/{filename}"
                with open(filepath, "wb") as f:
                    f.write(image_data)
                logger.info(f"📸 Image sauvegardée: {filepath}")
                return filepath
            return None

        except Exception as e:
            logger.error(f"Erreur sauvegarde image: {e}")
            return None
