# coding: utf8
import json
import datetime
from gluon.debug import dbg
import logging
import autoopsview

logger = logging.getLogger('web2py.app.parapet')
logger.setLevel(logging.DEBUG)

# Don't have a default page.
def index():
    session.forget()
    raise HTTP(404)

####
# register API
#
# Registers the host into the hostInfo table
#
# With the new parapet client and init.d script is also called when
# machine is shutting down.
#
# On boot:
#  hostInfo['awsInfo']['ec2_state'] == 'running'
#  hostInfo['awsInfo']['ec2_state_code'] == '16'
# On termination:
#  hostInfo['awsInfo']['ec2_state'] == 'shutting-down'
#  hostInfo['awsInfo']['ec2_state_code'] == '32'

def register():
    session.forget()
    try:
        # Fix up the inbound variable to make the json parser happy
        hostInfo = json.loads(request.vars.hostData)

        # Get the important fields
        instanceId = hostInfo['awsInfo']['ec2_id']
        myAcctId = db(db.accountInfo.accountNumber==hostInfo['awsInfo']['ec2_account_number']).select().first()
        awsRegion =  hostInfo['awsInfo']['ec2_region']
        application = hostInfo['userInfo']['CLOUD_APP']
        instanceType = hostInfo['awsInfo']['ec2_instance_type']
        devPhase = hostInfo['userInfo']['CLOUD_DEV_PHASE']
        #notesData = "AWS Info:\n{0}\nUser Info:\n{1}".format(json.dumps(myAwsInfo), json.dumps(myUserInfo))

        monitorIP = hostInfo['awsInfo']['ec2_private_ip_address']
        account = hostInfo['awsInfo']['ec2_account_number']
        stateCode = int(hostInfo['awsInfo']['ec2_state_code'])

        # ec2_mount_paths are a new feature
        # if an older client doesn't submit them, default to monitoring root disk
        mountPaths = hostInfo['awsInfo'].get('ec2_mount_paths', '/')

        # stack for now is only used in naming host in monitoring, so it's okay to be non-existent
        stack = hostInfo['userInfo'].get('CLOUD_STACK', None)
    except Exception as e:
        # Something failed in the parsing of the passed in data, assume bad input
        return dict(message="requirements not met:" + str(e))

    logger.debug("registering instance:'%s' account:'%s' region:'%s' app:'%s' type:'%s' phase:'%s' monIP:'%s' state:%d",
                 instanceId, account, awsRegion, application, instanceType, devPhase, monitorIP, stateCode)

    try:
        hostInfoId = db.hostInfo.update_or_insert(db.hostInfo.instance_id==instanceId,instance_id=instanceId,
                                                  accountNumber=myAcctId.id,region=awsRegion,app=application,
                                                  instanceType=instanceType,devPhase=devPhase,notes=json.dumps(hostInfo))
        if hostInfoId is None:
            hostInfo = db(db.hostInfo.instance_id==instanceId).select(db.hostInfo.id).first()
            hostInfoId = hostInfo.id
    except Exception as e:
        # Something failed in the DB transaction, it would be nice to say what... but that's for later
        logger.error("error inserting: " + str(e))
        return dict(message="Database Error")

    try:
        # notify opsview
        mon = autoopsview.AutomatedOpsView(db, awsRegion, account, application, stack, devPhase)
        mon.update(stateCode, instanceId, monitorIP, mountPaths)
    except autoopsview.OpsViewError as e:
        logger.error("error updating monitoring server: %s", str(e))
        # this is a concern, but should not be fatal

    logger.debug("registered acct_id:%d region:'%s', app:'%s' type:'%s', phase:'%s', hostInfoId:'%d' hostGroup:'%s' monSlave:'%s'",
                 myAcctId.id, awsRegion, application, instanceType, devPhase, hostInfoId, mon.hostGroup, mon.slaveName)
    return dict(accountNumber=myAcctId.id,
                awsRegion=awsRegion,
                application=application,
                instanceType=instanceType,
                devPhase=devPhase,
                hostInfoId=hostInfoId,
                hostGroup=mon.hostGroup,
                slaveName=mon.slaveName)


####
# getInstructions API
#
# Given the appName, accountNumber, and hostId from the client,
# return a JSON set that describes the tasks to be run.
def getInstructions():
    session.forget()
    try:
        appName = request.vars.appName
        accountNumber = request.vars.accountNumber
        hostId = request.vars.hostId
        # Query to determine the tasks assigned to this host.
        # We could stop requiring the accountNumber and applicationName from the client
        # but, it doesn't hurt anything to leave it.
        query = ((((db.appTask.appInfo_id==db.appInfo.id)&((db.appInfo.name==appName)|(db.appInfo.name=="All Applications")))&(db.appTask.accountInfo_id==db.accountInfo.id)&((db.accountInfo.accountNumber==accountNumber)|(db.accountInfo.accountNumber=="000000000000"))&(db.appTask.pbInfo_id==db.pbInfo.id)&((db.appTask.devPhase==db.hostInfo.devPhase)|((db.appTask.devPhase == None)|(db.appTask.devPhase == ""))))&(db.appTask.enabled==True)&(db.hostInfo.id==hostId))
        s = db(query)
        rows = s.select(orderby=db.appTask.taskOrder)
        taskList = []
        for row in rows:
            try:
                task = {}
                jobTaskId = db.statusInfo.insert(hostInfo_id=hostId, appTask_id=row.appTask.id, jobState=1, jobStartTime=datetime.datetime.now())
                task = {'taskId':jobTaskId, 'pbPath':row.pbInfo.pbPath,'pbAccessKey':row.pbInfo.accessKey,
                        'pbSecret':row.pbInfo.secret,'appTaskId':row.appTask.id,'appTaskname':row.appTask.name,
                        'hostInfoId':hostId,'pbExtraVars':row.appTask.extraVars,'pbEncVars':row.appTask.encVars}
                taskList.append(task)
            except Exception as e:
                errorString = "One of us is sad (hint: it's not me): {0}".format(e)
                return dict(message="getInstructions",status="task assignment failure", errorMsg=errorString)
        return dict(message="getInstructions", appname=appName, accountnumber=accountNumber,data=taskList)
    except:
        return dict(message="getInstructions")

####
# updateStatusInfo API
#
# Given the hostId, taskId, jobState and jobResults,
# update the task status in the statusInfo DB.
def updateStatusInfo():
    session.forget()
    try:
        hostInfo_id = request.vars.hostInfo_id
        appTask_id = request.vars.appTask_id
        jobState = request.vars.jobState
        jobResults = request.vars.jobResults
        db.statusInfo.insert(hostInfo_id=hostInfo_id, appTask_id=appTask_id, jobState=jobState, jobStartTime=datetime.datetime.now(), jobResults=jobResults)
        return dict(message="updateStatusInfo")
    except Exception as e:
        errorString = "One of us is sad (hint: it's not me): {0}".format(e)
        return dict(message="updateStatusInfo",status="status assignment failure", errorMsg=errorString)

####
# getHostFactFinder API
#
# Returns a python script that can be placed into /etc/ansible/facts.d
# to find a set of running hosts that make use of the aws filter types.
#
# Much more refinement required here... currently using just a static script
# in an S3 bucket.
def getHostFactFinder():
    session.forget()
    try:
        keyType = request.vars.keyType
        value = request.vars.value
        script='''
#!/usr/bin/python

import boto.ec2
import json
import os
import urllib2

esHosts = {}
hosts = ""
hostFilter={'KEYTYPE':'VALUE','instance-state-code':16}

try:
    regionURL = 'http://169.254.169.254/latest/meta-data/placement/availability-zone/'
    region = urllib2.urlopen(regionURL).read()[:-1]
except:
    region = os.environ.get("EC2_REGION")

conn = boto.ec2.connect_to_region(region)
reservations = conn.get_all_reservations(filters=hostFilter)
for reservation in reservations:
    for instance in reservation.instances:
        esHosts[instance.id] = instance.private_dns_name
        hosts = hosts + instance.private_dns_name+":9300,"

esHosts['string'] = hosts[:-1]
print json.dumps(esHosts)
'''.replace("KEYTYPE", keyType).replace("VALUE", value)

        return XML(script)
    except Exception as e:
        errorString = "One of us is sad (hint: it's not me): {0}".format(e)
        return dict(message="getHostFactFinder",status="script creation failure", errorMsg=errorString)

####
# healthCheck API
#
# Returns OK if parapet is happy
def healthCheck():
    session.forget()
    return dict(message="ok")


def addAttributes():
    """\
    Adds the list of attributes provided as JSON in monAttr to the
    monitored host provided in instanceId.
    """
    session.forget()

    if None in (request.vars.instanceId, request.vars.monAttr):
        return dict(message="addAttributes",
                    status="incomplete request",
                    errorMsg="missing value")
    try:
        instanceId = request.vars.instanceId
        monAttr = json.loads(request.vars.monAttr)
    except ValueError as e:
        return dict(message="addAttributes",
                    status="invalid request",
                    errnorMsg=str(e))

    iconName = request.vars.iconName

    logger.debug("addAttributes - instanceId: '%s' monAttr: '%s' iconName: '%s'", instanceId, monAttr, iconName)

    hostInfo = db(db.hostInfo.instance_id == instanceId).select(db.hostInfo.ALL).first()

    if hostInfo is None:
        errorMsg = "unknown instance '{0}'".format(instanceId)
        logger.error(errorMsg)
        raise HTTP(404, errorMsg)

    accountNumber = db(db.accountInfo.id == hostInfo.accountNumber).select(db.accountInfo.accountNumber).first()['accountNumber']

    # we need to pull the stack out of the notes field of the instance
    stack = json.loads(hostInfo.notes)['userInfo'].get('CLOUD_STACK', None)
    if stack == 'None':
        stack = None

    try:
        mon = autoopsview.AutomatedOpsView(db,
                                           hostInfo['region'],
                                           accountNumber,
                                           hostInfo['app'],
                                           stack,
                                           hostInfo['devPhase'])
        if mon.addAttributes(instanceId, monAttr, iconName) is None:
            raise HTTP(404, "could not update instance '{0}'".format(instanceId))
    except autoopsview.OpsViewError as e:
        logger.error("error updating monitoring server: %s", str(e))
        return dict(message="addAttributes",
                    status="update failed",
                    errorMsg=str(e))

    return dict(message='ok')
