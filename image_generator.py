import asyncio
import aiohttp
import base64
import logging
from typing import Optional
from config import STABILITY_API_KEY, IMAGE_PROMPTS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ImageGenerator:
    """Generate images using Stability AI"""
    
    def __init__(self):
        self.api_key = STABILITY_API_KEY
        self.api_host = "https://api.stability.ai"
        self.engine_id = "stable-diffusion-v1-6"
    
    async def generate_image(self, prompt: str) -> Optional[bytes]:
        """Generate image from prompt"""
        try:
            url = f"{self.api_host}/v1/generation/{self.engine_id}/text-to-image"
            
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            body = {
                "text_prompts": [
                    {
                        "text": prompt,
                        "weight": 1
                    }
                ],
                "cfg_scale": 7,
                "height": 1024,
                "width": 1024,
                "samples": 1,
                "steps": 30
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status == 200:
                        resp_json = await response.json()
                        image_data = base64.b64decode(resp_json["artifacts"][0]["base64"])
                        logger.info(f"✅ Image générée avec succès")
                        return image_data
                    else:
                        error = await response.text()
                        logger.error(f"Erreur Stability AI: {error}")
                        return None
        
        except Exception as e:
            logger.error(f"Erreur génération image: {e}")
            return None
    
    async def get_random_prompt(self) -> str:
        """Get random image prompt"""
        import random
        return random.choice(IMAGE_PROMPTS)
    
    async def generate_and_save(self, filename: str) -> Optional[str]:
        """Generate image and save locally"""
        try:
            prompt = await self.get_random_prompt()
            image_data = await self.generate_image(prompt)
            
            if image_data:
                import os
                os.makedirs("generated_images", exist_ok=True)
                filepath = f"generated_images/{filename}"
                with open(filepath, 'wb') as f:
                    f.write(image_data)
                logger.info(f"📸 Image sauvegardée: {filepath}")
                return filepath
            return None
        
        except Exception as e:
            logger.error(f"Erreur sauvegarde image: {e}")
            return None
