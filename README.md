# Gazette 💌

Gazette est un logiciel permettant d'agréger des flux RSS et de les servir dans une petite page légère, le but étant de permettre sa consommation de masse depuis un téléphone (récent ou non), depuis un navigateur, ou pour les personnes malvoyantes.

> La sélection de sources se veut politiquement orientée. La gazette s'adresse avant tout à des militants et sympathisants de la gauche de rupture.

## Features
- Application sur une seule page
- Calcul de la page toutes les 10 minutes pour être léger sur votre serveur
- Compression (Gazette supporte GZip par défaut, le setup du `docker-compose.yml` support aussi Brotli)
- Téléchargement des images sources pour une conversion en WebP
- Compatible WPA
- Compatible avec les lecteurs d'écran
- Responsive