Overview
=========

Following on from discussions at the Mozilla December 2010 all-hands, I've been experimenting with what F1 would look like in a "browser mediated services" environment.  The intention was to experiment with using pure HTML to create browser-agnostic applications for things like access to your contacts and sharing services.

This experiment is not intended to be used as the basis for a production system - as many short-cuts as possible where taken while still demonstrating the key issues such a system would face.  In other words, it is quite hacky.

This experiment consists of the following parts:

* An 'account server' - a server which manages the concept of an 'account' and permissions granted to web-pages (or applications) for this account.  This server also hosts the consent UI for the other servers (ie, consent to access your contacts or to share an item).  This is a tornado based server and is directly in the git source tree.

* A 'contacts server' - this is the contacts server Mike put together in December, but with all account information and consent UI ripped out (using the above account server instead.)  This is a 'git submodule' in the source tree, referencing mhammond's fork of Mike's server on github.

* A 'share server' - this is the F1 server, also modified to make use of the account server.  This is a 'git submodule' in the source tree, referencing a feature branch in the F1 github repo.

* A stub for an 'application' which uses these services.  The stub is a modified F1 UI, but conceptually is not related to F1 at all (ie, this page is not implicitly trusted by the system)

The main things this experiment investigates is:

* How feasible it is to have different servers, each with their own database, to share the concept of an account ID provided by the account server without requiring the user log in to each individual server.

* How reasonable it is for the account server to manage the consent UI for the services provided by the contacts and the share server, and make xhr requests into the contacts and share server.

While the short story is "it all works", there are some significant issues which would needed to be addressed before considering such a system.  The rest of this document details some of those issues, with basic instructions to get it working at the end.

How it operates
---------------

The account-server supports only openid based logins, but it could support any login system.

The contact-server and F1 are both assumed to be on the same domain as the account server, so the account server cookies are also sent to these servers.  The account-server has an API end-point which takes a cookie and returns the account ID.  This end-point is designed to be used only by these other servers - ie, is not to be publically accessable.  This avoids the servers needing to share the server 'secret'.  The other servers cache this value in their own session cookie.

The contacts and share servers use the above mechanisms to determine if a user is logged in with the account server, and if not, redirect the user to the login UI provided by the account server.  This redirect also provides the 'return_to' address, so the user is redirect back to the contacts or share server after login.

The account server hosts the "glue" code used by the applications.  Applications must load this into an iframe, and helpers are provided so the app can communicate with the iframe using jschannels.  In each call made to this glue code, the application can specify the complete set of permissions needed by the app, so the glue code can request consent for all these permissions in one hit.  The account server stores the result of the consent UI, and if approved, initiates the XHR request to the relevant server and returns the result to the application.

The contacts and share servers have had some end-points changed to allow XHR requests to originate from the account-server.

Issues
======

Some of the issues found in this implementation include:

UX Issues:
-----------

* F1 has been designed to explicitly avoid a "login" step purely for a better UX.  This isn't really possible in this account-server-centric model.

* We add the concept of 'permissions' - but now we have 2 things to expose to the user from the POV of revoking them:
    * The permissions we expose and store (eg, "access contacts")
    * The OAuth tokens we have used to implement our permissions (eg, an OAuth token to Google, another to twitter, facebook etc for accessing contacts stored there).

ie, while we must offer a UI for managing our concept of "permissions", we also need to offer a UI to see which OAuth tokens we hold and a way of revoking them.  This subtlety may well be lost on many users.

* Need reasonable UX for permissions without overwhelming the user.  Eg, checkboxes to allow some permissions but not all, "remember this" options (eg, forever, a fixed duration, this "session" etc)

* OpenID/OAuth artificial separations: Currently the account server does the open ID, and the contacts server does the OAuth.  We desire a way to do both at the same time (eg, if using google for both openid and contacts), but still work when this is not possible (eg, a mozilla-based login, or using different providers for login versus contacts/sharing)

* UI flow for new accounts: F1 says "signin" and doing so automatically creates a new account if necessary.  But a new account really wants additional configuration (eg, configure your contacts sources, etc).

* Consent UI possibly needs to grown functionality to allow the user to connect to external services - eg, if a call is made to fetch contacts but the user has no contact sources configured, we probably want to guide them through adding these sources rather than just returning zero contacts.

Architectural type stuff that needs discussion, thought...
-----------------------------------------------------------

* Apps probably want a manifest to declare the permissions used by the app, so consent can optionally be given at install time.

* OAuth considerations: Our servers will need to ask for fairly broad OAuth permissions from services such as facebook, twitter and your contacts store, even if the user has not (yet) consented to allowing applications access to these features.  The obvious alternative (doing the OAuth as they consent) will provide UX issues (the user will need to perform multiple OAuths per service instead of one) and technical issues (a single OAuth "application" generally can't have variable permissions which are incrementally activated as needed). Other side of the same coin: if a user has revoked permissions such that no app has permission to read contacts, should we continue to store OAuth tokens which relate to contacts?

* Need some basic registry of "permission id" and "localized permission text" - the ID is something used by the apps (eg, 'contacts.fetch') where the text is for the user (eg, "access to your contacts")

* Integer or otherwise "predictable" user-ids may be a problem given the disparate databases which use it.  Eg, consider an acct server generating integer IDs stored by F1.  If the acct server fails, is restored from backup and the user-id sequence is reset, F1 will associate with an incorrect user.  UUIDs?

* User IDs and deleted accounts: with disparate databases, how would things like F1 or the contacts server know about account deletions?

Stuff that sucks in the imnplementation - but is "easily" fixed
----------------------------------------------------------------

* The jchannel stuff doesn't work correctly - pressing reload causes the call to fetch contacts to silently fail (the debugger shows the iframe-hosted code isn't executed second time around.)  More of a problem with FF4 than 3.x, but probably easy to solve.

* F1 accounts/get call now returns null if not logged in (as opposed to returning [], which means logged-in but no accounts configured), but not all the F1 front-end code seems happy with that.  Similarly, occasionally a user-id of 'None' (a string) is seen instead of the user being logged out.

* Cross-domain XHR support hacked in for the one end-point used by the example - this is just me being "lazy" in the implementation.

Stuff not even considered
-------------------------

* OAuth token storage.  Currently held by the 'contacts' server *and* F1 (although they each store tokens for different purposes).  Where these tokens are ultimately stored isn't that relevant, so long as each component has access to them as necessary (although see above re UX issues and not burdening the user with too many auth requests)

Getting it running
==================

This is just an overview of the steps.  All servers are implemented using Python - you probably want to use a virtualenv or similar and probably need to manually install some dependencies.

* Prepare the source tree
    * Clone this repo
    * In the root of the checked-out tree, execute 'git submodule init'
    * In this same directory, execute 'git submodule update'

* Start the account server:
    * In a new shell, change into the account-server/src/ directory
    * set CONFIG_SQLALCHEMY=sqlite:///accounts.db
    * execute 'python webserver.py' - the account server should now be running on port 8301

* Start the contacts server:
    * In a new shell, change into the contact-server/src/ directory
    * set CONFIG_SQLALCHEMY=sqlite:///contacts..db
    * execute 'python webserver.py' - the contacts server should now be running on port 8300

* Start the F1 share server:
    * In a new shell, change into the f1 directory.
    * Execute 'python setup.py develop'
    * Execute 'paster serve development.ini' - the server should start on port 8000.
    

* Load the application stub
    * In your browser, open http://localhost:8000/share
    * F1 should notice you are not logged in - click the 'login' link.
    * Login using the google openID button.
    * Reload the page - you should be prompted for consent to access your contacts and share links.
    * You will probably get no contacts returned as your account will not be tied to any contacts sources - visit http://localhost:8300 to hook the contact server up with google.

Profit
====

??