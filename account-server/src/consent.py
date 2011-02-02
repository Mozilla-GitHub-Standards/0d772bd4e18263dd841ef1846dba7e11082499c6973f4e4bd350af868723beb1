# A simple interface to fetching and saving user consent for various
# operations
import urllib2

import tornado.web

from sqlalchemy import and_
from sqlalchemy.orm.exc import NoResultFound

import model
from webhandler import WebHandler, authenticated

class ConsentHandler(WebHandler):
    @authenticated
    def get(self):
        assert self.current_user
        origin = self.get_argument("origin", None)
        session = model.Session()
        actions_param = self.get_argument("actions", None)
        where = [model.UserConsent.user_id==self.current_user]
        if origin is not None:
            where.append(model.UserConsent.origin==origin)
        if actions_param is not None:
            actions = actions_param.split(",")
            where.append(model.UserConsent.operation.in_(actions))
        existing = session.query(model.UserConsent).filter(
                        and_(*where)).all()
        result = {}
        for e in existing:
            origin_result = result.setdefault(e.origin, {})
            origin_result[e.operation] = e.allowed
        # work out if we are trying to serve up the html ui or just the data.
        accepts = urllib2.parse_http_list(self.request.headers.get("Accept", ""))
        try:
            json_ndx = accepts.index("application/json")
        except ValueError:
            json_ndx = 10000
        try:
            html_ndx = accepts.index("text/html")
        except ValueError:
            html_ndx = 10000
        if html_ndx < json_ndx:
            self.render("consent.html", consent_items=result)
        else:
            self.write(result)

    @authenticated
    def post(self):
        assert self.current_user
        session = model.Session()
        origin = self.get_argument("origin")
        for operation, values in self.request.arguments.iteritems():
            if operation=="origin": # gross...
                continue
            print "HAVE OPERATION", operation, values
            if values[0]=='null':
                allowed = None
            else:
                allowed = values[0]=='true'
            try:
                existing = session.query(model.UserConsent).filter(
                    and_(model.UserConsent.user_id==self.current_user,
                         model.UserConsent.origin==origin,
                         model.UserConsent.operation==operation
                        )).one()
            except NoResultFound:
                if allowed is not None:
                    uc = model.UserConsent(self.current_user, origin, operation, allowed)
                    session.add(uc)
            else:
                if allowed is None:
                    # request to 'unremember'
                    session.delete(existing)
                else:
                    existing.allowed = allowed
        session.commit()
        self.write("<html><body>permissions updated</body></html>")

