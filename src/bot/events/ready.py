import discord


def setup_ready_event(client: discord.Client):
    @client.event
    async def on_ready():
        assert client.user is not None
        print(f"Connecté comme {client.user} ({client.user.id})")
