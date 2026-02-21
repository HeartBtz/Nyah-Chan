# Nyah-Chan

Bot Discord modulaire en Python avec panel web d'administration.

## Fonctionnalites

### Bot Discord
- **Moderation** — `/ban`, `/kick`, `/timeout`, `/warn`, `/warnings`, `/unwarn`, `/purge`, `/serverinfo`
- **Keyword Responses** — Embeds automatiques declenchees par mots-cles (cooldown anti-spam)
- **Role Triggers** — Attribution/retrait de roles par mots-cles dans les messages
- **Grant Commands** — Commandes speciales pour attribuer des roles (`!vip @user`)
- **Ollama Q&A** — Reponses IA via un modele Ollama local (optionnel)
- **Messages de bienvenue** — Embeds automatiques a l'arrivee d'un membre
- **Commandes utilitaires** — `!ping`, `!help`, `!roles`, `!stats`

### Panel Web Admin
- **Dashboard** avec stats en temps reel (serveurs, utilisateurs, latence, uptime)
- **Editeur de keyword responses** avec previsualisation d'embed Discord
- **Editeur de role triggers**
- **Editeur de grant commands**
- **Authentification par mot de passe** (session securisee)
- **Design moderne** dark theme

## Prerequis

- **Python 3.10+**
- Un **token Discord** ([Discord Developer Portal](https://discord.com/developers/applications))

## Installation rapide

### Linux / macOS
```bash
git clone https://github.com/HeartBtz/Nyah-Chan.git
cd Nyah-Chan
chmod +x install.sh
./install.sh
```

### Windows (PowerShell)
```powershell
git clone https://github.com/HeartBtz/Nyah-Chan.git
cd Nyah-Chan
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install.ps1
```

Les scripts d'installation :
- Creent un environnement virtuel `.venv`
- Installent les dependances
- Generent un `.env` configure avec un mot de passe admin aleatoire
- Demandent ton token Discord, prefixe, et options de moderation/bienvenue

## Installation manuelle

```bash
git clone https://github.com/HeartBtz/Nyah-Chan.git
cd Nyah-Chan
python3 -m venv .venv
source .venv/bin/activate    # Linux/macOS
# .\.venv\Scripts\Activate.ps1  # Windows
pip install -r requirements.txt
cp .env.example .env
# Editer .env avec ton token et tes preferences
```

## Configuration

Toute la configuration se fait via le fichier `.env` :

| Variable | Description | Defaut |
|---|---|---|
| `DISCORD_TOKEN` | Token du bot Discord | *obligatoire* |
| `PREFIX` | Prefixe des commandes texte | `!` |
| `WEB_SECRET_KEY` | Mot de passe du panel admin | *obligatoire* |
| `NYAH_WEB_HOST` | Hote du panel web | `0.0.0.0` |
| `NYAH_WEB_PORT` | Port du panel web | `8000` |
| `MOD_LOG_CHANNEL_ID` | Channel pour les logs de moderation | *(vide)* |
| `WELCOME_ENABLED` | Activer les messages de bienvenue | `0` |
| `WELCOME_CHANNEL_ID` | Channel de bienvenue | *(vide)* |
| `WELCOME_MESSAGE` | Template du message | `Bienvenue {mention}...` |
| `OLLAMA_ENABLED` | Activer le Q&A Ollama | `0` |
| `OLLAMA_BASE_URL` | URL du serveur Ollama | `http://localhost:11434` |
| `OLLAMA_MODEL` | Modele a utiliser | `llama3` |

## Lancement

### Bot seul
```bash
source .venv/bin/activate
python run_bot.py
```

### Bot + Panel web
```bash
source .venv/bin/activate
python run_bot_with_web.py
```

Le panel web sera accessible sur `http://localhost:8000` (ou le port configure).

## Fichiers JSON de configuration

Ces fichiers sont geres automatiquement via le panel web :

| Fichier | Contenu |
|---|---|
| `keyword_responses.json` | Embeds declenchees par mots-cles |
| `role_triggers.json` | Attribution de roles par mots-cles |
| `grant_commands.json` | Commandes speciales d'attribution de roles |
| `moderation_warnings.json` | Historique des avertissements |

Des fichiers d'exemple sont fournis : `*.example.json`

## Commandes slash

| Commande | Permission requise | Description |
|---|---|---|
| `/ban` | Ban Members | Bannir un membre |
| `/kick` | Kick Members | Expulser un membre |
| `/timeout` | Moderate Members | Mettre en timeout |
| `/warn` | Moderate Members | Ajouter un avertissement |
| `/warnings` | Moderate Members | Voir les avertissements |
| `/unwarn` | Moderate Members | Retirer un avertissement |
| `/purge` | Manage Messages | Supprimer des messages (1-200) |
| `/serverinfo` | — | Informations du serveur |

## Commandes texte

| Commande | Description |
|---|---|
| `!help` | Liste des commandes |
| `!ping` | Latence du bot |
| `!roles` | Liste des roles du serveur |
| `!stats` | Statistiques du bot |

## Structure du projet

```
Nyah-Chan/
  install.sh              # Script d'installation Linux/macOS
  install.ps1             # Script d'installation Windows
  run_bot.py              # Lancement bot seul
  run_bot_with_web.py     # Lancement bot + panel web
  requirements.txt        # Dependances Python
  .env.example            # Exemple de configuration
  src/bot/
    main.py               # Point d'entree du bot
    web.py                # Panel web FastAPI
    moderation.py         # Commandes de moderation (slash)
    moderation_store.py   # Stockage des avertissements
    features/
      commands.py         # Commandes texte (!ping, !help, etc.)
      keyword_responses.py
      role_triggers.py
      grant_commands.py
      ollama_qna.py
      registry.py         # Registre des features
    events/
      ready.py            # Evenement on_ready
      message_create.py   # Dispatch des messages
      member_join.py      # Messages de bienvenue
    config/
      *_store.py          # Lecture/ecriture des configs JSON
  templates/              # Templates HTML du panel web
  static/                 # CSS du panel web
```

## Securite

- Authentification par session (cookie httponly + samesite)
- Comparaison de mot de passe timing-safe (hmac)
- Protection XSS dans les templates
- Ecritures atomiques des fichiers de configuration
- Verification de hierarchie des roles pour toutes les commandes de moderation
- Validation de chemin pour les fichiers GIF (anti path-traversal)

## Licence

MIT