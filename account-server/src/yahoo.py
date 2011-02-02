#!/usr/bin/env python
#
# Contacts server front end
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


# The OpenID+OAuth hybrid stuff doesn't work for us because (AFAICT) we're not
# world-routable yet.  So this is just doing authentication and then we hand
class YahooConnectHandler(tornado.web.RequestHandler, tornado.auth.OpenIdMixin):
  _OPENID_ENDPOINT = "https://open.login.yahooapis.com/openid/op/auth"

  @tornado.web.asynchronous
  def get(self):
    if self.get_argument("openid.mode", None):
      self.get_authenticated_user(self.async_callback(self.onConnect))
      return
    to = self.get_argument("to", None)
    if not to: to = "/"
    self.authenticate_redirect(callback_uri = "http://localhost:8300/connect/yahoo?" + urllib.urlencode({"to":to}))
    
  # Got the response and unpacked OpenID parameters: handle it
  def onConnect(self, claimed_user_data):
    logging.info(claimed_user_data)
  
    if not claimed_user_data:
      logging.warning("Could not log in Yahoo user")
      self.write("unable to connect")
      self.finish()
      return
    
    # Now do we have a user for this Yahoo identity?
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
        logging.info("Yahoo ID %s logged in succesfully to user account %s" % (claimed_id, user.id))
      else:
        # new user
        user = model.User()
        session.add(user)
        id = model.Identity(claimed_id, user, claimed_user_data["name"], model.OP_YAHOO)
        id.verifiedNow()
        session.add(id)
        session.commit()

      self.set_secure_cookie("uid", str(user.id))
      
      # Where to?
    except Exception, e:
      logging.exception(e)
      session.rollback()
    
    to = self.get_argument("to", None)
    if to:
      self.redirect(to)
    else:
      self.redirect("/")

# This works even on localhost - but it doesn't give us the user's ID.
# For now that's okay.  Once we're routable we should be able to do it
# all from YahooConnect and get the access_token in the user object
# passed to onConnect. (i.e. we can chuck this handler)
class YahooAuthorizeHandler(tornado.web.RequestHandler, tornado.auth.OAuthMixin):
  _OAUTH_NO_CALLBACKS = False
  _OAUTH_VERSION = "1.0"
  _OAUTH_REQUEST_TOKEN_URL = "https://api.login.yahoo.com/oauth/v2/get_request_token"
  _OAUTH_AUTHORIZE_URL     = "https://api.login.yahoo.com/oauth/v2/request_auth"
  _OAUTH_ACCESS_TOKEN_URL  = "https://api.login.yahoo.com/oauth/v2/get_token"


  @tornado.web.asynchronous
  def get(self):
    uid = self.get_secure_cookie("uid")
    if not uid:
      logging.warn("No user session: redirecting to root")
      return self.redirect("/")
      
    if self.get_argument("oauth_token", None):
      self.get_authenticated_user(self.async_callback(self.onConnect))
      return

    to = self.get_argument("to", None)
    if not to: to = "/listview"

    self.authorize_redirect(callback_uri = "http://localhost:8300/authorize/yahoo?" + urllib.urlencode({"to":to}), extra_params = {
      'xoauth_displayname': "Mozilla Contacts"
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
    
    logging.info("Got OAuth callback: %s" % response)
    # NOTE that we assume the user has only one Yahoo account here! 
    access_token = tornado.auth._oauth_parse_response(response.body)
    logging.info(" parsed to: %s" % access_token)

    # What we get back is:
    #  {'xoauth_yahoo_guid': '54MJG4TXXXXXXMDIXXXXX5G5M', 
    #   'oauth_authorization_expires_in': '855808199', 'oauth_expires_in': '3600', 
    #   'oauth_session_handle': 'AHNm_UxwMcc-', 
    #   'secret': '2864f3d82f082cbbcf70b', 
    #   'key': 'A=EDiRDHTtsx3u5W.I9Vj<lots bigger>...'}

    session = model.Session()
    user = model.user(session, uid)
    id = user.identity(session, model.OP_YAHOO)
    if id:
      id.accessToken = access_token["key"]
      id.accessSecret = access_token["secret"]
      id.opaqueID = access_token["xoauth_yahoo_guid"]
      session.add(id)
      session.commit()
    else: # strange, we have no id for this user
      self.write("Whoops - we don't have an authenticated Yahoo login for you.  That's weird.")
      self.finish()
      return
    
    to = self.get_argument("to", None)
    if to:
      self.redirect(to)
    else:
      self.redirect("/")

  def onConnect(self, user):
    logging.error("Made it to onConnect")
    if not user:
      raise tornado.web.HTTPError(500, "Yahoo authorization failed")
    # The access token is in access_token - save it
    logging.error(user)

  def _oauth_consumer_token(self):
      self.require_setting("yahoo_consumer_key", "Yahoo OAuth")
      self.require_setting("yahoo_consumer_secret", "Yahoo OAuth")
      return dict(
          key=self.settings["yahoo_consumer_key"],
          secret=self.settings["yahoo_consumer_secret"])
