from urllib import urlopen
import re

def embed_weather(url):
    req = urlopen(url)
    text = req.read()
    text = text[text.find('.TODAY')+1:]
    text = text.split('&&', 1)[0]
    text = text.replace('<br> <br>', '\n\n')
    text = re.sub('</*(br|pre)[ /]*>', '', text)
    text = '\n'.join(['##' + x.replace('...', '\n') for x in text.split(' .')])
    return text.strip('\n ').lower()
