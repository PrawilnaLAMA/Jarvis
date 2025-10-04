import webbrowser
import urllib.request
import re
from core.utils import is_similar
from core.separation_from_context import SeparationFromContext

class YouTubeCommand:
    def __call__(self, message):
        ai = SeparationFromContext()
        query = ai.extract_song_title(message)
        html = urllib.request.urlopen(f"https://www.youtube.com/results?search_query={query}")
        video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())
        if video_ids:
            video_url = f"https://www.youtube.com/watch?v={video_ids[0]}"
            webbrowser.open(video_url)
            return f"Otwieram YouTube."

