# Déploiement sur VPS sans Docker

Gazette se découpe en deux services indépendants :

- **`gazette`** (systemd) : récupère les flux toutes les 15 minutes et écrit les
  pages pré-rendues dans `/opt/gazette/static`, chacune accompagnée de ses copies
  `.br` et `.gz`.
- **`caddy`** : sert ce répertoire. Grâce à `precompressed br gzip`, il renvoie
  directement les fichiers déjà compressés et ne compresse jamais une réponse
  lui-même.

Aucune base de données à administrer : SQLite tourne en mémoire dans le processus.

## Prérequis

- Un VPS Debian/Ubuntu (512 Mo de RAM suffisent — pic mesuré à ~170 Mo)
- [`uv`](https://github.com/astral-sh/uv) (installe Python 3.14 tout seul)
- [Caddy](https://caddyserver.com/docs/install)
- `bun` **uniquement** si vous modifiez les sources Tailwind : le CSS compilé
  (`static/css/daisy.min.css`) est versionné dans le dépôt.

## Installation automatisée

```bash
# Sur le VPS, en root :
git clone https://github.com/haysberg/gazette.git /tmp/gazette-bootstrap
DOMAIN=insoumis.news /tmp/gazette-bootstrap/deploy/bootstrap.sh
```

`bootstrap.sh` est réexécutable : chaque étape vérifie si elle s'applique encore.
Il installe `uv` et Caddy si besoin, crée l'utilisateur système, clone le dépôt,
construit les assets, installe l'unité systemd et le Caddyfile (en y substituant
votre domaine), puis attend le premier rendu.

Ensuite, pour déployer une nouvelle version :

```bash
ssh vps 'sudo /opt/gazette/deploy/update.sh'
```

`update.sh` doit tourner en root (il a besoin de `systemctl`) et redescend vers le
compte de service pour le `git reset`, le `uv sync` et le build. Les visiteurs ne
voient rien : Caddy continue de servir les pages précédentes pendant le
redémarrage.

## Installation manuelle

Les étapes que `bootstrap.sh` automatise, si vous préférez les dérouler à la main :

```bash
# 1. Utilisateur système dédié, sans shell ni home
sudo useradd --system --create-home --home-dir /opt/gazette --shell /usr/sbin/nologin gazette

# 2. Récupération du code. On clone en root puis on donne l'arbre au service :
#    l'utilisateur gazette ne peut pas écrire dans /opt, et --create-home a déjà
#    rempli /opt/gazette (git refuse de cloner dans un répertoire non vide).
sudo git clone https://github.com/haysberg/gazette.git /tmp/gazette-clone
sudo bash -c 'shopt -s dotglob && mv /tmp/gazette-clone/* /opt/gazette/'
sudo rmdir /tmp/gazette-clone
sudo chown -R gazette:gazette /opt/gazette
sudo chmod 755 /opt/gazette
cd /opt/gazette

# 3. Dépendances : runtime + groupe build (csscompressor et jsmin, tous deux en
#    Python pur — aucune bibliothèque système requise sur le VPS).
sudo -u gazette uv sync --exact --no-default-groups --group build

# 4. Build des assets — l'ordre compte : compress_all.py produit
#    static/css/style.min.css et static/js/index.min.js dont generate_opml.py a besoin.
#    convert_icons.py et download_images.py ne sont PAS nécessaires ici : leurs
#    sorties (icônes AVIF, favicons) sont versionnées, et elles exigeraient
#    Pillow et cairosvg — donc libcairo — sur le serveur.
#    On appelle .venv/bin/python et non `uv run` : `uv run` resynchronise
#    l'environnement avec les groupes par défaut et réinstallerait tout le groupe dev.
sudo -u gazette ./.venv/bin/python build_tools/compress_all.py
sudo -u gazette ./.venv/bin/python build_tools/generate_opml.py

# 5. Service
sudo cp deploy/gazette.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gazette
sudo systemctl status gazette

# 6. Caddy (adaptez le nom de domaine dans le fichier avant de copier)
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo caddy validate --adapter caddyfile --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy doit pouvoir traverser `/opt/gazette` pour lire `static/` — les permissions
`755` par défaut suffisent. Ouvrez les ports 80 et 443 : Caddy provisionne TLS
automatiquement.

## Vérification

```bash
# La page doit arriver déjà compressée, sans travail de compression côté serveur
curl -sI -H 'Accept-Encoding: br' https://votre-domaine/ | grep -i content-encoding
# -> content-encoding: br

# Le flux RSS doit être du XML bien formé
curl -s https://votre-domaine/feed.xml | python3 -c 'import sys,xml.etree.ElementTree as E; E.fromstring(sys.stdin.read()); print("XML OK")'

journalctl -u gazette -f
```

## Mise à jour manuelle

Équivalent de `update.sh`, à la main :

```bash
cd /opt/gazette
sudo -u gazette git fetch origin
sudo -u gazette git reset --hard origin/main
sudo -u gazette uv sync --exact --no-default-groups --group build
sudo -u gazette ./.venv/bin/python build_tools/compress_all.py
sudo -u gazette ./.venv/bin/python build_tools/generate_opml.py
sudo systemctl restart gazette
```

`git reset --hard` plutôt que `git pull` : le build réécrit des fichiers suivis par
git (les `.br`/`.gz` des assets, `static/sw.js`, les `.min.*`), donc un `pull`
échouerait sur des modifications locales. Le reset repart d'un arbre propre.

Au redémarrage, le service refetch les 49 flux (~6 s) et régénère les pages avant
que le planificateur ne se déclenche : la base étant en mémoire, rien n'est
persisté entre deux exécutions.

## Variables d'environnement

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `GAZETTE_SERVE_STATIC` | `1` | `0` désactive le static-web-server intégré (à utiliser avec Caddy) |
| `GAZETTE_STATIC_DIR` | `static` | Répertoire des fichiers servis, lu **et** écrit |
| `GAZETTE_TEMPLATES_DIR` | `templates` | Répertoire des templates Jinja2 |
| `GAZETTE_CONFIG` | `gazette.toml` | Fichier de configuration des flux |
| `GAZETTE_UPDATE_MINUTES` | `15` | Intervalle de rafraîchissement |
