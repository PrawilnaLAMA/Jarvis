from commands.youtube_command import YouTubeCommand
from commands.google_command import GoogleCommand
from commands.time_command import TimeCommand
from commands.train_command import TrainCommand
from commands.discord_message_command import DiscordMessageCommand
from commands.ai_command import AICommand
from commands.shutdown_command import ShutdownCommand
from commands.calendar_command import CalendarOpenCommand
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
        if confidence < 0.4:
            print("Niska pewność rozpoznania - proszę sprecyzować komendę")
            return
        
        actions = {
            'wyszukiwanie': GoogleCommand(),
            'discord': DiscordMessageCommand(),
            'muzyka': YouTubeCommand(),
            'otworz_kalendarz': CalendarOpenCommand("open"),
            'dodaj_do_kalendarza': CalendarOpenCommand("add"),
            'ai': AICommand(),
            'czas': TimeCommand(),
            'pociąg': TrainCommand(),
            'shutdown': ShutdownCommand()
        }
        
        action = actions.get(command, self.unknown_command)
        return action(original_text)

    def unknown_command(self, text):
        print("⚠️ Nieznana komenda")
