# coding: utf8
import json
import datetime
from gluon.debug import dbg

# Don't have a default page.
def index(): raise HTTP(404)
    
def register():
    try:
        # Fix up the inbound variable to make the json parser happy
        #awsInfo = request.vars.awsInfo.replace("'",'"').replace('u"','"').replace("True","true").replace("False","false").replace("None","null")
        hostInfo = json.loads(request.vars.hostData)
        #awsInfo = hostInfo['awsInfo']
        #userInfo = request.vars.userInfo.replace("'",'"')
        #userInfo = hostInfo['userInfo']
        # Convert from json to dict
        #myUserInfo = json.loads(userInfo)
        #myAwsInfo = json.loads(awsInfo)
        # Get the important fields
        instanceId = hostInfo['awsInfo']['ec2_id']
        myAcctId = db(db.accountInfo.accountNumber==hostInfo['awsInfo']['ec2_account_number']).select().first()
        awsRegion =  hostInfo['awsInfo']['ec2_region']
        application = hostInfo['userInfo']['CLOUD_APP']
        instanceType = hostInfo['awsInfo']['ec2_instance_type']
        devPhase = hostInfo['userInfo']['CLOUD_DEV_PHASE']
        #notesData = "AWS Info:\n{0}\nUser Info:\n{1}".format(json.dumps(myAwsInfo), json.dumps(myUserInfo))
        try:
            hostInfoId = db.hostInfo.update_or_insert(db.hostInfo.instance_id==instanceId,instance_id=instanceId,
                                                      accountNumber=myAcctId.id,region=awsRegion,app=application,
                                                      instanceType=instanceType,devPhase=devPhase,notes=json.dumps(hostInfo))
            if hostInfoId is None:
                hostInfo = db(db.hostInfo.instance_id==instanceId).select(db.hostInfo.id).first()
                hostInfoId = hostInfo.id
            return dict(accountNumber=myAcctId.id,awsRegion=awsRegion,application=application,
                        instanceType=instanceType,devPhase=devPhase,hostInfoId=hostInfoId)
        except Exception as e:
            # Something failed in the DB transaction, it would be nice to say what... but that's for later
            return dict(message="Database Error")
        
    except:
        # Something failed in the parsing of the passed in data, assume bad input
        return dict(message="requirements not met")

def getInstructions():
    try:
        appName = request.vars.appName
        accountNumber = request.vars.accountNumber
        hostId = request.vars.hostId
        #query = (((db.appTask.appInfo_id==db.appInfo.id)&(db.appInfo.name==appName))&(((db.appTask.accountInfo_id==db.accountInfo.id)|(db.appTask.accountInfo_id==None))&(db.accountInfo.accountNumber==accountNumber)))
        #query = (((db.appTask.appInfo_id==db.appInfo.id)&((db.appInfo.name==appName)|(db.appInfo.name=="All Applications")))&(db.appTask.accountInfo_id==db.accountInfo.id)&((db.accountInfo.accountNumber==accountNumber)|(db.accountInfo.accountNumber=="000000000000"))&(db.appTask.pbInfo_id==db.pbInfo.id))
        #query = ((((db.appTask.appInfo_id==db.appInfo.id)&((db.appInfo.name==appName)|(db.appInfo.name=="All Applications")))&(db.appTask.accountInfo_id==db.accountInfo.id)&((db.accountInfo.accountNumber==accountNumber)|(db.accountInfo.accountNumber=="000000000000"))&(db.appTask.pbInfo_id==db.pbInfo.id))&(db.appTask.enabled==True))
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

def updateStatusInfo():
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

def getHostFactFinder():
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
        return dict(message="updateStatusInfo",status="status assignment failure", errorMsg=errorString)
