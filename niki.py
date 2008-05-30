from google.appengine.ext.webapp import util
from google.appengine.api import users
from markdown import markdown
from urlparse import urljoin
from base64 import b64decode
import nstore
import web

REMOTE_DATASTORE = 'http://api.example.com/'

urls = (
	'/',					'WikiPage',
	'/(?P<pagename>.+)',	'WikiPage',
)

class WikiPage(object):
	def __init__(self):
		self.data = nstore.CacheDict(nstore.GoogleHTTPStore(REMOTE_DATASTORE), caches=[nstore.AppEngineStore()])
	
	def render(self, template, **kwargs):
		vars = {
			'STATIC_URL': 'http://static.neohippie.net',
			'SITE_NAME': 'nikiwiki',
			'SITE_MOTTO': 'anybody can edit, nobody can talk',
			'CONTENT_TYPE': 'text/html',
		}
		vars.update(kwargs)
		return self.data['templates/%s' % template] % vars

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
			
		print self.render('wiki.html', 
			title=pagename,
			raw_content=content,
			content=markdown(content))
	
	def POST(self, pagename):
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
		del self.data[pagename]

def main():
	app = web.wsgifunc(web.webpyfunc(urls, globals(), web.reloader))
	util.run_wsgi_app(app)

if __name__ == "__main__":
	main()
