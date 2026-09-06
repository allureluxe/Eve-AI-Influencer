"""Luna — compagne virtuelle IA : messages, appel vocal et visio.

Luna est un personnage de fiction. Elle n'est pas une personne reelle et
ne pretend jamais l'etre.

    python3 luna.py app       l'application (navigateur)
    python3 luna.py chat      la meme conversation, dans le terminal
"""
from .persona import LUNA, Persona
from .chat import Luna
from .memoire import Memoire
from .limites import ADULTE, SENSUEL, TENDRE, PorteAdulte

__all__ = ["LUNA", "Persona", "Luna", "Memoire", "PorteAdulte",
           "TENDRE", "SENSUEL", "ADULTE"]
