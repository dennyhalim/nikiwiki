#!/home/synack/src/nikiwiki/env/bin/python
from flup.server.fcgi_fork import WSGIServer
from subprocess import Popen, PIPE
from os import getpid

from pam import authenticate
from cgi import FieldStorage
from base64 import b64decode

from markdown import markdown
from nstore import FileStore
import sys
import re

import embed

LISTEN_PORT = 9609
INSTALL_DIR = '/home/synack/src/nikiwiki'
PID_FILE = '/var/run/nikiwiki.pid'
MARKDOWN_EXT = ['toc', 'fenced_code', 'codehilite', 'tables']

embedpattern = re.compile('\$(?P<funcname>.*)\((?P<args>.*)\)\$')

def render(template, app, **kwargs):
    vars = {
        'BASE_URL': 'https://synack.me/niki',
        'STATIC_URL': 'https://synack.me/niki/static',
        'SITE_NAME': 'niki',
        'SITE_MOTTO': '*insert fortune here*',
        'CONTENT_TYPE': 'text/html',
    }
    vars.update(kwargs)

    try:
        fortune = Popen(['/usr/games/fortune', '-s'], stdout=PIPE).stdout.read()
        vars['SITE_MOTTO'] = fortune
    except: pass

    app.header('Content-type', vars['CONTENT_TYPE'])
    return template % vars

def valid_auth(environ):
    auth = environ.get('HTTP_AUTHORIZATION', None)
    if auth:
        auth = b64decode(auth[6:])
        username, password = auth.split(':')
        return authenticate(username, password)
    else:
        return False

def patch_content(text):
    start = 0
    while start < len(text):
        match = embedpattern.search(text, start)
        if match:
            groups = match.groupdict()
            args = groups['args'].split(',')
            if hasattr(embed, groups['funcname']):
                func = getattr(embed, groups['funcname'])
                text = embedpattern.sub(func(*args), text)
            start = match.endpos
        else:
            break
    text = text.replace('\n', '  \n')
    return text

class WikiPage(object):
    def __init__(self):
        self.app = None
        self.data = FileStore('%s/data/' % INSTALL_DIR)

    def GET(self, pagename='Main_Page'):
        pagename = pagename.rstrip('/')
        try:
            content = self.data[pagename]
        except KeyError:
            try:
                entries = []
                for line in self.data[pagename + '/.index'].split('\n'):
                    entry = line.split(',', 1)
                    if len(entry) == 2:
                        entries.append(entry)
                entries.sort(key=lambda x: x[1], reverse=True)
                latest = entries[:5]
                content = ''
                for slug, timestamp in latest:
                    content += self.data[pagename + '/' + slug]
                    content += '\n***\n' 
                content += '#### Older posts\n\n'
                for slug, timestamp in entries:
                    content += '[%s](%s/%s)  \n' % (slug, pagename, slug)
            except KeyError:
                content = self.data['Not_Found']
            
        yield render(self.data['templates/wiki.html'], self.app,
            title=pagename,
            raw_content=content,
            content=markdown(patch_content(content), MARKDOWN_EXT))
        return
    
    def POST(self, pagename=None):
        if not pagename:
            self.app.status = '400 Bad Request'
            yield 'Bad request'
            return
        try:
            content = self.app.get_content()['content'].value
            self.data[pagename] = content
            yield markdown(patch_content(content), MARKDOWN_EXT)
        except:
            self.app.status = '500 Internal Server Error'
            yield 'Unable to write content to data store\n'
    
    def PUT(self, pagename):
        self.POST(pagename)
    
    def DELETE(self, pagename):
        del self.data[pagename]
        return

class WSGIApp(object):
    def __init__(self, urls=None):
        self.load_urls(urls)
    
    def __call__(self, environ, start_response):
        self.environ = environ
        self.start_response = start_response
        self.headers = []
        self.status = '200 OK'
        return self.handle_request()
    
    def handle_request(self):
        for url in self.urls:
            match = url.match(self.environ['PATH_INFO'])
            if match:
                groupdict = match.groupdict()
                if not groupdict:
                    groupdict = {}
                handler = self.urls[url]()
                handler.app = self
                if hasattr(handler, self.environ['REQUEST_METHOD']):
                    method = getattr(handler, self.environ['REQUEST_METHOD'])

                    response = method(**groupdict)
                    response = [x.encode('ascii', 'ignore') for x in response]
                    self.header('Content-Length', str(sum([len(x) for x in response])))
                    self.start_response(self.status, self.headers)
                    return response
    
    def header(self, name, value):
        self.headers.append((name, value))
    
    def get_content(self):
        input = self.environ['wsgi.input']
        form = FieldStorage(fp=input, environ=self.environ, keep_blank_values=True)
        return form
    
    def load_urls(self, urls):
        self.urls = {}
        for url in urls:
            handler = urls[url]
            url = re.compile(url)
            self.urls[url] = handler

urls = {
    '^/niki/(?P<pagename>.+)$': WikiPage,
    '^/niki/$':                 WikiPage,
}

def main():
    server = WSGIServer(WSGIApp(urls), bindAddress=('0.0.0.0', LISTEN_PORT), debug=True).run()

if __name__ == '__main__':
    main()
