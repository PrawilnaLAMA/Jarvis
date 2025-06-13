import time

class DiscordReader:
    def __init__(self, discord_client, command_handler, channel_id):
        self.discord_client = discord_client
        self.command_handler = command_handler
        self.channel_id = channel_id
        self.previous_message = ""

    def read_messages(self):
        while True:
            try:
                messages = self.discord_client.get_messages(self.channel_id)
                latest_message = messages[0]['content']
                latest_message_author = messages[0]['author']['username']

                if latest_message != self.previous_message:
                    if latest_message_author.lower() == 'jarvis.robot10':
                        continue
                    self.previous_message = latest_message
                    response = self.command_handler.handle_command(latest_message)
                    if response:
                        self.discord_client.send_message(self.channel_id, response)
            except Exception as e:
                print(f"Error: {e}")

            time.sleep(0.5)
