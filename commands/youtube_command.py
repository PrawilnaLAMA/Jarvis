import webbrowser
import urllib.request
import re
from core.utils import is_similar

class YouTubeCommand:
    def execute(self, message):
        words = message.split()
        for word in words:
            if is_similar(word.lower(), "youtube", threshold=0.7):
                query = message.split(word)[-1].strip().replace(' ', '_')
                html = urllib.request.urlopen(f"https://www.youtube.com/results?search_query={query}")
                video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())
                if video_ids:
                    video_url = f"https://www.youtube.com/watch?v={video_ids[0]}"
                    webbrowser.open(video_url)
                    return f"Otwieram YouTube."
        return None
