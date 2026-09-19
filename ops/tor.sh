#!/bin/bash
# Raccourci court : installe Tor pour la navigation de l'agent.
# Le terminal de l'operateur coupe les commandes longues, d'ou ce nom.
exec bash "$(dirname "$0")/installer_tor.sh"
