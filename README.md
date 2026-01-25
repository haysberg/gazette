# Gazette

Gazette est un agrégateur de flux RSS léger, conçu pour servir des sources d'information alternatives et indépendantes de gauche, principalement françaises et européennes.

> La sélection de sources se veut politiquement orientée. La gazette s'adresse avant tout à des militants et sympathisants de la gauche de rupture.

## Fonctionnalités

- **Agrégation de flux RSS** : Plus de 45 sources d'actualités alternatives
- **Mises à jour automatiques** : Actualisation toutes les 15 minutes
- **Performance optimisée** : Page statique pré-générée, compression gzip, images en AVIF
- **PWA** : Installable comme application mobile avec support hors-ligne
- **Accessibilité** : Compatible lecteurs d'écran pour les personnes malvoyantes
- **Responsive** : Fonctionne sur tous les appareils (téléphones anciens ou récents, tablettes, ordinateurs)
- **Flux RSS généré** : Permet de suivre l'agrégation depuis un lecteur RSS externe

## Technologies

**Backend**
- Python 3.14+
- APScheduler (tâches planifiées)
- SQLModel + SQLite en mémoire
- Feedparser (parsing RSS)
- Jinja2 (templates)

**Frontend**
- HTML/CSS/JavaScript vanilla
- DaisyUI (composants Tailwind CSS)
- Service Worker (fonctionnalité hors-ligne)

**Déploiement**
- Docker & Docker Compose
- static-web-server (serveur HTTP léger)

## Installation

### Prérequis

- Python 3.14 ou supérieur
- [uv](https://github.com/astral-sh/uv) (gestionnaire de paquets Python)

### Développement local

```bash
# Cloner le dépôt
git clone https://github.com/votre-repo/gazette.git
cd gazette

# Installer les dépendances
uv sync

# Lancer l'application
python3 app.py
```

### Déploiement Docker

```bash
# Lancer avec docker-compose
docker-compose up -d

# L'application est accessible sur le port 8000
# http://localhost:8000
```

## Configuration

### gazette.toml

Fichier de configuration des flux RSS à agréger. Chaque entrée contient :

```toml
[[feeds.feedlist]]
link = "https://exemple.com/rss"
domain = "exemple.com"
title = "Nom de la source"
image = "https://exemple.com/favicon.ico"
subtitle = "Description optionnelle"
```

### Variables d'environnement

| Variable | Description | Défaut |
|----------|-------------|--------|
| `LOGLEVEL` | Niveau de journalisation (DEBUG, INFO, WARNING, ERROR) | INFO |
| `TZ` | Fuseau horaire | Europe/Paris |

### sws.toml

Configuration du serveur web statique (cache, compression, etc.).

## Structure du projet

```
gazette/
├── app.py                 # Point d'entrée principal
├── gazette.toml           # Configuration des flux RSS
├── sws.toml               # Configuration du serveur web
├── pyproject.toml         # Configuration Python
├── Dockerfile             # Image Docker
├── docker-compose.yml     # Déploiement Docker
│
├── utils/                 # Modules utilitaires
│   ├── models.py          # Modèles SQLModel (Feed, Post)
│   ├── utils.py           # Logique principale
│   └── logs.py            # Configuration des logs
│
├── templates/             # Templates Jinja2
│   ├── index.html         # Page principale
│   ├── sources.html       # Page des sources
│   └── ...
│
├── static/                # Fichiers statiques générés
│   ├── index.html         # Page HTML générée
│   ├── feed.xml           # Flux RSS généré
│   ├── css/               # Styles
│   ├── js/                # Scripts
│   ├── favicons/          # Favicons des sources (AVIF)
│   └── ...
│
└── build_tools/           # Scripts de build
    ├── compress_all.py    # Minification CSS/JS
    ├── download_images.py # Téléchargement des favicons
    └── generate_opml.py   # Génération du fichier OPML
```

## Fonctionnement

1. **Initialisation** : Lecture de `gazette.toml` et création des entrées en base de données
2. **Mise à jour** : Toutes les 15 minutes, récupération des nouveaux articles de chaque flux
3. **Génération** : Création des fichiers statiques `index.html` et `feed.xml`
4. **Nettoyage** : Suppression automatique des articles de plus de 7 jours

Les articles sont organisés par date (aujourd'hui / hier) et affichés par ordre chronologique inverse.

## Outils de build

```bash
# Minifier les fichiers CSS et JS
python3 build_tools/compress_all.py

# Télécharger les favicons des sources
python3 build_tools/download_images.py

# Générer le fichier OPML
python3 build_tools/generate_opml.py

# Télécharger DaisyUI
python3 build_tools/download_daisy.py
```

## Licence

Voir le fichier [LICENSE](LICENSE) pour plus de détails.
