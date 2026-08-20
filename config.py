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

# Configuration
POST_FREQUENCY = int(os.getenv("POST_FREQUENCY", 2))

# Eve.AI Character
EVE_CHARACTER = {
    "name": "Eve",
    "style": "Blonde, sexy, luxury lifestyle",
    "personality": "Joie de vivre, motivante, provocante",
    "interests": ["Voyages", "Hôtels luxe", "Fashion", "Restaurants chics", "Voitures", "Bijoux"],
    "tone": "Friendly, engaging, inspiring"
}

# Image Generation Prompts
IMAGE_PROMPTS = [
    "Beautiful blonde woman in luxury hotel room, 5-star Maldives resort, wearing designer clothes, natural lighting, professional photography, lifestyle magazine style",
    "Blonde woman in Ferrari, luxury car interior, designer sunglasses, Mediterranean coast background, fashion editorial, high quality",
    "Woman in luxury restaurant, Michelin star dining, champagne glass, elegant dress, warm lighting, fine dining aesthetic",
    "Blonde woman at airport lounge, luxury travel, designer luggage, sophisticated style, lifestyle content",
    "Woman with luxury jewelry, Cartier, Rolex, diamond necklace, close-up, luxury lifestyle, glamorous photography",
    "Blonde woman in luxury villa, infinity pool, sunset, resort lifestyle, vacation vibes, paradise setting",
    "Woman in high-end fashion boutique, designer clothes, shopping, luxury brands, lifestyle content",
    "Blonde woman at beach resort, luxury vacation, bikini, tropical paradise, relaxation, lifestyle"
]

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
