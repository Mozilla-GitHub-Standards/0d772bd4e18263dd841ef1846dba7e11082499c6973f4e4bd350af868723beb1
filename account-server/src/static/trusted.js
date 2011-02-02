/* ***** BEGIN LICENSE BLOCK *****
 * Version: MPL 1.1/GPL 2.0/LGPL 2.1
 *
 * The contents of this file are subject to the Mozilla Public License Version
 * 1.1 (the "License"); you may not use this file except in compliance with
 * the License. You may obtain a copy of the License at
 * http://www.mozilla.org/MPL/
 *
 * Software distributed under the License is distributed on an "AS IS" basis,
 * WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
 * for the specific language governing rights and limitations under the
 * License.
 *
 * The Original Code is contact-server.
 *
 * Contributor(s):
 *   Michael Hanson <mhanson@mozilla.com>
 *
 * Alternatively, the contents of this file may be used under the terms of
 * either the GNU General Public License Version 2 or later (the "GPL"), or
 * the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
 * in which case the provisions of the GPL or the LGPL are applicable instead
 * of those above. If you wish to allow use of your version of this file only
 * under the terms of either the GPL or the LGPL, and not to allow others to
 * use your version of this file under the terms of the MPL, indicate your
 * decision by deleting the provisions above and replace them with the notice
 * and other provisions required by the GPL or the LGPL. If you do not delete
 * the provisions above, a recipient may use your version of this file under
 * the terms of any one of the MPL, the GPL or the LGPL.
 *
 * ***** END LICENSE BLOCK ***** */

;ClientBridge = (function() {
    var chan = Channel.build({
        window: window.parent,
        origin: "*",
        scope: "contacts"
    });

    // Reference shortcut so minifier can save on characters
    var win = window;

    // We're the top window, don't do anything
    if(win.top == win) return;

    // unsupported browser
    if(!win.postMessage || !win.localStorage || !win.JSON) return;

    // storage engines
    var permissionStorage = TypedStorage("perm").open();

    handleFetch = function(allowed, t) {
        if (allowed) {
            permissionStorage.put(t.origin, true);
            // Use .ajax so we can hook withCredentials in...
            $.ajax({
              url: "http://localhost:8300/fetch/google",
              dataType: 'json',
              beforeSend: function(xhr){
                xhr.withCredentials = true;
              },
              success: function(data) {
                if (data.status == "ok")
                {
                  t.complete(data.contacts);
                }
              }
            });
        } else {
            t.error("denied", "User denied installation request");
        }
    };

    chan.bind("get", function(t, args) {
        if (console)
            console.log("Contacts call: get");
        // indicate that response will occur asynchronously, later.
        t.delayReturn(true);

        // Check permissions sane - thisPermission is 'trusted' - it is
        // supplied with the implementation endpoint.  allPermissions is
        // supplied by the page - the idea is to prompt for consent for
        // *all* needed permissions once, so consent UI can be avoided for
        // future calls made which use additional permissions.
        if (!args['allPermissions']) {
            args['allPermissions'] = [args['thisPermission']];
        }
        var allPermissions = args['allPermissions'];
        var thisPermission = args['thisPermission'];

        if (allPermissions.indexOf(thisPermission)==-1) {
            throw "invalid allPermissions - doesn't include " + thisPermission;
        }
        // check saved permissions.  If we get a saved authority for
        // *this* permission we can do it without consent.  If we don't, we
        // prompt for consent of *all* permissions, then save.
        // ask the account server about saved permissions.
        var consentURL = "http://localhost:8301/consent"
        data={actions: allPermissions.join(","),
              origin: t.origin};
        $.getJSON(consentURL, data,
                  function(data) {
                    var originPerms = data[t.origin] || {}
                    if (originPerms[thisPermission]===undefined) {
                        // never previously asked (or not remembered)
                        var missing = [];
                        allPermissions.forEach(function (perm) {
                            if (originPerms[perm]===undefined) {
                                missing.push(perm);
                            }
                        });
                        // cause the UI to display a prompt to the user
                        consentUI(t.origin, missing, function (allowed, remember) {
                            if (remember) {
                                // convert back into the format expected by the POST handler.
                                data = {origin: t.origin};
                                missing.forEach(function(what) {
                                    data[what] = allowed;
                                });
                                $.post(consentURL, data, null);
                            }
                            handleFetch(allowed, t);
                        });
                    } else if (originPerms[thisPermission]===true) {
                        // previously authorized and remembered.
                        handleFetch(true, t);
                    } else { // presumably: originPerms[thisPermission]===false)...
                        // previously denied and remembered.
                        handleFetch(false, t);
                    }
                  });
    });

    function consentUI(origin, permissions, success) {
        displayConfirmPrompt(origin, permissions, success);
    }

    /**
       help with debugging issues
       We can eventually toggle this using a debug.myapps.org store
    **/
    function logError(message) {
        if(win.console && win.console.log) {
            win.console.log('App Repo error: ' + message);
        }
    }

    return {
        showDialog: function() { chan.notify({ method: "showme" }); },
        hideDialog: function() { chan.notify({ method: "hideme" }); }
    }
})();
