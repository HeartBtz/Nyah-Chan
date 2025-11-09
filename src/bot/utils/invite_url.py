import os
from dotenv import load_dotenv, find_dotenv

BASE_URL = "https://discord.com/api/oauth2/authorize"

# Default permission set: Manage Roles, View Channels, Send Messages, Add Reactions, Read Message History, Use Application Commands
DEFAULT_PERMISSIONS = (
    268435456  # Manage Roles
    | 1024      # View Channels
    | 2048      # Send Messages
    | 64        # Add Reactions
    | 65536     # Read Message History
    | 2147483648  # Use Application Commands
)


def build_invite_url(client_id: str, permissions: int = DEFAULT_PERMISSIONS, scopes: list[str] | None = None) -> str:
    if scopes is None:
        scopes = ["bot", "applications.commands"]
    scope_str = "%20".join(scopes)
    return f"{BASE_URL}?client_id={client_id}&permissions={permissions}&scope={scope_str}"


def main():
    load_dotenv(find_dotenv())
    client_id = os.getenv("APPLICATION_CLIENT_ID") or os.getenv("CLIENT_ID") or ""
    if not client_id:
        print("[ERREUR] APPLICATION_CLIENT_ID manquant. Ajoutez-le dans python_miwa_bot/.env (ex: APPLICATION_CLIENT_ID=1437188072033747118)")
        return
    permissions_env = os.getenv("INVITE_PERMISSIONS")
    if permissions_env:
        try:
            permissions = int(permissions_env)
        except ValueError:
            print("INVITE_PERMISSIONS invalide, utilisation du set par défaut.")
            permissions = DEFAULT_PERMISSIONS
    else:
        permissions = DEFAULT_PERMISSIONS
    url = build_invite_url(client_id, permissions)
    print("URL d'invitation :")
    print(url)


if __name__ == "__main__":
    main()
