"""\
AutomatedOpsView

An interface which wrangles adding and removing instances to OpsView
servers.
The server to notify is mapped uniquely from the AWS region, AWS
account, and the application name and phase.
Authentication credentials for the OpsView servers are kept in the
autoopsview_config.py file.

TODO:
Detect expired token and try to reacquire.
Read credentials from private file, ini or json or something.
Memoize object instantiation.
"""

import json
import datetime
import requests
import logging

from autoopsview_config import credentials

logger = logging.getLogger('web2py.app.parapet')
logger.setLevel(logging.DEBUG)


class OpsViewError(Exception):
    pass


class OpsViewAuthError(OpsViewError):
    """An error involving authentication to an OpsView server."""
    pass


class OpsViewAPIError(OpsViewError):
    """An error occurred in an OpsView API query, report back.
    Create with JSON-parsed reply."""
    def __init__(self, reply):
        self.reply = reply

    def __str__(self):
        if 'messages' in self.reply:
            return ','.join(self.reply['messages'])
        else:
            return repr(self.reply.get('message', 'unknown')) + ': ' + repr(self.reply.get('detail', 'no details'))


def authToken(restURL, username, password):
    """Get an authentication token for the OpsView REST API."""
    r = requests.post(restURL + '/login',
                      data=json.dumps({'username': username, 'password': password}),
                      headers = {'Content-Type': 'application/json', 'Accept': 'application/json'})
    token = r.json().get('token', None)
    if token is None:
        raise OpsViewAuthError('Could not get auth token!')
    logger.debug("new auth token '%s' for '%s'", token, restURL)
    return token


def reload(db, quiesceSeconds=600):
    """\
    Reload all region servers with pending changes, which have waited
    at least quiesceSeconds.
    FIXME: this needs to collapse on rest_url, to MAX of last_change, for determining quiescence.
    """
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(seconds=quiesceSeconds)
    rows = db((db.serverInfo.last_change != None) & (db.serverInfo.last_change < cutoff)).select(db.serverInfo.ALL)
    for row in rows:
        logger.debug("reload needed for '%s' last changed: %s", row.region, row.last_changed)
        if row.region not in credentials:
            raise OpsViewAuthError('No credentials for server!')

        token = authToken(row.rest_url, credentials[region]['username'], credentials[region]['password'])
        r = requests.post(row.rest_url + '/reload',
                          headers={'X-Opsview-Token': token,
                                   'X-Opsview-Username': credentials[region]['username'],
                                   'Content-Type': 'application/json',
                                   'Accept': 'application/json'})
        logger.debug("reload request: %s", r)
        reply = r.json()
        if r.status_code == 409:
            logger.info("reload already in progress for '%s'", row.region)
            # A reload was already in progress, so just act like our request worked.
            # This might be the wrong thing to do if a reload takes longer than the quiet time.
            pass
        elif r.status_code / 100 != 2:
            raise OpsViewAPIError(reply)

        if int(reply['server_status']) > 1:
            raise OpsViewAPIError(reply)

        db(db.serverInfo.region == row.region).update(last_change=None)
        logger.info("reloaded '%s'", row.region)


class AutomatedOpsView(object):
    defaultServerMap = {
        'serverInfo': {
            'rest_url': 'http://127.0.0.1/rest'
        },
        'monitorMap': {
            'hostgroup': '',
            'slave_name': None
        }
    }

    def __init__(self, db, region, account, application, stack, phase):
        self.db = db
        self.region = region
        self.account = account
        self.application = application
        self.stack = stack
        self.phase = phase

        if self.stack in ('None', ''):
            self.stack = None

        if region not in credentials:
            raise OpsViewAuthError('No credentials for server!')

        self.username = credentials[region]['username']
        self.password = credentials[region]['password']

        self.token = None
        self.authJSONHeaders = {
            'X-Opsview-Token': None,
            'X-Opsview-Username': self.username,
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        # join the monitorMap and accountInfo tables on account id
        # join the monitorMap and serverInfo tables on server id
        # get only the rows with matching account, region, and phase
        monQuery = self.db(self.db.monitorMap.accountInfo_id == self.db.accountInfo.id)\
                          (self.db.accountInfo.accountNumber == account)\
                          (self.db.monitorMap.serverInfo_id == self.db.serverInfo.id)\
                          (self.db.serverInfo.region == region)\
                          (self.db.monitorMap.phase == phase)
        serverMap = monQuery.select(self.db.monitorMap.ALL, self.db.serverInfo.ALL).first()
        # logger.debug("account:'%s' region:'%s' phase:'%s' -- serverMap: '%r'", account, region, phase, serverMap)
        if not serverMap:
            serverMap = self.defaultServerMap

        # if no row at all, default all
        # but also default any null fields
        self.restURL  =  serverMap['serverInfo'].get('rest_url', self.defaultServerMap['serverInfo']['rest_url'])
        self.hostGroup = serverMap['monitorMap'].get('hostgroup', self.defaultServerMap['monitorMap']['hostgroup'])
        self.slaveName = serverMap['monitorMap'].get('slave_name', self.defaultServerMap['monitorMap']['slave_name'])


    def opsviewname(self, instanceId):
        """\
        Return the name OpsView will know an instanceId as.
        """
        return '_'.join(filter(None, (self.application or 'infra', self.stack, self.phase, instanceId)))


    def opsviewname_old(self, instanceId):
        """\
        Return a name OpsView might have previously known an instanceId as.
        """
        return '_'.join(filter(None, (self.application or 'infra', instanceId)))


    def genMonReqAdd_(self, instanceId, monitorIP, mountPaths):
        """\
        Return a dict suitable for feeding to OpsView API to add a host to monitoring.
        TODO: generate this from configuration somewhere
        """
        req = {}
        req['name'] = self.opsviewname(instanceId)
        req['ip'] = monitorIP
        req['alias'] = instanceId

        req['hostgroup'] = {
            'name': self.hostGroup
        }

        template = 'Application - {0}'.format(self.application)
        if self.getOpsViewObjByName_('hosttemplate', template) is None:
            template = 'OS - Unix Base'

        req['hosttemplates'] = [
            { 'name': template },
        ]

        req['check_period'] = [
            { 'name': '24x7' }
        ]
        req['notification_options'] = 'u,d,r,f'
        req['notification_interval'] = 5
        req['icon'] = {
            'name': 'LOGO - Linux Penguin'
        }
        req['check_command'] = {
            'name': 'NRPE (on port 5666)'
        }
        req['monitored_by'] = {}
        if self.slaveName:
            req['monitored_by']['name'] = self.slaveName

        if mountPaths:
            req['hostattributes'] = []
            for path in mountPaths:
                req['hostattributes'].append({
                    'name': 'DISK',
                    'value': path
                })

        return req


    def wantReload_(self):
        """Make note that a reload will be needed."""
        now = datetime.datetime.utcnow()
        self.db(self.db.serverInfo.region == self.region).update(last_change=now)
        logger.debug("updated timestamp for '%s': %s", self.region, now)


    def refreshOpsViewAuthToken_(self):
        """Update the auth token for the OpsView REST API."""
        self.token = authToken(self.restURL, self.username, self.password)
        self.authJSONHeaders['X-Opsview-Token'] = self.token


    def addOpsViewHost_(self, instanceId, monitorIP, mountPaths):
        """\
        Add the instanceId to the OpsView server, return the OpsView id.
        """
        logger.debug("adding instance '%s' (%s)", instanceId, monitorIP)
        if self.token is None:
            self.refreshOpsViewAuthToken_()

        host_id = self.getOpsViewObjByName_('host', self.opsviewname(instanceId))
        if host_id is not None:
            logger.debug("instance '%s' already monitored".format(instanceId))
            return host_id

        r = requests.post(self.restURL + '/config/host',
                          data=json.dumps(self.genMonReqAdd_(instanceId, monitorIP, mountPaths.split(':'))),
                          headers=self.authJSONHeaders)
        logger.debug("add request: %s", r)
        reply = r.json()
        if r.status_code / 100 != 2:
            logger.debug("add request: %s", r.text)
            raise OpsViewAPIError(reply)

        self.wantReload_()
        logger.info("added '%s' (%s) as %s", instanceId, monitorIP, reply['object']['id'])
        return reply['object']['id']


    def putObj_(self, objType, objId, data):
        """\
        Send a PUT request to update a monitored object id.
        """
        logger.debug("updating '%s' '%s', data: '%s'", objType, objId, data)
        if self.token is None:
            self.refreshOpsViewAuthToken_()

        r = requests.put('{0}/config/{1}/{2}'.format(self.restURL, objType, objId),
                         data=json.dumps(data),
                         headers=self.authJSONHeaders)
        logger.debug("put request: %s", r)
        if (r.status_code / 100 != 2):
            logger.debug("add request: %s", r.text)
            raise OpsViewAPIError(r.json())

        self.wantReload_()
        logger.info("updated '%s' '%s'", objType, objId)
        return r.json()['object']['id']


    def getOpsViewDataByName_(self, objType, name):
        """\
            Return the data for the OpsView entity which matches the provided name.
            Expects only one object to be found.
        """
        if self.token is None:
            self.refreshOpsViewAuthToken_()

        filterDict = {'name': {'=': name}}

        r = requests.get(self.restURL + '/config/' + objType,
                         params={'json_filter': json.dumps(filterDict)},
                         headers=self.authJSONHeaders)
        logger.debug("get request: %s", r)
        if r.headers['Content-Type'].split(';',1)[0] == 'application/json':
            reply = r.json()
        else:
            reply = {'message': r.text}

        if r.status_code / 100 != 2:
            logger.debug("get request: %r", reply)
            raise OpsViewAPIError(reply)
        if int(reply['summary']['totalrows']) == 0:
            return None
        if int(reply['summary']['totalrows']) > 1:
            raise OpsViewError('multiple entries for {0} "{1}"'.format(objType, name))
        return reply['list'][0]


    def getOpsViewObjByName_(self, objType, name):
        """\
            Return the id of the OpsView entity matching name.
            Expects only one.
        """
        data = self.getOpsViewDataByName_(objType, name)
        return data['id'] if data else None


    def delOpsViewHost_(self, instanceId):
        """\
        Remove the instanceId from the OpsView server, return the OpsView id deleted.
        """
        logger.debug("removing instance '%s'", instanceId)
        if self.token is None:
            self.refreshOpsViewAuthToken_()

        host_id = self.getOpsViewObjByName_('host', self.opsviewname(instanceId))
        if host_id is None:
            # try old name.  can remove this once old hosts have drained from monitoring
            host_id = self.getOpsViewObjByName_('host', self.opsviewname_old(instanceId))
            if host_id is None:
                return None

        r = requests.delete(self.restURL + '/config/host/' + host_id,
                            headers=self.authJSONHeaders)
        logger.debug("delete request: %s", r)
        reply = r.json()
        if r.status_code / 100 != 2:
            logger.debug("delete request: %s", r.text)
            raise OpsViewAPIError(reply)

        if int(reply['success']) != 1:
            raise OpsViewAPIError(reply)

        self.wantReload_()
        logger.info("removed '%s' (%s)", instanceId, host_id)
        return host_id


    def addAttributes(self, instanceId, attributes, iconName):
        """\
        Append attributes to the monitored host.
        """
        monName = self.opsviewname(instanceId)
        hostData = self.getOpsViewDataByName_('host', monName)
        if hostData is None:
            logger.info("could not find '%s' to update", monName)
            return None

        if 'hostattributes' not in hostData:
            hostData['hostattributes'] = []

        hostData['hostattributes'].extend(attributes)

        if iconName:
            hostData['icon'] = {'name': iconName}

        self.putObj_('host', hostData['id'], hostData)
        self.wantReload_()
        logger.info("updated attributes for '%s'", monName)
        return hostData['id']


    def update(self, stateCode, instanceId, monitorIP, mountPaths):
        """\
        Adds or removes a host from monitoring, based on the runstate.
        """
        if not self.hostGroup:
            logger.info("not monitoring {0}: no hostgroup for {1}/{2}/{3}/{4}".format(instanceId, self.region, self.account, self.application, self.phase))
            return

        if stateCode == 16:
            self.addOpsViewHost_(instanceId, monitorIP, mountPaths)
        elif stateCode == 32:
            self.delOpsViewHost_(instanceId)
        else:
            logger.info("no monitoring change for {0} stateCode {1}".format(instanceId, stateCode))
            pass # unknown state!
