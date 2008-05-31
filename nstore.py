from base64 import b64encode, b64decode
from threading import Thread
from random import choice
from time import strftime
import os, os.path
import cPickle
import zlib

from wsgiref.simple_server import make_server
from httplib import HTTPConnection
from cgi import parse_qs
import urllib, urlparse

class DictMixin(object):
	def keys(self): pass
	def __getitem__(self, key): pass
	def __setitem__(self, key, value): pass
	def __delitem__(self, key): pass

class UserDict(object):
	def __init__(self, data):
		self.data = data
	def __getitem__(self, key):
		return self.data[key]
	def __setitem__(self, key, value):
		self.data[key] = value
	def __delitem__(self, key):
		del self.data[key]
	def keys(self):
		return self.data.keys()

class FileStore(DictMixin):
	def __init__(self, path):
		self.path = path
	
	def keys(self):
		for dirpath, dirnames, filenames in os.walk(self.path):
			for name in filenames:
				yield os.path.join(dirpath.split(self.path, 1)[1], name)
	
	def get_path(self, key):
		path = os.path.normpath(os.path.join(self.path, key))
		if not path.startswith(self.path):
			raise KeyError(key)
		else:
			return path

	def __getitem__(self, key):
		path = self.get_path(key)
		if not os.path.exists(path):
			raise KeyError(key)
		if os.path.isdir(path):
			raise KeyError(key)
		return open(path, 'r').read()
	
	def __setitem__(self, key, value):
		path = self.get_path(key)
		if os.path.isdir(path):
			raise KeyError(key)
		spath = '/'.join(path.split('/')[:-1])
		if not os.path.exists(spath):
			os.makedirs(spath)
		fd = open(path, 'w')
		fd.write(value)
		fd.close()
	
	def __delitem__(self, key):
		path = self.get_path(key)
		os.remove(path)
		basepath = '/'.join(path.split('/')[:-1])
		if len(os.listdir(basepath)) == 0:
			os.rmdir(basepath)

class MemoryStore(DictMixin):
	def __init__(self):
		self.data = {}
	def __getitem__(self, key):
		return self.data[key]
	def __setitem__(self, key, value):
		self.data[key] = value
	def __delitem__(self, key):
		del self.data[key]
	def keys(self):
		return self.data.keys()

class HTTPStore(DictMixin):
	def __init__(self, uri):
		self.uri = uri
	
	def __getitem__(self, key):
		target = urlparse.urlparse(self.uri)
		if target.netloc.find(':') != -1:
			server, port = target.netloc.split(':', 1)
		else:
			server = target.netloc
			port = 80
		conn = HTTPConnection(server, int(port))
		conn.request('GET', '/%s' % urllib.quote(key))
		response = conn.getresponse()
		if response.status == 404:
			raise KeyError(key)
		if response.status != 200:
			raise IOError(response.status)
		chunk = True
		data = ''
		while chunk != '':
			chunk = response.read()
			data += chunk
		return data
	
	def __setitem__(self, key, value):
		target = urlparse.urljoin(self.uri, urllib.quote(key))
		response = urllib.urlopen(target, urllib.urlencode({'value': value}))
		result = response.read()
	
	def __delitem__(self, key):
		target = urlparse.urlparse(self.uri)
		if target.netloc.find(':') != -1:
			server, port = target.netloc.split(':', 1)
		else:
			server = target.netloc
			port = 80
		conn = HTTPConnection(server, int(port))
		conn.request('DELETE', '/%s' % urllib.quote(key))
		response = conn.getresponse()
		if response.status == 404:
			raise KeyError(key)
		if response.status != 200:
			raise IOError('%s %s' % (response.status, response.reason))
	
	def keys(self):
		return self.__getitem__('').split('\n')

try:
	import google.appengine.api.urlfetch
	from google.appengine.ext import db
	class GoogleHTTPStore(DictMixin):
		def __init__(self, url):
			self.url = url
		def __getitem__(self, key):
			response = google.appengine.api.urlfetch.fetch(self.url + key, method=google.appengine.api.urlfetch.GET)
			if response.status_code == 200:
				return response.content
			else:
				raise KeyError(key, response.content)
		def __setitem__(self, key, value):
			response = google.appengine.api.urlfetch.fetch(self.url + key, method=google.appengine.api.urlfetch.POST, payload=value)
			if response.status_code != 200:
				raise IOError('%s %s' % (response.status_code, response.content))
		
		def __delitem__(self, key):
			response = google.appengine.api.urlfetch.fetch(self.url + key, method=google.appengine.api.urlfetch.DELETE)
			if response.status_code != 200:
				raise KeyError(key)
		
		def keys(self):
			return self.__getitem__('').split('\n')
	
	class AppEngineData(db.Model):
		name = db.StringProperty(required=True)
		value = db.TextProperty(required=True)
	class AppEngineStore(DictMixin):
		def __getitem__(self, key):
			result = db.GqlQuery('SELECT * FROM AppEngineData WHERE name = :1', key).fetch(1)
			if len(result) > 0:
				return result[0].value
			else:
				raise KeyError(key)
		def __setitem__(self, key, value):
			self.__delitem__(key)
			data = AppEngineData(name=key, value=value)
			data.put()
		def __delitem__(self, key):
			query = db.GqlQuery('SELECT * FROM AppEngineData WHERE name = :1', key)
			results = query.fetch(1000)
			for result in results:
				db.delete(result)
		def keys(self):
			for result in db.GqlQuery("SELECT * FROM AppEngineData").fetch(1000):
				yield repr(result.name)
except:
	pass

class PickleSerializer(UserDict):
	def __init__(self, data):
		self.data = data
	def __getitem__(self, key):
		return cPickle.loads(self.data[key])
	def __setitem__(self, key, value):
		self.data[key] = cPickle.dumps(value)
	def __delitem__(self, key):
		del self.data[key]

class B64KeyDict(UserDict):
	def __getitem__(self, key):
		return self.data[b64encode(key)]
	def __setitem__(self, key, value):
		self.data[b64encode(key)] = value
	def __delitem__(self, key):
		del self.data[b64encode(key)]
	def keys(self):
		return [b64decode(x) for x in self.data.keys()]

class LoggingDict(UserDict):
	def __init__(self, data, logfd=None, date_format='%m/%d/%Y %H:%M:%S %Z'):
		self.data = data
		self.fd = logfd
		self.date_format = date_format
		
	def __getitem__(self, key):
		self.fd.write('%s GET %s\n' % (strftime(self.date_format), key))
		return self.data[key]
	
	def __setitem__(self, key, value):
		self.fd.write('%s SET %s\n' % (strftime(self.date_format), key))
		self.data[key] = value
	
	def __delitem__(self, key):
		self.fd.write('%s DEL %s\n' % (strftime(self.date_format), key))
		del self.data[key]

class CacheDict(UserDict):
	def __init__(self, data, caches=[], sync_write=False):
		self.data = data
		self.caches = caches 
		self.sync_write = sync_write
	
	def __setitem__(self, key, value):
		self.data[key] = value
		threads = []
		for cache in self.caches:
			t = Thread(target=cache.__setitem__, args=(key, value))
			threads.append(t)
			t.start()

		if self.sync_write:
			for t in threads:
				t.join()
	
	def __getitem__(self, key):
		try:
			cache = choice(self.caches)
			return cache[key]
		except KeyError:
			value = self.data[key]
			cache[key] = value
			return value
	
	def __delitem__(self, key):
		del self.data[key]
		threads = []
		for cache in self.caches:
			t = Thread(target=cache.__delitem__, args=(key))
			threads.append(t)
			t.start()

		if self.sync_write:
			for t in threads:
				t.join()
	
	def keys(self):
		return self.data.keys()

class ZipDict(UserDict):
	def __getitem__(self, key):
		return zlib.decompress(self.data[key])
	def __setitem__(self, key, value):
		self.data[key] = zlib.compress(value)

class HTTPDict(UserDict):
	def __init__(self, data, port=9608):
		self.data = data
		self.server = make_server('', port, self.wsgiapp)
		t = Thread(target=self.server.serve_forever)
		t.setDaemon(True)
		t.start()
	
	def wsgiapp(self, environ, start_response):
		key = urllib.unquote(environ['PATH_INFO']).lstrip('/')
		if environ['REQUEST_METHOD'] == 'GET':
			try:
				if key == '':
					response = [x + '\n' for x in self.data.keys()]
					response[-1] = response[-1].rstrip('\n')
				else:
		 			response = [self.data[key]]
			except KeyError:
				start_response('404 Not Found', [('Content-type', 'text/plain')])
				return ['']
			start_response('200 OK', [('Content-type', 'application/octet-stream')])
			return response

		if environ['REQUEST_METHOD'] == 'POST':
			query = environ['wsgi.input'].read(int(environ['CONTENT_LENGTH']))
			query = parse_qs(query)
			if 'value' in query:
				value = query['value'][0]
				self.data[key] = value
				start_response('200 OK', [('Content-type', 'text/plain')])
				return [str(len(value))]
			else:
				start_response('400 Bad Request', [('Content-type', 'text/plain')])
				return ['']
		if environ['REQUEST_METHOD'] == 'DELETE':
			del self.data[key]
			start_response('200 OK', [('Content-type', 'text/plain')])
			return ['']
