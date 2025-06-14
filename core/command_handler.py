from commands.youtube_command import YouTubeCommand
from commands.calculator_command import CalculatorCommand
from commands.google_command import GoogleCommand
from commands.time_command import TimeCommand
from commands.train_command import TrainCommand
from commands.discord_message_command import DiscordMessageCommand

class CommandHandler:
    def __init__(self, discord_client):
        self.discord_client = discord_client
        self.commands = {
            "youtube": YouTubeCommand(),
            "calculate": CalculatorCommand(),
            "google": GoogleCommand(),
            "time": TimeCommand(),
            "train": TrainCommand(),
            "discord_message": DiscordMessageCommand(),
        }

    def handle_command(self, message):
        for command_name, command in self.commands.items():
            response = command.execute(message)
            if response:
                return response
        return None
