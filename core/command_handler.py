from commands.youtube_command import YouTubeCommand
from commands.google_command import GoogleCommand
from commands.time_command import TimeCommand
from commands.train_command import TrainCommand
from commands.discord_message_command import DiscordMessageCommand
from commands.ai_command import AICommand
from commands.shutdown_command import ShutdownCommand
from command_classifier import CommandClassifier

class CommandHandler:
    def __init__(self, model_path='./models/command_classifier.pkl'):
        self.classifier = CommandClassifier.load_model(model_path)
        print("Asystent głosowy załadowany!")
    
    def handle_command(self, text):
        """Przetwarzanie komendy tekstowej"""
        print(f"Otrzymano komendę: '{text}'")
        
        result = self.classifier.predict(text)
        
        print(f"Rozpoznano komendę: {result['command']}")
        print(f"Pewność: {result['confidence']:.3f}")
        
        # Wykonanie akcji na podstawie komendy
        action = self.execute_command(result['command'], text, result['confidence'])
        return action
    
    def execute_command(self, command, original_text, confidence):
        """Wykonanie odpowiedniej akcji na podstawie sklasyfikowanej komendy"""
        if confidence < 0.5:
            print("Niska pewność rozpoznania - proszę sprecyzować komendę")
            return
        
        actions = {
            'wyszukiwanie': GoogleCommand(),
            'discord': DiscordMessageCommand(),
            'muzyka': YouTubeCommand(),
            'ai': AICommand(),
            'czas': TimeCommand(),
            'pociąg': TrainCommand(),
            'shutdown': ShutdownCommand()
        }
        
        action = actions.get(command, self.unknown_command)
        return action(original_text)

    def unknown_command(self, text):
        print("⚠️ Nieznana komenda")

# class CommandHandler:
#     def __init__(self):
#         self.commands = {
#             "youtube": YouTubeCommand(),
#             "calculate": CalculatorCommand(),
#             "google": GoogleCommand(),
#             "time": TimeCommand(),
#             "train": TrainCommand(),
#             "discord_message": DiscordMessageCommand(),
#             "ai": AICommand(),
#             "shutdown": ShutdownCommand(),
#         }

#     def handle_command(self, message):
#         for command_name, command in self.commands.items():
#             response = command.execute(message)
#             if response:
#                 return response
#         return None
