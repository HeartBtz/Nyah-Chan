# Nyah‑Chan

Nyah‑Chan est un bot Discord modulaire écrit en Python, conçu pour :

- gérer des rôles via des mots‑clés et des commandes spéciales,
- répondre avec des embeds configurables (par mot‑clé),
- faire des Q&A via un modèle Ollama (LLM local),
- être administré via une **interface web** (webGUI) pour éditer les configs sans toucher aux fichiers JSON.

---

## Table des matières

- [Fonctionnalités](#fonctionnalités)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Configuration](#configuration)
- [Fichiers JSON de configuration](#fichiers-json-de-configuration)
- [Lancement du bot](#lancement-du-bot)
- [WebGUI d’administration](#webgui-dadministration)
- [Ajouter une nouvelle feature](#ajouter-une-nouvelle-feature)
- [Dépannage](#dépannage)

---

## Fonctionnalités

### Commandes de base

- `!ping` : répond « Pong! ».
- `!help` / `!aide` : affiche les commandes disponibles.
- `!roles` : liste les rôles du serveur (réservé aux membres avec la permission `manage_roles`).

### Triggers de rôles (`role_triggers`)

- Ajoute ou retire automatiquement un rôle quand un message contient certains mots.
- Création automatique du rôle si nécessaire (et repositionnement sous le rôle du bot).
- Option de réaction automatique :
	- ✅ quand un rôle est attribué,
	- 🗑️ quand un rôle est retiré.

### Grant commands (`grant_commands`)

- Crée des commandes dédiées, par ex. `!vip @membre`, pour attribuer un rôle.
- Limité à une liste d’IDs utilisateurs autorisés.
- Possibilité d’envoyer un GIF quand la commande réussit.
- Création + repositionnement automatique du rôle cible.

### Keyword responses (`keyword_responses`)

- Répond avec un **embed Discord** quand un message contient certains mots (ex : `egirl`).
- Plusieurs triggers possibles par embed (`egirl`, `e-girl`, `e girl`, etc.).
- Entièrement configurable via un fichier JSON **ou** via la webGUI.

### Q&A via Ollama (`ollama_qna`)

- Quand le bot est mentionné dans un message contenant un `?`, il envoie la question à un modèle Ollama (LLM local).
- Réponse renvoyée en un ou plusieurs messages (découpage automatique).

### WebGUI d’administration

- Serveur web FastAPI local (par défaut `http://127.0.0.1:8000`).
- Pages :
	- `/ui/keywords` : gestion des embeds de `keyword_responses`.
	- `/ui/roles` : gestion de `role_triggers`.
	- `/ui/grant` : gestion de `grant_commands`.
- Sauvegarde via API (JSON) qui réécrit directement les fichiers de configuration.
- Bouton global **"Recharger les configs"** dans la barre de navigation pour recharger à chaud les features (sans redémarrer le bot) après modification des JSON.

---

## Prérequis

- **Python** : 3.11 ou 3.12 recommandé.
- **Discord** :
	- Un bot créé dans le portail développeur Discord.
	- Token du bot.
	- Intents activés dans l’onglet *Bot* :
		- **MESSAGE CONTENT INTENT** (obligatoire).
		- **SERVER MEMBERS INTENT** si `USE_MEMBERS_INTENT=1`.

- **Ollama** (optionnel, pour la feature Q&A) :
	- Ollama installé et un modèle (ex : `llama3`) disponible.
	- Serveur accessible (par défaut `http://localhost:11434`).

---

## Installation

Cloner le dépôt :

```bash
git clone https://github.com/<ton-user>/<ton-repo>.git
cd Nyah-Chan
```

### Windows (PowerShell)

```powershell
# Créer et activer l'environnement virtuel
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Installer les dépendances
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Linux / macOS (bash)

```bash
# Créer et activer l'environnement virtuel
python3 -m venv .venv
source .venv/bin/activate

# Installer les dépendances
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

---

## Configuration

### 1. Fichier `.env`

Copier le modèle :

```bash
cp .env.example .env
# sous Windows PowerShell :
# copy .env.example .env
```

Éditer `.env` et renseigner au minimum :

```env
# Discord
DISCORD_TOKEN=TON_VRAI_TOKEN_DISCORD
PREFIX=!
USE_MEMBERS_INTENT=0
LOG_LEVEL=INFO  # DEBUG | INFO | WARNING | ERROR | CRITICAL
```

Options utiles :

```env
# Réactions automatiques (role_triggers)
REACTIONS_ENABLED=1   # 1 pour activer, 0 pour désactiver

# JSON de configuration (chemins optionnels, défaut = fichiers à la racine du projet)
ROLE_TRIGGERS_CONFIG=role_triggers.json
GRANT_COMMANDS_CONFIG=grant_commands.json
KEYWORD_RESPONSES_CONFIG=keyword_responses.json

# Modération
MOD_LOG_CHANNEL_ID=          # ID du salon texte pour les logs de modération
MOD_WARNINGS_PATH=           # Chemin du fichier JSON de warns (défaut: moderation_warnings.json)

# Ollama (optionnel)
OLLAMA_ENABLED=0
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
OLLAMA_TIMEOUT=60
```

---

## Commandes de modération (slash)

Le bot embarque un module de modération basé sur des **commandes slash**.

Permissions requises côté Discord (rôles/permissions sur le serveur) :

- `/ban` : permission **Bannir des membres** (`ban_members`).
- `/kick` : permission **Expulser des membres** (`kick_members`).
- `/timeout`, `/warn`, `/warnings`, `/unwarn` : permission **Modérer les membres** (`moderate_members`).

### Salon de logs de modération

En renseignant `MOD_LOG_CHANNEL_ID` dans `.env` avec l'ID d'un salon texte, le bot enverra un embed de log pour chaque action :

- bannissements (`/ban`),
- expulsions (`/kick`),
- timeouts (`/timeout`),
- avertissements (`/warn`).

Chaque log contient au minimum : le membre ciblé, le modérateur, la raison, et des informations supplémentaires (durée de timeout, ID d'avertissement, etc.).
Si `MOD_LOG_CHANNEL_ID` est vide ou invalide, les commandes continuent de fonctionner mais aucun log n'est envoyé.

### Avertissements (warns)

Les avertissements sont stockés dans un fichier JSON (par défaut `moderation_warnings.json` à la racine, ou le chemin défini dans `MOD_WARNINGS_PATH`).

Commandes principales :

- `/warn membre:User raison:str` : ajoute un avertissement pour le membre sur le serveur courant et log l'action.
- `/warnings membre:User` : liste les avertissements du membre sur le serveur courant (réponse éphémère).
- `/unwarn id:int` : supprime un avertissement par son ID (restreint au serveur courant).

Les IDs d'avertissements sont uniques et incrémentaux, mais la consultation et la suppression se font toujours par serveur.

---

## Fichiers JSON de configuration

Des fichiers `*.example.json` sont fournis comme modèles. Tu peux les copier et adapter si tu veux partir d'un exemple directement, mais ce n'est **pas obligatoire** :

- si les fichiers `role_triggers.json`, `grant_commands.json` ou `keyword_responses.json` n'existent pas, ils seront **créés automatiquement** avec une structure vide au premier accès.

### 1. `keyword_responses.json`

Contrôle les embeds envoyés par mot‑clé.

Tu peux soit laisser le bot créer un fichier vide, soit copier l'exemple :

```bash
cp keyword_responses.example.json keyword_responses.json
# ou sous Windows PowerShell :
# copy keyword_responses.example.json keyword_responses.json
```

Structure de l'exemple :

```json
{
	"embeds": [
		{
			"name": "egirl_warning",
			"triggers": ["egirl", "e-girl", "e girl"],
			"title": "À propos du terme « egirl »",
			"description": "Merci d'éviter ce terme sur le serveur...",
			"color": "red",
			"fields": [
				{
					"name": "Ce qu'on ne veut pas ❌",
					"value": "- Exemple 1\n- Exemple 2",
					"inline": false
				}
			],
			"footer": "En cas de doute, contacte un membre du staff ✨",
			"image_url": null,
			"thumbnail_url": null
		}
	]
}
```

- `color` peut être un **nom** (`red`, `blue`, `green`, `orange`, etc.) ou un code **hex** `#3498db` ou `3498db`.

### 2. `role_triggers.json`

Contrôle les triggers de rôles automatiques.

Tu peux soit laisser le bot créer un fichier vide, soit copier l'exemple :

```bash
cp role_triggers.example.json role_triggers.json
# Windows : copy role_triggers.example.json role_triggers.json
```

Structure de l'exemple :

```json
{
	"triggers": [
		{
			"trigger": "je veux le rôle vip",
			"role_name": "VIP",
			"remove_trigger": "enlever vip"
		}
	]
}
```

- Si `trigger` est dans le message → ajout du rôle.
- Si `remove_trigger` est dans le message → retrait du rôle.

### 3. `grant_commands.json`

Contrôle les commandes type `!vip`.

Tu peux soit laisser le bot créer un fichier vide, soit copier l'exemple :

```bash
cp grant_commands.example.json grant_commands.json
# Windows : copy grant_commands.example.json grant_commands.json
```

Structure de l'exemple :

```json
{
	"commands": [
		{
			"name": "vip",
			"role_name": "VIP",
			"allowed_user_ids": [123456789012345678, 987654321098765432],
			"gif_path": "pokeball-fable.gif"
		}
	]
}
```

---

## Lancement du bot

### Bot seul

#### Windows

```powershell
cd "C:\chemin\vers\Nyah-Chan"
.\.venv\Scripts\Activate.ps1
python .\run_bot.py
```

#### Linux / macOS

```bash
cd /chemin/vers/Nyah-Chan
source .venv/bin/activate
python run_bot.py
```

### Bot + WebGUI (recommandé)

#### Windows

```powershell
cd "C:\chemin\vers\Nyah-Chan"
.\.venv\Scripts\Activate.ps1
python .\run_bot_with_web.py
```

#### Linux / macOS

```bash
cd /chemin/vers/Nyah-Chan
source .venv/bin/activate
python run_bot_with_web.py
```

- Le bot se connecte à Discord.
- La webGUI est disponible par défaut sur : `http://127.0.0.1:8000`.

---

## WebGUI d’administration

Une fois `run_bot_with_web.py` lancé :

### `/ui/keywords`

- Gère `keyword_responses.json`.
- Permet de :
	- lister les embeds,
	- définir les **triggers** (séparés par des virgules),
	- configurer la couleur, le titre, la description, les champs, le footer, les URLs d’images,
	- gérer les champs d’embed via un petit formulaire (nom, valeur, inline) sans jamais écrire de JSON à la main,
	- visualiser en direct un aperçu de l’embed (titre, description, champs, footer, thumbnail),
	- sauvegarder (écrit le JSON sur disque).

### `/ui/roles`

- Gère `role_triggers.json`.
- Permet de :
	- définir `trigger`, `role_name`, `remove_trigger`,
	- sauvegarder la liste.

### `/ui/grant`

- Gère `grant_commands.json`.
- Permet de :
	- définir `name` (sans préfixe), `role_name`,
	- définir les `allowed_user_ids` (séparés par des virgules),
	- définir `gif_path`,
	- sauvegarder la liste.

> Note : les features chargent les configs au démarrage.  
> Après modification via la webGUI, clique sur **"Recharger les configs"** dans la barre du haut pour appliquer les changements immédiatement dans le bot, sans redémarrage.

---

## Ajouter une nouvelle feature

1. Créer un fichier dans `src/bot/features/`, par ex. `my_feature.py` :

	 ```python
	 import discord
	 from .registry import register

	 class MyFeature:
			 name = "my_feature"

			 def setup(self, client: discord.Client) -> None:
					 # Initialisation si besoin
					 pass

			 async def on_message(self, message: discord.Message) -> None:
					 if message.author.bot or message.guild is None:
							 return
					 if message.content == "!hello":
							 await message.channel.send("Hello depuis MyFeature !")

	 register(MyFeature())
	 ```

2. Importer la feature dans `src/bot/main.py` pour l’enregistrer :

	 ```python
	 from .features import my_feature  # noqa: F401
	 ```

3. Redémarrer le bot.

---

## Dépannage

- **`DISCORD_TOKEN manquant`**  
	→ Vérifier que `.env` existe et contient `DISCORD_TOKEN=` avec ton token (sans guillemets).

- **`PrivilegedIntentsRequired`**  
	→ Activer les intents nécessaires dans le portail Discord :
	- Message Content,
	- Members (si `USE_MEMBERS_INTENT=1`).

- **Les embeds ne s’envoient pas**  
	- Vérifier que `keyword_responses.json` est valide (JSON bien formé).
	- Vérifier que le `trigger` est bien dans la liste et présent dans le message.

- **La webGUI ne répond pas**  
	- S’assurer que tu as lancé `run_bot_with_web.py` et non `run_bot.py`.
	- Vérifier que `fastapi`, `uvicorn`, `Jinja2` sont bien installés :

		```bash
		python -m pip install -r requirements.txt
		```

---
