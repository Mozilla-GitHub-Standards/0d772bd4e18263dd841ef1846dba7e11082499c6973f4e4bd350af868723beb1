#!/usr/bin/env python
#
# Google openid logon
#
# The webserver module is responsible for incoming and outgoing HTTP requests.
#

import tornado.httpserver
import tornado.auth
import tornado.ioloop
import tornado.web
import os
import re
import time
import calendar
import base64
import traceback
import logging
import urllib
import cStringIO
import json
import cgi
import json
from urlparse import urlparse

import model  # replace this with a dbserver

from webhandler import WebHandler, authenticated

# The OpenID+OAuth hybrid stuff doesn't work for us because (AFAICT) we're not
# world-routable yet.  So this is just doing authentication and then we hand
# off to the authorizer.
class GoogleConnectHandler(WebHandler, tornado.auth.GoogleMixin):
  @tornado.web.asynchronous
  def get(self):
    if self.get_argument("openid.mode", None):
      self.get_authenticated_user(self.async_callback(self.onConnect))
      return
    to = self.get_argument("to", None)
    if not to: to = "/"
    self.authenticate_redirect(callback_uri = "http://localhost:8300/connect/google?" + urllib.urlencode({"to":to}))
    
  # Got the response and unpacked OpenID parameters: handle it
  def onConnect(self, claimed_user_data):
    if not claimed_user_data:
      logging.warning("Could not log in Google user")
      self.write("unable to connect")
      self.finish()
      return
    
    # Now do we have a user for this Google identity?
    claimed_id = claimed_user_data["claimed_id"] if "claimed_id" in claimed_user_data else claimed_user_data["email"]
    if not claimed_id:
      self.write("unable to get an identifier")
      self.finish()
      return 

    try:
      session = model.Session()
      id_list = model.identity(session, claimed_id)
      if id_list and len(id_list) > 0:
        if len(id_list) > 1: # uh oh
          self.write("More than one user has claimed this identity.  That's confusing.  We should try to merge them somehow?")
          self.finish()
          return
          
        user = id_list[0].user
        logging.info("Google ID %s logged in succesfully to user account %s" % (claimed_id, user.id))
      else:
        # new user
        user = model.User()
        session.add(user)
        id = model.Identity(claimed_id, user, claimed_user_data["name"], model.OP_GOOGLE)
        id.verifiedNow()
        session.add(id)
        session.commit()

      self.set_secure_cookie("uid", str(user.id))
      
      # Where to?
    except Exception, e:
      logging.exception(e)
      session.rollback()
    
    #self.write("Success.  <a href='/fetch/google?" + urllib.urlencode(user["access_token"]) + "'>Load Google Contacts</a>")
    to = self.get_argument("to", None)
    if to:
      self.redirect(to)
    else:
      self.redirect("/")

# This works even on localhost - but it doesn't give us the user's ID.
# For now that's okay.  Once we're routable we should be able to do it
# all from GoogleConnect and get the access_token in the user object
# passed to onConnect. (i.e. we can chuck this handler)
class GoogleAuthorizeHandler(WebHandler, tornado.auth.OAuthMixin):
  _OAUTH_REQUEST_TOKEN_URL = "https://www.google.com/accounts/OAuthGetRequestToken"
  _OAUTH_ACCESS_TOKEN_URL = "https://www.google.com/accounts/OAuthGetAccessToken"
  _OAUTH_AUTHORIZE_URL = "https://www.google.com/accounts/OAuthAuthorizeToken"
  _OAUTH_NO_CALLBACKS = False

  @authenticated
  @tornado.web.asynchronous
  def get(self):
    uid = self.current_user

    if self.get_argument("oauth_token", None):
      self.get_authenticated_user(self.async_callback(self.onConnect))
      return
    self.authorize_redirect(callback_uri = "http://localhost:8300/authorize/google", extra_params = {
      'xoauth_displayname': "Mozilla Contacts",
      'scope': 'http://www.google.com/m8/feeds' # /contacts'
    })
    
  def _on_access_token(self, callback, response):
    if response.error:
        logging.warning("Could not fetch access token")
        callback(None)
        return

    uid = self.get_secure_cookie("uid")
    if not uid:
      logging.warn("No user session: redirecting to root")
      return self.redirect("/")
    
    # NOTE that we assume the user has only one GMail account here! 
    # This may be okay given that Google is moving towards single-login/multiple-account
    # but it could be a problem.
    access_token = tornado.auth._oauth_parse_response(response.body)
    session = model.Session()
    user = model.user(session, uid)
    id = user.identity(session, model.OP_GOOGLE)
    if id:
      id.accessToken = access_token["key"]
      id.accessSecret = access_token["secret"]
      session.add(id)
      session.commit()
    else: # strange, we have no id for this user
      self.write("Whoops - we don't have an authenticated Google login for you.  That's weird.")
      self.finish()
      return
    
    self.write("Success.  Saved access codes for Google.  <a href='/fetch/google'>Take a look</a>")
    self.finish()

  def onConnect(self, user):
    logging.error("Made it to onConnect")
    if not user:
      raise tornado.web.HTTPError(500, "Google authorization failed")
    # The access token is in access_token - save it
    logging.error(user)

  def _oauth_consumer_token(self):
      self.require_setting("google_consumer_key", "Google OAuth")
      self.require_setting("google_consumer_secret", "Google OAuth")
      return dict(
          key=self.settings["google_consumer_key"],
          secret=self.settings["google_consumer_secret"])
