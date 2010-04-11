#!/home/synack/src/nikiwiki/env/bin/python
from wsgiref.simple_server import make_server, WSGIRequestHandler
from subprocess import Popen, PIPE
from traceback import format_exc
from os import getpid
import os.path

from pam import authenticate
from cgi import FieldStorage
from base64 import b64decode

from webob import Request, Response
from webob.exc import *
from markdown import markdown
from nstore import FileStore
import sys
import re

import embed

LISTEN_PORT = 8082
INSTALL_DIR = '/home/synack/tmp/nikiwiki'
PID_FILE = '/var/run/nikiwiki.pid'
MARKDOWN_EXT = ['toc', 'fenced_code', 'codehilite', 'tables']

embedpattern = re.compile('\$(?P<funcname>.*)\((?P<args>.*)\)\$')

def render(template, **kwargs):
    vars = {
        'BASE_URL': 'http://synack.me:8082',
        'STATIC_URL': 'http://synack.me:8082/static',
        'SITE_NAME': 'niki',
        'SITE_MOTTO': '*insert fortune here*',
    }
    vars.update(kwargs)

    try:
        fortune = Popen(['/usr/games/fortune', '-s'], stdout=PIPE).stdout.read()
        vars['SITE_MOTTO'] = fortune
    except: pass

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
        self.data = FileStore('%s/data/' % INSTALL_DIR)

    def GET(self, request, pagename='Main_Page'):
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
            
        return Response(status=200, body=render(
            self.data['templates/wiki.html'],
            title=pagename,
            raw_content=content,
            content=markdown(patch_content(content), MARKDOWN_EXT)))
    
    def POST(self, request, pagename=None):
        if not pagename:
            return HTTPBadRequest()
        try:
            content = request.POST['content']
            self.data[pagename] = content
            return Response(status=200, body=markdown(patch_content(content), MARKDOWN_EXT))
        except:
            return HTTPInternalServerError(explanation='Unable to write content to data store')
    
    def PUT(self, request, pagename):
        return self.POST(request, pagename)
    
    def DELETE(self, request, pagename):
        del self.data[pagename]
        return Response(status=200)

class StaticFile(object):
    def GET(self, request, filename):
        path = os.path.normcase(os.path.normpath(os.path.join(INSTALL_DIR, 'static/', filename)))
        if not path.startswith(INSTALL_DIR):
            return HTTPBadRequest()
        if not os.path.exists(path):
            return HTTPNotFound()
        return Response(status=200, body=file(path).read())


class WSGIApp(object):
    def __init__(self, urls):
        self.urls = [(re.compile(pattern), handler) for pattern, handler in urls]
    
    def __call__(self, environ, start_response):
        request = Request(environ)

        response = None
        for pattern, handler in self.urls:
            match = pattern.match(request.path_info)
            if match:
                groupdict = match.groupdict()
                if not groupdict:
                    groupdict = {}

                handler = handler()
                if hasattr(handler, request.method.upper()):
                    method = getattr(handler, request.method.upper())
                    try:
                        response = method(request, **groupdict)
                    except:
                        response = Response(status=500, body=format_exc())
                        response.headers.add('Content-type', 'text/plain')
                    break

        if not response:
            response = HTTPNotFound()
        return response(environ, start_response)

urls = [
    ('^/static/(?P<filename>.*)$',   StaticFile),
    ('^/(?P<pagename>.+)$',          WikiPage),
    ('^/$',                          WikiPage),
]

def main():
    app = WSGIApp(urls)

    wsgi = WSGIRequestHandler
    def address_string(self):
        return self.client_address[0]
    wsgi.address_string = address_string

    server = make_server('0.0.0.0', LISTEN_PORT, app, handler_class=wsgi)
    server.serve_forever()

if __name__ == '__main__':
    main()
