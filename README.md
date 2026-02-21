# Nyah-Chan

Bot Discord modulaire en Python avec panel web d'administration et authentification Discord OAuth2.
Toute la configuration est stockée dans une base SQLite — aucun fichier JSON.

## Fonctionnalités

### Bot Discord
- **Modération** — `/ban`, `/kick`, `/timeout`, `/warn`, `/warnings`, `/unwarn`, `/purge`, `/serverinfo`, `/userinfo`, `/avatar`
- **Auto-modération** — Filtre mots interdits, spam de mentions, excès de majuscules (seuils configurables)
- **Keyword Responses** — Embeds automatiques déclenchées par mots-clés (cooldown anti-spam)
- **Role Triggers** — Attribution/retrait de rôles par mots-clés dans les messages
- **Grant Commands** — Commandes spéciales pour attribuer des rôles (`!vip @user`)
- **Ollama Q&A** — Réponses IA via un modèle Ollama local (optionnel)
- **Messages de bienvenue / au revoir** — Messages automatiques à l'arrivée ou au départ d'un membre
- **Escalade automatique** — Actions automatiques après N warnings (timeout, kick, ban)
- **Commandes utilitaires** — `!ping`, `!help`, `!roles`, `!stats`

### Panel Web Admin
- **Authentification Discord OAuth2** — connexion avec votre compte Discord
- **Multi-serveur** — sélecteur de serveur, configuration par guild
- **Dashboard** avec stats en temps réel (serveurs, utilisateurs, uptime)
- **Éditeur de keyword responses**
- **Éditeur de role triggers**
- **Éditeur de grant commands**
- **Viewer de warnings** avec suppression
- **Page Paramètres** — tous les seuils et options en un seul endroit
- **Design moderne** dark theme

## Prérequis

- **Python 3.10+**
- Un **bot Discord** ([Discord Developer Portal](https://discord.com/developers/applications))
- **OAuth2** configuré sur l'application Discord (voir ci-dessous)

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
- Créent un environnement virtuel `.venv`
- Installent les dépendances
- Génèrent un `.env` configuré
- Demandent token Discord, Client ID, Client Secret, et redirect URI

### Installation manuelle

```bash
git clone https://github.com/HeartBtz/Nyah-Chan.git
cd Nyah-Chan
python3 -m venv .venv
source .venv/bin/activate    # Linux/macOS
# .\.venv\Scripts\Activate.ps1  # Windows
pip install -r requirements.txt
cp .env.example .env
# Éditer .env avec vos identifiants
```

## Configuration Discord OAuth2

1. Rendez-vous sur le [Developer Portal](https://discord.com/developers/applications)
2. Sélectionnez votre application (celle du bot)
3. Allez dans **OAuth2 > General**
4. Copiez le **Client ID** et le **Client Secret**
5. Ajoutez un **Redirect URI** : `http://localhost:8000/auth/callback`
   (remplacez par votre domaine en production)
6. Renseignez ces valeurs dans `.env`

### Variables .env

| Variable | Description | Défaut |
|---|---|---|
| `DISCORD_TOKEN` | Token du bot Discord | *obligatoire* |
| `DISCORD_CLIENT_ID` | Client ID de l'application | *obligatoire pour le web* |
| `DISCORD_CLIENT_SECRET` | Client Secret OAuth2 | *obligatoire pour le web* |
| `DISCORD_REDIRECT_URI` | URI de callback OAuth2 | `http://localhost:8000/auth/callback` |
| `NYAH_WEB_HOST` | Hôte du panel web | `0.0.0.0` |
| `NYAH_WEB_PORT` | Port du panel web | `8000` |
| `DATABASE_PATH` | Chemin de la base SQLite | `nyahchan.db` |
| `USE_MEMBERS_INTENT` | Activer l'intent Members | `1` |
| `LOG_LEVEL` | Niveau de log | `INFO` |

> Toutes les autres options (préfixe, automod, welcome, goodbye, Ollama, escalade…) se configurent via la page **Paramètres** du panel web, par serveur.

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

Le panel web sera accessible sur `http://localhost:8000`.
Connectez-vous avec Discord, puis sélectionnez le serveur à administrer.

## Base de données

Toute la configuration est stockée dans `nyahchan.db` (SQLite, mode WAL) :

| Table | Contenu |
|---|---|
| `guild_config` | Configuration par serveur (préfixe, automod, welcome, Ollama…) |
| `keyword_responses` | Embeds déclenchées par mots-clés |
| `role_triggers` | Attribution de rôles par mots-clés |
| `grant_commands` | Commandes spéciales d'attribution de rôles |
| `warnings` | Historique des avertissements |
| `warn_escalation` | Règles d'escalade automatique |

La base est créée automatiquement au premier lancement.
Les anciens fichiers `moderation_warnings.json` sont migrés automatiquement.

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
| `/userinfo` | — | Informations d'un utilisateur |
| `/avatar` | — | Avatar d'un utilisateur |

## Structure du projet

```
Nyah-Chan/
  run_bot.py              # Lancement bot seul
  run_bot_with_web.py     # Lancement bot + panel web
  requirements.txt        # Dépendances Python
  .env                    # Configuration (non versionné)
  src/bot/
    main.py               # Point d'entrée du bot
    database.py           # Gestionnaire SQLite (toute la config)
    web.py                # Panel web FastAPI + OAuth2
    moderation.py         # Commandes slash de modération
    utils.py              # Utilitaires partagés
    features/
      automod.py          # Auto-modération
      commands.py         # Commandes texte (!ping, !help…)
      keyword_responses.py
      role_triggers.py
      grant_commands.py
      ollama_qna.py
      registry.py         # Registre et dispatch des features
    events/
      ready.py            # Événement on_ready
      message_create.py   # Dispatch des messages
      member_join.py      # Messages bienvenue/au revoir
  templates/              # Templates HTML (Jinja2)
  static/                 # CSS du panel web
```

## Sécurité

- Authentification Discord OAuth2 (session cookie httponly + samesite)
- Seuls les administrateurs des serveurs où le bot est présent peuvent configurer
- Protection XSS dans les templates
- SQLite WAL mode avec verrouillage thread-safe
- Vérification de hiérarchie des rôles pour toutes les commandes de modération
- Validation des noms de colonnes (anti SQL injection)

## Licence

MIT