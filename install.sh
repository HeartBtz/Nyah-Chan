#!/usr/bin/env bash
############################################################
# Nyah-Chan — Script d'installation automatique (Linux/macOS)
############################################################
set -euo pipefail

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

banner() {
    echo -e "${CYAN}"
    echo "  _   _             _            _____ _                 "
    echo " | \ | |           | |          / ____| |                "
    echo " |  \| |_   _  __ _| |__ ______| |    | |__   __ _ _ __ "
    echo " |     | | | |/ _  | '_ \______| |    | '_ \ / _  | '_ \\"
    echo " | |\  | |_| | (_| | | | |     | |____| | | | (_| | | | |"
    echo " |_| \_|\__, |\__,_|_| |_|      \_____|_| |_|\__,_|_| |_|"
    echo "         __/ |                                            "
    echo "        |___/          Auto-Installer v1.0                "
    echo -e "${NC}"
}

info()    { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*"; }
ask()     { echo -en "${CYAN}[?]${NC} $* "; }

banner

# --- Vérifications préalables ---
echo -e "${BOLD}=== Vérification des prérequis ===${NC}"

if ! command -v python3 &>/dev/null; then
    error "Python 3 n'est pas installé."
    echo "  Installe-le avec: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if (( PY_MAJOR < 3 || (PY_MAJOR == 3 && PY_MINOR < 10) )); then
    error "Python 3.10+ requis (trouvé: $PY_VERSION)"
    exit 1
fi
info "Python $PY_VERSION détecté"

if ! python3 -c "import venv" &>/dev/null; then
    warn "Module venv manquant, tentative d'installation..."
    sudo apt install -y python3-venv 2>/dev/null || {
        error "Impossible d'installer python3-venv. Installe-le manuellement."
        exit 1
    }
fi
info "Module venv disponible"

if ! command -v git &>/dev/null; then
    warn "Git n'est pas installé (optionnel mais recommandé)"
fi

# --- Environnement virtuel ---
echo ""
echo -e "${BOLD}=== Création de l'environnement virtuel ===${NC}"

if [ -d ".venv" ]; then
    warn "Environnement .venv existant détecté"
    ask "Recréer l'environnement ? (o/N):"
    read -r RECREATE
    if [[ "$RECREATE" =~ ^[oOyY]$ ]]; then
        rm -rf .venv
        python3 -m venv .venv
        info "Environnement recréé"
    else
        info "Environnement existant conservé"
    fi
else
    python3 -m venv .venv
    info "Environnement .venv créé"
fi

# Activation
# shellcheck disable=SC1091
source .venv/bin/activate
info "Environnement activé"

# --- Installation des dépendances ---
echo ""
echo -e "${BOLD}=== Installation des dépendances ===${NC}"
pip install --upgrade pip -q
pip install -r requirements.txt -q
info "Dépendances installées"

# --- Configuration .env ---
echo ""
echo -e "${BOLD}=== Configuration du fichier .env ===${NC}"

if [ -f ".env" ]; then
    warn "Un fichier .env existe déjà"
    ask "Écraser avec une nouvelle configuration ? (o/N):"
    read -r OVERWRITE
    if [[ ! "$OVERWRITE" =~ ^[oOyY]$ ]]; then
        info "Configuration .env conservée"
        echo ""
        echo -e "${BOLD}=== Installation terminée ! ===${NC}"
        echo ""
        info "Lancer le bot:           source .venv/bin/activate && python run_bot.py"
        info "Lancer le bot + web:     source .venv/bin/activate && python run_bot_with_web.py"
        echo ""
        exit 0
    fi
fi

echo ""
echo -e "${BOLD}--- Token Discord ---${NC}"
ask "Colle ton token Discord:"
read -r DISCORD_TOKEN

if [ -z "$DISCORD_TOKEN" ]; then
    error "Le token Discord est obligatoire !"
    exit 1
fi

echo ""
echo -e "${BOLD}--- Discord OAuth2 (Panel Web) ---${NC}"
echo -e "  Configure OAuth2 sur https://discord.com/developers/applications"
echo -e "  Redirect URI: http://localhost:8000/auth/callback"
echo ""
ask "Client ID de l'application Discord:"
read -r DISCORD_CLIENT_ID
ask "Client Secret de l'application Discord:"
read -r DISCORD_CLIENT_SECRET

echo ""
echo -e "${BOLD}--- Panel web ---${NC}"
ask "Port du panel web (défaut: 8000):"
read -r WEB_PORT
WEB_PORT="${WEB_PORT:-8000}"

ask "Hôte du panel web (défaut: 0.0.0.0):"
read -r WEB_HOST
WEB_HOST="${WEB_HOST:-0.0.0.0}"

REDIRECT_URI="http://localhost:${WEB_PORT}/auth/callback"
ask "Redirect URI OAuth2 (défaut: ${REDIRECT_URI}):"
read -r REDIRECT_INPUT
REDIRECT_URI="${REDIRECT_INPUT:-$REDIRECT_URI}"

# Écriture du .env
cat > .env << ENVEOF
############################################################
# Nyah-Chan Discord Bot Configuration
############################################################

# --- Discord ---
DISCORD_TOKEN=${DISCORD_TOKEN}
USE_MEMBERS_INTENT=1
LOG_LEVEL=INFO

# --- Discord OAuth2 (Web Panel) ---
DISCORD_CLIENT_ID=${DISCORD_CLIENT_ID}
DISCORD_CLIENT_SECRET=${DISCORD_CLIENT_SECRET}
DISCORD_REDIRECT_URI=${REDIRECT_URI}

# --- Web Panel ---
NYAH_WEB_HOST=${WEB_HOST}
NYAH_WEB_PORT=${WEB_PORT}

# --- Database ---
DATABASE_PATH=nyahchan.db
ENVEOF

info "Fichier .env généré"

# Création des dossiers nécessaires
mkdir -p logs static

info "Dossiers logs/ et static/ créés"

# --- Résumé ---
echo ""
echo -e "${BOLD}============================================${NC}"
echo -e "${GREEN}   Installation terminée avec succès !${NC}"
echo -e "${BOLD}============================================${NC}"
echo ""
echo -e "  ${CYAN}Panel web:${NC}       http://${WEB_HOST}:${WEB_PORT}"
echo -e "  ${CYAN}Redirect URI:${NC}    ${REDIRECT_URI}"
echo -e "  ${CYAN}Authentification:${NC} Discord OAuth2"
echo ""
echo -e "  ${BOLD}Commandes de lancement:${NC}"
echo -e "    Bot seul:         ${GREEN}source .venv/bin/activate && python run_bot.py${NC}"
echo -e "    Bot + panel web:  ${GREEN}source .venv/bin/activate && python run_bot_with_web.py${NC}"
echo ""
echo -e "  ${YELLOW}⚠  Assure-toi d'avoir configuré le Redirect URI sur le Developer Portal !${NC}"
echo ""
