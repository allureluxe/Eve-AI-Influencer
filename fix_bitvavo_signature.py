from pathlib import Path

path = Path("gold_bot/brokers/bitvavo.py")
text = path.read_text(encoding="utf-8")

old = '''    def _signer(self, horodatage: int, methode: str, chemin: str,\n                corps: Optional[dict]) -> str:\n        """HMAC-SHA256 de : horodatage + methode + /v2 + chemin + corps.\n\n        Le corps doit etre serialise exactement comme il sera envoye, d'ou\n        les separateurs compacts : un espace de difference et la signature\n        ne correspond plus.\n        """\n        message = f"{horodatage}{methode}/v2{chemin}"\n        if corps:\n            message += json.dumps(corps, separators=(",", ":"))\n        return hmac.new(self.config.api_secret.encode("utf-8"),\n                        message.encode("utf-8"), hashlib.sha256).hexdigest()\n'''

new = '''    def _signer(self, horodatage: int, methode: str, chemin: str,\n                corps: Optional[str]) -> str:\n        """Signe EXACTEMENT les octets du corps transmis a Bitvavo.\n\n        Bitvavo verifie HMAC-SHA256(timestamp + method + /v2 + path + body).\n        Le corps utilise pour la signature doit etre strictement identique\n        a celui envoye sur le reseau. On recoit donc ici la chaine JSON deja\n        serialisee, plutot qu'un dict qui pourrait etre reserialise differemment.\n        """\n        methode = str(methode).upper()\n        chemin = str(chemin)\n        message = f"{int(horodatage)}{methode}/v2{chemin}"\n        if corps:\n            message += corps\n        return hmac.new(\n            self.config.api_secret.encode("utf-8"),\n            message.encode("utf-8"),\n            hashlib.sha256,\n        ).hexdigest()\n'''

if old not in text:
    raise SystemExit("Bloc _signer attendu introuvable; aucune modification appliquee")
text = text.replace(old, new, 1)

old2 = '''        entetes = {"User-Agent": "gold-bot/1.0", "Accept": "application/json"}\n        donnees = None\n        if corps:\n            donnees = json.dumps(corps, separators=(",", ":")).encode("utf-8")\n            entetes["Content-Type"] = "application/json"\n\n        if signe:\n            if not (self.config.api_key and self.config.api_secret):\n                raise BrokerError("BITVAVO_API_KEY et BITVAVO_API_SECRET absents")\n            horodatage = int(time.time() * 1000)\n            entetes.update({\n                "bitvavo-access-key": self.config.api_key,\n                "bitvavo-access-signature": self._signer(horodatage, methode, requete, corps),\n                "bitvavo-access-timestamp": str(horodatage),\n                "bitvavo-access-window": str(self.config.window),\n            })\n'''

new2 = '''        entetes = {"User-Agent": "gold-bot/1.0", "Accept": "application/json"}\n        # Une seule serialisation : les memes octets servent a la signature\n        # ET au corps HTTP. C'est essentiel pour Bitvavo (erreur 309 sinon).\n        corps_json = json.dumps(corps, separators=(",", ":"), ensure_ascii=False) if corps else ""\n        donnees = corps_json.encode("utf-8") if corps_json else None\n        if corps_json:\n            entetes["Content-Type"] = "application/json"\n\n        if signe:\n            if not (self.config.api_key and self.config.api_secret):\n                raise BrokerError("BITVAVO_API_KEY et BITVAVO_API_SECRET absents")\n            horodatage = int(time.time() * 1000)\n            methode = str(methode).upper()\n            entetes.update({\n                "bitvavo-access-key": self.config.api_key,\n                "bitvavo-access-signature": self._signer(\n                    horodatage, methode, requete, corps_json),\n                "bitvavo-access-timestamp": str(horodatage),\n                "bitvavo-access-window": str(self.config.window),\n            })\n'''

if old2 not in text:
    raise SystemExit("Bloc _appel attendu introuvable; aucune modification appliquee")
text = text.replace(old2, new2, 1)
path.write_text(text, encoding="utf-8")
print("Correction Bitvavo appliquee dans", path)
