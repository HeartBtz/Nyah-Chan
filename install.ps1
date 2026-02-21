############################################################
# Nyah-Chan — Script d'installation automatique (Windows)
############################################################
#Requires -Version 5.1

$ErrorActionPreference = "Stop"

# --- Couleurs ---
function Write-Info    { Write-Host "[OK] " -ForegroundColor Green -NoNewline; Write-Host $args }
function Write-Warn    { Write-Host "[!]  " -ForegroundColor Yellow -NoNewline; Write-Host $args }
function Write-Err     { Write-Host "[X]  " -ForegroundColor Red -NoNewline; Write-Host $args }
function Write-Ask     { Write-Host "[?]  " -ForegroundColor Cyan -NoNewline }

function Write-Banner {
    Write-Host @"

   _   _             _            _____ _
  | \ | |           | |          / ____| |
  |  \| |_   _  __ _| |__ ______| |    | |__   __ _ _ __
  |     | | | |/ _  | '_ \______| |    | '_ \ / _  | '_ \
  | |\  | |_| | (_| | | | |     | |____| | | | (_| | | | |
  |_| \_|\__, |\__,_|_| |_|      \_____|_| |_|\__,_|_| |_|
          __/ |
         |___/          Auto-Installer v4.0

"@ -ForegroundColor Cyan
}

Write-Banner

# --- Verifications ---
Write-Host "=== Verification des prerequis ===" -ForegroundColor White

# Check Python
$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 10) {
                $pythonCmd = $cmd
                Write-Info "Python $($Matches[1]).$($Matches[2]) detecte ($cmd)"
                break
            }
        }
    } catch { }
}

if (-not $pythonCmd) {
    Write-Err "Python 3.10+ n'est pas installe ou pas dans le PATH."
    Write-Host "  Telecharge Python depuis: https://www.python.org/downloads/"
    Write-Host "  N'oublie pas de cocher 'Add Python to PATH' pendant l'installation."
    exit 1
}

# --- Virtual environment ---
Write-Host ""
Write-Host "=== Creation de l'environnement virtuel ===" -ForegroundColor White

$createVenv = $true
if (Test-Path ".venv") {
    Write-Warn "Environnement .venv existant detecte"
    Write-Ask
    $recreate = Read-Host "Recreer l'environnement ? (o/N)"
    if ($recreate -match "^[oOyY]$") {
        Remove-Item -Recurse -Force .venv
    } else {
        Write-Info "Environnement existant conserve"
        $createVenv = $false
    }
}

if ($createVenv) {
    & $pythonCmd -m venv .venv
    Write-Info "Environnement .venv cree"
}

# Activation
$activateScript = Join-Path ".venv" "Scripts" "Activate.ps1"
if (-not (Test-Path $activateScript)) {
    Write-Err "Impossible de trouver le script d'activation: $activateScript"
    exit 1
}
. $activateScript
Write-Info "Environnement active"

# --- Dependencies ---
Write-Host ""
Write-Host "=== Installation des dependances ===" -ForegroundColor White

pip install --upgrade pip -q 2>&1 | Out-Null
pip install -r requirements.txt -q
Write-Info "Dependances installees"

# --- .env Configuration ---
Write-Host ""
Write-Host "=== Configuration du fichier .env ===" -ForegroundColor White

if (Test-Path ".env") {
    Write-Warn "Un fichier .env existe deja"
    Write-Ask
    $overwrite = Read-Host "Ecraser avec une nouvelle configuration ? (o/N)"
    if ($overwrite -notmatch "^[oOyY]$") {
        Write-Info "Configuration .env conservee"
        Write-Host ""
        Write-Host "=== Installation terminee ! ===" -ForegroundColor Green
        Write-Host ""
        Write-Info "Lancer le bot:        .\.venv\Scripts\Activate.ps1; python run_bot.py"
        Write-Info "Lancer le bot + web:  .\.venv\Scripts\Activate.ps1; python run_bot_with_web.py"
        Write-Host ""
        exit 0
    }
}

Write-Host ""
Write-Host "--- Token Discord ---" -ForegroundColor White
Write-Ask
$discordToken = Read-Host "Colle ton token Discord"
if ([string]::IsNullOrWhiteSpace($discordToken)) {
    Write-Err "Le token Discord est obligatoire !"
    exit 1
}

Write-Host ""
Write-Host "--- Discord OAuth2 (Panel Web) ---" -ForegroundColor White
Write-Host "  Configure OAuth2 sur https://discord.com/developers/applications"
Write-Host "  Redirect URI: http://localhost:8000/auth/callback"
Write-Host ""
Write-Ask
$clientId = Read-Host "Client ID de l'application Discord"
Write-Ask
$clientSecret = Read-Host "Client Secret de l'application Discord"

Write-Host ""
Write-Host "--- Panel web ---" -ForegroundColor White
Write-Ask
$webPort = Read-Host "Port du panel web (defaut: 8000)"
if ([string]::IsNullOrWhiteSpace($webPort)) { $webPort = "8000" }

Write-Ask
$webHost = Read-Host "Hote du panel web (defaut: 0.0.0.0)"
if ([string]::IsNullOrWhiteSpace($webHost)) { $webHost = "0.0.0.0" }

$defaultRedirect = "http://localhost:${webPort}/auth/callback"
Write-Ask
$redirectUri = Read-Host "Redirect URI OAuth2 (defaut: $defaultRedirect)"
if ([string]::IsNullOrWhiteSpace($redirectUri)) { $redirectUri = $defaultRedirect }

# Write .env
$envContent = @"
############################################################
# Nyah-Chan Discord Bot Configuration
############################################################

# --- Discord ---
DISCORD_TOKEN=$discordToken
USE_MEMBERS_INTENT=1
LOG_LEVEL=INFO

# --- Discord OAuth2 (Web Panel) ---
DISCORD_CLIENT_ID=$clientId
DISCORD_CLIENT_SECRET=$clientSecret
DISCORD_REDIRECT_URI=$redirectUri

# --- Web Panel ---
NYAH_WEB_HOST=$webHost
NYAH_WEB_PORT=$webPort

# --- Database ---
DATABASE_PATH=nyahchan.db
"@

Set-Content -Path ".env" -Value $envContent -Encoding UTF8
Write-Info "Fichier .env genere"

# Create necessary directories
New-Item -ItemType Directory -Force -Path "logs" | Out-Null
New-Item -ItemType Directory -Force -Path "static" | Out-Null
Write-Info "Dossiers logs/ et static/ crees"

# --- Summary ---
Write-Host ""
Write-Host "============================================" -ForegroundColor White
Write-Host "   Installation terminee avec succes !" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor White
Write-Host ""
Write-Host "  Panel web:        " -ForegroundColor Cyan -NoNewline
Write-Host "http://${webHost}:${webPort}"
Write-Host "  Redirect URI:     " -ForegroundColor Cyan -NoNewline
Write-Host "$redirectUri"
Write-Host "  Authentification: " -ForegroundColor Cyan -NoNewline
Write-Host "Discord OAuth2"
Write-Host ""
Write-Host "  Commandes de lancement:" -ForegroundColor White
Write-Host "    Bot seul:        " -NoNewline
Write-Host ".\.venv\Scripts\Activate.ps1; python run_bot.py" -ForegroundColor Green
Write-Host "    Bot + panel web: " -NoNewline
Write-Host ".\.venv\Scripts\Activate.ps1; python run_bot_with_web.py" -ForegroundColor Green
Write-Host ""
Write-Host "  Assure-toi d'avoir configure le Redirect URI sur le Developer Portal !" -ForegroundColor Yellow
Write-Host ""
