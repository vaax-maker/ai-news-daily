from .youtube import YouTubeParser
from .article import ArticleParser

def get_parser(url: str):
    youtube_parser = YouTubeParser()
    if youtube_parser.can_parse(url):
        return youtube_parser
    
    return ArticleParser()
