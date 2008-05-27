from markdown import markdown
from os import unlink, stat, getpid
from base64 import b64decode
from pam import authenticate
import web
import sys

import traceback
from time import clock

from nstore import FileStore

INSTALL_DIR = '/home/synack/src/nikiwiki'
PID_FILE = '/var/run/nikiwiki.pid'
SSL_HOST = 'secure.example.com'

urls = (
	'/',					'WikiPage',
	'/(?P<pagename>.+)',	'WikiPage',
)

def render(template, **kwargs):
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
	web.header('Content-type', vars['CONTENT_TYPE'])
	return result % vars

def valid_auth():
	auth = web.ctx.environ.get('HTTP_AUTHORIZATION', None)
	if auth:
		auth = b64decode(auth[6:])
		username, password = auth.split(':')
		return authenticate(username, password)
	else:
		return False

class WikiPage(object):
	def __init__(self):
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
			
		print render('wiki.html', 
			title=pagename,
			raw_content=content,
			content=markdown(content))
	
	def POST(self, pagename):
		if not valid_auth():
			web.ctx.status = '401 Unauthorized'
			web.header('WWW-Authenticate', 'Basic realm="Restricted"')
			return
		i = web.input()
		content = i.content.decode('ascii', 'ignore')
		try:
			self.data[pagename] = content
		except:
			traceback.print_exc()
		print markdown(content)
	
	def PUT(self, pagename):
		self.POST(pagename)
	
	def DELETE(self, pagename):
		if not valid_auth():
			web.ctx.status = '401 Unauthorized'
			web.header('WWW-Authenticate', 'Basic realm=Restricted')
			return
		del self.data[pagename]

if __name__ == '__main__':
	fd = open(PID_FILE, 'w')
	fd.write(str(getpid()))
	fd.close()
	web.run(urls, globals(), web.reloader)
