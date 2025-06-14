import os

discord_config = {
    "user_token": os.getenv("USER_TOKEN"),
    "channel_ids": {
        key.split('_')[1].upper(): os.getenv(key)
        for key in os.environ.keys()
        if key.startswith("CHANNEL_")
    },
    "discord_channel_id": os.getenv("DISCORD_CHANNEL_ID"),
    "jarvis_token": os.getenv("JARVIS_TOKEN")
}
