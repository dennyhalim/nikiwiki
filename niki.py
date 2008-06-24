from wsgiref.simple_server import make_server
from markdown import markdown
from pam import authenticate
from cgi import FieldStorage
from base64 import b64decode
from os import getpid
import sys
import re

from nstore import FileStore

INSTALL_DIR = '/home/synack/src/nikiwiki'
PID_FILE = '/var/run/nikiwiki.pid'

def render(template, app, **kwargs):
	vars = {
		'STATIC_URL': 'http://static.example.com/niki',
		'SITE_NAME': 'nikiwiki',
		'SITE_MOTTO': 'everybody can edit, nobody can talk',
		'CONTENT_TYPE': 'text/html',
	}
	vars.update(kwargs)

	fd = open('%s/templates/%s' % (INSTALL_DIR, template), 'r')
	result = fd.read()
	fd.close()
	app.header('Content-type', vars['CONTENT_TYPE'])
	return result % vars

def valid_auth(environ):
	auth = environ.get('HTTP_AUTHORIZATION', None)
	if auth:
		auth = b64decode(auth[6:])
		username, password = auth.split(':')
		return authenticate(username, password)
	else:
		return False

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
			
		yield render('wiki.html', self.app,
			title=pagename,
			raw_content=content,
			content=markdown(content))
		return
	
	def POST(self, pagename=None):
		if not valid_auth(self.app.environ):
			self.app.status = '401 Unauthorized'
			self.app.header('WWW-Authenticate', 'Basic realm="Restricted"')
			yield 'Unauthorized'
			return
		if not pagename:
			self.app.status = '400 Bad Request'
			yield 'Bad request'
			return
		try:
			content = self.app.get_content()['content'].value
			self.data[pagename] = content
			yield markdown(content)
		except:
			self.app.status = '500 Internal Server Error'
			yield 'Unable to write content to data store\n'
	
	def PUT(self, pagename):
		self.POST(pagename)
	
	def DELETE(self, pagename):
		if not valid_auth(self.app.environ):
			self.app.status = '401 Unauthorized'
			self.app.header('WWW-Authenticate', 'Basic realm=Restricted')
			return
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
					sent_headers = False

					response = method(**groupdict)
					self.start_response(self.status, self.headers)
					return [x.encode('ascii', 'ignore') for x in response]
	
	def header(self, name, value):
		assert self.headers != None
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
	'/':					WikiPage,
	'/(?P<pagename>.+)':	WikiPage,
}

def main():
	server = make_server('', 8080, WSGIApp(urls))
	server.serve_forever()

if __name__ == '__main__':
	# Create a PID file
	fd = open(PID_FILE, 'w')
	fd.write(str(getpid()))
	fd.close()

	main()
