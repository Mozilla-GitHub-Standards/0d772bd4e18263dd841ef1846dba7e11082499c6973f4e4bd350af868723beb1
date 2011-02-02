import functools
import tornado.web

class WebHandler(tornado.web.RequestHandler):
  def get_current_user(self):
    return self.get_secure_cookie("uid")

# From tornado's default - but always 403 rather than redirect to the login.
def authenticated(method):
    """Decorate methods with this to require that the user be logged in."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        if not self.current_user:
            raise tornado.web.HTTPError(403)
        return method(self, *args, **kwargs)
    return wrapper
