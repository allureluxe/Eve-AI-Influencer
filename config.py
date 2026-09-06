import os
from dotenv import load_dotenv

load_dotenv()

# Instagram
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")

# TikTok
TIKTOK_USERNAME = os.getenv("TIKTOK_USERNAME")
TIKTOK_PASSWORD = os.getenv("TIKTOK_PASSWORD")

# APIs
STABILITY_API_KEY = os.getenv("STABILITY_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

# Configuration
POST_FREQUENCY = int(os.getenv("POST_FREQUENCY", 2))
IMAGE_PROVIDER = os.getenv(
    "IMAGE_PROVIDER",
    "replicate" if REPLICATE_API_TOKEN else "stability",
).strip().lower()
IMAGE_API_HOST = os.getenv("IMAGE_API_HOST", "").strip()
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "").strip()
IMAGE_SEED = int(os.getenv("IMAGE_SEED", "774921"))
IMAGE_STEPS = int(os.getenv("IMAGE_STEPS", "36"))
IMAGE_CFG_SCALE = float(os.getenv("IMAGE_CFG_SCALE", "3.5"))
IMAGE_WIDTH = int(os.getenv("IMAGE_WIDTH", "1024"))
IMAGE_HEIGHT = int(os.getenv("IMAGE_HEIGHT", "1024"))
IMAGE_NEGATIVE_PROMPT = os.getenv(
    "IMAGE_NEGATIVE_PROMPT",
    "3d render, cgi, illustration, painting, anime, cartoon, digital art, "
    "airbrushed, smooth plastic skin, waxy, doll-like, porcelain skin, "
    "perfect symmetry, beauty filter, oversaturated, hdr, studio lighting, "
    "glamour shot, retouched, flawless skin, deformed hands, distorted face, "
    "watermark, text",
)

# Eve.AI Character
EVE_CHARACTER = {
    "name": "Eve",
    "age": 26,
    "origin": "French",
    "style": "Candid iPhone photo realism, natural light, unretouched skin texture",
    "personality": "Joie de vivre, naturelle, chaleureuse",
    "interests": ["Voyages", "Cafés", "Mode simple", "Restaurants", "Week-ends", "Photo"],
    "tone": "Friendly, engaging, natural",
}

EVE_IDENTITY_PROMPT = (
    "photo, candid iPhone photo of a 26-year-old French woman, long golden "
    "blonde hair with soft natural waves and loose flyaway strands, warm hazel "
    "eyes, light sun-kissed skin with faint freckles across the nose, "
    "heart-shaped face, high cheekbones, small gold hoop earrings, barely any "
    "makeup, visible skin pores and fine texture, light shine on the forehead "
    "and nose, faint under-eye shadows, slight facial asymmetry, unretouched, "
    "shot on iPhone 15 Pro, photojournalism, no filter, no beauty retouching"
)

IMAGE_SCENES = [
    "plain white t-shirt, head and shoulders, looking straight into the lens, "
    "relaxed natural expression, soft daylight from a window on her left, "
    "plain wall behind her, shallow depth of field, imperfect framing",
    "cream knit sweater in a small Paris cafe, coffee cup near frame, soft "
    "window light, candid shoulder-up composition, background gently blurred",
    "dark blazer over a white tee in an airport lounge, tired but warm eyes, "
    "carry-on handle just visible, natural overhead daylight, documentary style",
    "simple black top at a neighborhood restaurant, warm practical lighting, "
    "slight motion blur in the background, candid close portrait",
    "light denim jacket on a city sidewalk after golden hour, phone in hand, "
    "ambient street reflections, off-center framing, realistic smartphone photo",
    "white shirt at home in a quiet kitchen, messy loose hair, late-afternoon "
    "window light, intimate everyday portrait, shallow depth of field",
]
IMAGE_PROMPTS = [f"{EVE_IDENTITY_PROMPT}, {scene}" for scene in IMAGE_SCENES]

# Captions Templates
CAPTION_TEMPLATES = [
    "✨ La vie est trop courte pour ne pas vivre comme une reine 👑 #LuxeLifestyle #Eve",
    "🌍 Explorer le monde en style... c'est ma philosophie 💎 #Voyages #Luxe",
    "🍾 Les moments de luxe sont les meilleurs moments 🤍 #FineLife #Eve",
    "👗 Toujours classer, jamais ennuyeuse 💃 #Fashion #Luxe #Lifestyle",
    "✈️ La prochaine destination m'appelle... qui vient? 🏝️ #Wanderlust #Luxe",
    "💎 Le luxe n'est pas une destination, c'est une façon de vivre ✨ #EveStyle",
    "🏨 5 étoiles ou rien... c'est mon standard 👑 #LuxuryTravel #Eve",
    "⭐ La vie est belle quand tu la vis pleinement 😊 #JoieDeVivre #Luxe"
]

# Hashtags
HASTAGS = [
    "#EveAI", "#LuxeLifestyle", "#ArtificialIntelligence", "#InfluencerAI",
    "#Voyages", "#Luxe", "#Lifestyle", "#Fashion", "#TravelGram",
    "#JoieDeVivre", "#VieDeReve", "#ContentCreator", "#AIInfluencer"
]
