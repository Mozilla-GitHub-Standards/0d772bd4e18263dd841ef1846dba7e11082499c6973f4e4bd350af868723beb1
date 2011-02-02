#!/usr/bin/env python
#
# Account server front end
#
# The webserver module is responsible for incoming and outgoing HTTP requests.
#

import tornado.httpserver
import tornado.auth
import tornado.ioloop
import tornado.web
import os
import logging
import urllib
import cgi
import json

import model  # replace this with a dbserver

import google
import yahoo
import openidconsumer
import consent
from webhandler import WebHandler, authenticated

# pycurl and certificates are a real PITA on Windows and the python
# openid library doesn't offer a reasonable way of adding default
# options to the curl object it uses.
import sys, os

def monkeypatch_curl(cert_path):
    # Use the specified cert_path by default.
    import pycurl
    real_curl = pycurl.Curl
    def monkeyed_curl():
        c = real_curl()
        c.setopt(c.CAINFO, cert_path)
        return c
    pycurl.Curl = monkeyed_curl

if sys.platform.startswith("win"):
    try:
        # use the same env var as the curl cmdline tool.
        monkeypatch_curl(os.environ["CURL_CA_BUNDLE"])
    except KeyError: # no env var setup - leave things alone
        pass

del monkeypatch_curl


class MainHandler(WebHandler):
    def get(self):
        if self.current_user:
            self.render("index.html", errorMessage=None)
        else:
            self.render("index_no_user.html", errorMessage=None)

class UserHandler(WebHandler):
  @authenticated
  def get(self):
    self.write('{"uid":%s}' % self.current_user)


class UserIdentitiesHandler(WebHandler):
  @authenticated
  @tornado.web.asynchronous
  def get(self):
    uid = self.current_user
    assert uid
    http = tornado.httpclient.AsyncHTTPClient()
    request = tornado.httpclient.HTTPRequest("%s/user?uid=%s" % (webconfig.DB_URL, uid))
    http.fetch(request, callback=self.async_callback(self.onResponse))

  def onResponse(self, response):
    if response.code == 200:
      self.write(response.body)
      self.finish()
    else:
      raise tornado.web.HTTPError(500)


class UserServicesHandler(WebHandler):
  @authenticated
  def get(self):
    uid = self.current_user

    session = model.Session()
    user = model.user(session, uid)
    result = {"status":"ok"}
    services = result["services"] = []
    for anID in user.identities:
      services.append(anID.name())

    self.write(result)

class AddConnectHandler(WebHandler):
  @tornado.web.asynchronous
  def get(self):
    idService = self.request.arguments["svc"][0]
    

class FacebookIdentityHandler(tornado.web.RequestHandler, tornado.auth.FacebookMixin):
  @tornado.web.asynchronous
  def get(self):
    if self.get_argument("session", None):
        self.get_authenticated_user(self.async_callback(self._on_auth))
        return
    self.authenticate_redirect()

  def _on_auth(self, user):
    if not user:
        raise tornado.web.HTTPError(500, "Facebook auth failed")

    uid = self.get_secure_cookie("uid")
    if not uid:
      http = tornado.httpclient.AsyncHTTPClient()
      request = tornado.httpclient.HTTPRequest("%s/user" % (webconfig.DB_URL,), method="POST", body="")
      request.authResult = user
      http.fetch(request, callback=self.async_callback(self.onUserCreation))
    else:
      self.onAuthentication(uid, user)
    
  def onUserCreation(self, response):
    if response.code == 200:
      res = json.loads(response.body)
      if res["status"] == "ok":
        uid = res["uid"]
        self.set_secure_cookie("uid", str(uid))
        self.onAuthentication(uid, response.request.authResult)
      else:
        raise tornado.web.HTTPError(500)        
    else:
      raise tornado.web.HTTPError(500)
          
  def onAuthentication(self, uid, userData):
    logging.error(userData)
    # Will be like {'locale': u'en', 'first_name': u'Michael', 'last_name': u'Hanson', 'name': u'Michael Hanson', 'email': u'mhanson@gmail.com'}    
    # http://mozillalabs.com/contacts/?session=
    # {%22session_key%22%3A%222.yckrLpRNm1IifvZMkD9tcA__.3600.1285653600-562624793%22%2C%22uid%22%3A562
    # 624793%2C%22expires%22%3A1285653600%2C%22secret%22%3A%220iTnAkNTENnb8R6J1q1YJw__%22%2C%22sig%22%3A%223
    # 298b3435f8c78b63e165a09db160a68%22}&next=http%3A%2F%2Flocalhost%3A8300%2Fuser%2Faddid%2Ffacebook
    
    http = tornado.httpclient.AsyncHTTPClient()
    body = {"uid":uid, "identifier":userData["email"], "displayName":userData["name"], "opaqueID": userData["facebook_uid"], "sessionKey": userData["session_key"] }

    request = tornado.httpclient.HTTPRequest("%s/id" % (webconfig.DB_URL,), method="POST", body=urllib.urlencode(body))
    request.uid = uid
    http.fetch(request, callback=self.async_callback(self.onIdentitySaved))

  def onIdentitySaved(self, response):
    if response.code == 200:
      self.write('{"status":"ok", "uid": %s}' % response.request.uid)
      self.finish()
    else:
      raise tornado.web.HTTPError(500)


class LogoutHandler(tornado.web.RequestHandler):
    def get(self):
        self.clear_cookie('uid')
        return_to = self.get_argument("return_to", "/")
        self.redirect(return_to)


# The 'back-channel' - only come from trusted sites.
class BackChannelUIDHandler(tornado.web.RequestHandler):
    def get(self):
        value = self.get_argument('uid')
        uid = self.get_secure_cookie('uid', value=value)
        self.write({"uid": uid})


##################################################################
# Main Application Setup
##################################################################

settings = {
    "static_path": os.path.join(os.path.dirname(__file__), "static"),
    "cookie_secret": "B44CCD51-E21D-4D39-AFB7-03E4ED220733",
    "debug":True,
    
    "facebook_api_key":"873bb1ddcc201222004c053a25d07d12",
    "facebook_secret":"5a931183e640fa50ca93b0ab556eb949",

    "yahoo_consumer_key": "dj0yJmk9Qm9TNnJlY3FaVDNVJmQ9WVdrOU9YRkhNWGxMTjJzbWNHbzlPVFF6TURRNE5EWTEmcz1jb25zdW1lcnNlY3JldCZ4PTNi",
    "yahoo_consumer_secret": "b50f90fcc9b237da8272c8156cf5c4e202c5b5e4",

    "google_consumer_key":"anonymous",
    "google_consumer_secret":"anonymous"
#    "xsrf_cookies": True,
}

application = tornado.web.Application([
    (r"/user", UserHandler),
    (r"/user/ids", UserIdentitiesHandler),
#    (r"/user/addid", AddIdentityHandler),

    (r"/user/services", UserServicesHandler),

    (r"/consent", consent.ConsentHandler),

    (r"/login/(.*)", openidconsumer.OIDLoginHandler),
    (r"/logout", LogoutHandler),
#    (r"/connect/google", google.GoogleConnectHandler),
#    (r"/authorize/google", google.GoogleAuthorizeHandler),

#    (r"/connect/yahoo", yahoo.YahooConnectHandler),
#    (r"/authorize/yahoo", yahoo.YahooAuthorizeHandler),

#    (r"/connect/facebook", FacebookConnectHandler),
#    (r"/connect/yahoo", YahooConnectHandler),
#    (r"/connect/twitter", TwitterConnectHandler),
#    (r"/connect/flickr", FlickrConnectHandler),
    
    (r"/", MainHandler),
 
    (r"/backchannel/uid", BackChannelUIDHandler),
    ], **settings)

def run():
    http_server = tornado.httpserver.HTTPServer(application)
    http_server.listen(8301)
    tornado.ioloop.IOLoop.instance().start()

import logging
import sys
if __name__ == '__main__':
    if '-test' in sys.argv:
        import doctest
        doctest.testmod()
    else:
        logging.basicConfig(level = logging.DEBUG)
        run()
