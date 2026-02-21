# Nyah-Chan

Bot Discord modulaire en Python avec panel web d'administration et authentification Discord OAuth2.
Toute la configuration est stockée dans une base SQLite — aucun fichier JSON.

## Fonctionnalités

### Modération
| Fonctionnalité | Description |
|---|---|
| **Commandes slash** | `/ban`, `/kick`, `/timeout`, `/tempban`, `/warn`, `/warnings`, `/unwarn`, `/purge` |
| **Auto-modération** | Filtre mots interdits, spam de mentions, excès de majuscules |
| **Anti-raid** | Détecte un afflux de joins et applique kick/ban automatique |
| **Anti-spam** | Détecte le flood de messages, auto-timeout |
| **Anti-lien** | Bloque URLs et invites Discord, whitelist de domaines |
| **Tempban** | Ban temporaire avec débannissement automatique (`/tempban 7d`) |
| **Audit logs avancés** | Log éditions/suppressions de messages, changements vocaux, pseudos |
| **Escalade automatique** | Actions auto après N warnings (timeout → kick → ban) |

### Engagement
| Fonctionnalité | Description |
|---|---|
| **XP / Niveaux** | Gain d'XP par message avec cooldown, annonces de level-up, récompenses de rôles |
| **Tickets** | Système de support par boutons persistants (`/ticket`) |
| **Sondages** | Sondages avec réactions emoji (`/poll`) |
| **Giveaways** | Tirages au sort automatiques (`/giveaway`) |
| **Rappels** | Rappels personnels en DM (`/remind`) |
| **Starboard** | Reposte les messages stars dans un salon dédié |

### Utilitaires
| Fonctionnalité | Description |
|---|---|
| **Custom commands** | Commandes textuelles personnalisées via la WebUI |
| **Messages programmés** | Envoi automatique à une heure précise ou récurrent |
| **Reaction roles** | Attribution de rôles par réaction emoji |
| **Keyword responses** | Embeds automatiques par mots-clés |
| **Role triggers** | Attribution/retrait de rôles par mots-clés |
| **Grant commands** | Commandes spéciales d'attribution de rôles (`!vip @user`) |
| **Ollama Q&A** | Réponses IA via un modèle Ollama local (optionnel) |
| **Sauvegarde config** | Export/import JSON de toute la configuration |

### Panel Web Admin
- **Authentification Discord OAuth2** — connexion sécurisée
- **Multi-serveur** — sélecteur de serveur, configuration par guild
- **Dashboard** — stats temps réel + graphiques d'activité (messages, joins, leaves)
- **Éditeurs** — Keywords, Role triggers, Grant commands, Custom commands, Reaction roles, Messages programmés
- **XP** — Leaderboard + récompenses de rôles par niveau
- **Warnings** — Historique avec suppression
- **Audit log WebUI** — Journal de toutes les actions admin
- **Gestion des rôles** — Recherche de membres, ajout/retrait de rôles depuis le web
- **Paramètres** — Toutes les options en un seul endroit (anti-raid, anti-spam, anti-lien, starboard, XP, tickets, Ollama, escalade…)
- **Sauvegarde** — Export/import de la configuration
- **Design moderne** dark theme responsive

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

> Toutes les options (préfixe, automod, anti-raid, anti-spam, anti-lien, starboard, XP, tickets, Ollama, escalade…) se configurent via la page **Paramètres** du panel web, par serveur.

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
| `guild_config` | Configuration par serveur (40+ colonnes : automod, anti-raid, starboard, XP…) |
| `keyword_responses` | Embeds déclenchées par mots-clés |
| `role_triggers` | Attribution de rôles par mots-clés |
| `grant_commands` | Commandes spéciales d'attribution de rôles |
| `warnings` | Historique des avertissements |
| `warn_escalation` | Règles d'escalade automatique |
| `user_xp` | XP et niveaux des membres |
| `xp_role_rewards` | Récompenses de rôles par niveau |
| `custom_commands` | Commandes personnalisées |
| `reaction_roles` | Mapping emoji → rôle |
| `scheduled_messages` | Messages programmés |
| `tempbans` | Bans temporaires en attente de débannissement |
| `reminders` | Rappels personnels |
| `giveaways` | Giveaways en cours |
| `polls` | Sondages |
| `starboard_entries` | Messages repostés au starboard |
| `activity_stats` | Statistiques d'activité par jour |
| `webui_audit_log` | Journal des actions WebUI |

La base est créée automatiquement au premier lancement.
Les colonnes manquantes sont ajoutées automatiquement lors des mises à jour.

## Commandes slash

| Commande | Permission requise | Description |
|---|---|---|
| `/ban` | Ban Members | Bannir un membre |
| `/kick` | Kick Members | Expulser un membre |
| `/timeout` | Moderate Members | Mettre en timeout |
| `/tempban` | Ban Members | Ban temporaire (ex : `/tempban 7d`) |
| `/warn` | Moderate Members | Ajouter un avertissement |
| `/warnings` | Moderate Members | Voir les avertissements |
| `/unwarn` | Moderate Members | Retirer un avertissement |
| `/purge` | Manage Messages | Supprimer des messages (1-200) |
| `/serverinfo` | — | Informations du serveur |
| `/userinfo` | — | Informations d'un utilisateur |
| `/avatar` | — | Avatar d'un utilisateur |
| `/rank` | — | Voir son niveau et XP |
| `/leaderboard` | — | Classement XP du serveur |
| `/poll` | — | Créer un sondage |
| `/giveaway` | Manage Guild | Lancer un giveaway |
| `/remind` | — | Créer un rappel personnel |
| `/ticket` | Manage Channels | Envoyer un embed de création de ticket |

## Commandes textuelles

| Commande | Description |
|---|---|
| `!ping` | Latence du bot |
| `!help` | Aide complète |
| `!roles` | Liste des rôles du serveur |
| `!stats` | Statistiques du bot |
| Custom commands | Définis via la WebUI (ex : `!hello`) |
| Grant commands | Définis via la WebUI (ex : `!vip @user`) |

> Le préfixe `!` est configurable par serveur via les paramètres.

## Structure du projet

```
Nyah-Chan/
  run_bot.py                  # Lancement bot seul
  run_bot_with_web.py         # Lancement bot + panel web
  requirements.txt            # Dépendances Python
  install.sh                  # Script d'installation Linux/macOS
  install.ps1                 # Script d'installation Windows
  .env.example                # Exemple de configuration
  src/bot/
    main.py                   # Point d'entrée du bot
    database.py               # Gestionnaire SQLite (18 tables, 40+ méthodes)
    web.py                    # Panel web FastAPI + OAuth2 + API REST
    moderation.py             # Commandes slash de modération
    tasks.py                  # Boucle de tâches (tempbans, rappels, giveaways)
    utils.py                  # Utilitaires partagés
    features/
      automod.py              # Auto-modération
      antiraid.py             # Protection anti-raid
      antispam.py             # Protection anti-spam
      antilink.py             # Protection anti-lien
      audit_logs.py           # Logs avancés (edit, delete, voice, nick)
      commands.py             # Commandes texte (!ping, !help…)
      custom_commands.py      # Commandes personnalisées
      keyword_responses.py    # Réponses par mots-clés
      role_triggers.py        # Attribution de rôles par mots-clés
      grant_commands.py       # Commandes grant
      reaction_roles.py       # Réaction → rôle
      starboard.py            # Starboard
      xp_system.py            # Système XP / niveaux
      tickets.py              # Système de tickets
      ollama_qna.py           # Q&A via Ollama
      registry.py             # Registre et dispatch des features
    events/
      ready.py                # Événement on_ready
      message_create.py       # Dispatch des messages + tracking
      member_join.py          # Bienvenue / au revoir + tracking
  templates/                  # Templates HTML Jinja2 (13 pages)
  static/                     # CSS du panel web
```

## Sécurité

- Authentification Discord OAuth2 (session cookie httponly + samesite)
- Seuls les administrateurs des serveurs où le bot est présent peuvent configurer
- Protection XSS dans les templates
- SQLite WAL mode avec verrouillage thread-safe (RLock réentrant)
- Vérification de hiérarchie des rôles pour toutes les commandes de modération
- Validation des noms de colonnes (anti SQL injection)
- Journal d'audit WebUI traçant toutes les modifications de configuration

## Licence

MIT
