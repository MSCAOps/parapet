# -*- coding: utf-8 -*-
# this file is released under public domain and you can use without limitations

from gluon.debug import dbg
from gluon.scheduler import Scheduler
import re
import json
import logging
import datetime
import serverTask_config
import os

logger = logging.getLogger('web2py.app.parapet')
logger.setLevel(logging.DEBUG)

#########################################################################
## This is a sample controller
## - index is the default action of any application
## - user is required for authentication and authorization
## - download is for downloading files uploaded in the db (does streaming)
## - call exposes all registered services (none by default)
#########################################################################


def index():
    """
    example action using the internationalization operator T and flash
    rendered by views/default/index.html or views/generic.html

    if you need a simple wiki simply replace the two lines below with:
    return auth.wiki()
    """
    #response.flash = T("Welcome to web2py!")
    return dict(message=T('Ansible playbook server for provisioning automation'),content='Manage playbooks to be sent to nodes for local execution')
    #return dict(content='Define playbooks to be sent to nodes for local execution')

@auth.requires_login()
def manageAccountInfo():
    grid = SQLFORM.smartgrid(db.accountInfo,linked_tables=['appTask','hostInfo'])
    return dict(grid=grid)

@auth.requires_login()
def manageAppInfo():
    grid = SQLFORM.smartgrid(db.appInfo,linked_tables=['appTask'])
    return dict(grid=grid)

@auth.requires_login()
def managePbInfo():
    grid = SQLFORM.smartgrid(db.pbInfo,linked_tables=['appTask'])
    return dict(grid=grid)

@auth.requires_login()
def manageAppTask():
    grid = SQLFORM.smartgrid(db.appTask,linked_tables=['statusInfo','accountInfo','appInfo','pbInfo'])
    return dict(grid=grid)

@auth.requires_login()
def manageHostInfo():
    grid = SQLFORM.smartgrid(db.hostInfo,linked_tables=['statusInfo','accountInfo'],editable=False,deletable=False,create=False)
    return dict(grid=grid)

###
# serverTask
#
# Allows you to specify the parameters related to a scheduled server run task.
# This function will validate the inputs, run the host query for validation.
# If the query returns 0 hosts, then no task will be scheduled. Otherwise, the task
# will be scheduled using the parameters given.
@auth.requires_login()
def serverTask():

    grid = {}
    form = SQLFORM.factory(
            Field('accountId', length=25, label="AWS Account", requires=IS_IN_DB(db,db.accountInfo.id,'%(friendlyName)s')),
            Field('appId', length=25, label="Application", requires=IS_IN_DB(db,db.appInfo.name,'%(name)s')),
            Field('devPhase', length=25, label="Development Phase", comment="Blank for all phases"),
            Field('region', length=25, label="AWS Region", comment="Blank for all regions"),
            Field('kvCheck', "text", default={}, comment="Will automatically add a check to insure host is  running", requires=IS_JSON(), label="Host Filter Data"),
            Field('runAt', "datetime", requires=IS_DATETIME(), default=datetime.datetime.utcnow(), label="Run Task At",comment="Be sure to choose a time in UTC"),
            Field('pbPath', length=200, label="Playbook URL", requires=IS_URL(allowed_schemes=['http','https'])),
            Field('repeatCount', "int", default=1, label="Job Runs", comment="0 = Unlimited until stop time"),
            #Field('repeatPeriod', 'list:string', label="Repeat Period", default=60, requires=IS_IN_SET({60:'None',60*60:'Hourly',(60*60)*24:'Daily',((60*60)*24)*7:'Weekly'})),
            Field('repeatPeriod', 'list:string', label="Repeat Period", default=60, requires=IS_IN_SET([(60,'None'),(60*60,'Hourly'),((60*60)*24,'Daily'),(((60*60)*24)*7,'Weekly')])),
            Field('stopAt', "datetime", requires=IS_DATETIME(), default=datetime.datetime.utcnow()+datetime.timedelta(days=30), label="Stop Running At",comment="Be sure to choose a time in UTC"),
            )
    if form.process().accepted:
        grid=form.vars
        grid['validHosts'] = {}
        form=None

        accountId = request.vars.accountId
        if int(accountId) == 1:
            accountQuery = db.hostInfo.accountNumber > 1
        else:
            accountQuery = db.hostInfo.accountNumber == accountId

        appId = request.vars.appId
        if appId == "All Applications":
            appQuery = db.hostInfo.app.like('%')
        else:
            appQuery = db.hostInfo.app == appId

        if len(request.vars.devPhase) > 1:
            devQuery = db.hostInfo.devPhase == request.vars.devPhase
        else:
            devQuery = db.hostInfo.devPhase.like('%')

        if len(request.vars.region) > 1:
            regionQuery = db.hostInfo.region == request.vars.region
        else:
            regionQuery = db.hostInfo.region.like('%')

        hostFilter = json.loads(request.vars.kvCheck)
        try:
            hostFilter['awsInfo']['ec2_state'] = 'running'
        except KeyError:
            hostFilter['awsInfo'] = {}
            hostFilter['awsInfo']['ec2_state'] = 'running'

        dbQuery = ((accountQuery)&(appQuery)&(devQuery)&(regionQuery))
        s = db(dbQuery)
        rows = s.select()
        for row in rows:
            hostNotes = json.loads(row['notes'])
            for key in hostFilter.keys():
                if hostNotes.has_key(key):
                    for check in hostFilter[key].keys():
                        try:
                            if hostFilter[key][check] == hostNotes[key][check]:
                                if grid['validHosts'].has_key(row['instance_id']) is False:
                                    try:
                                        grid['validHosts'][row['instance_id']] = serverTask_config.keyData[hostNotes['awsInfo']['ec2_key_name']]
                                    except KeyError:
                                        logger.debug("Unable to find a key named {0} using default".format(hostNotes['awsInfo']['ec2_key_name']))
                                        grid['validHosts'][row['instance_id']] = serverTask_config.keyData['default']
                                elif grid['validHosts'][row['instance_id']] is None:
                                    pass
    
                            else:
                                grid['validHosts'][row['instance_id']] = None
                        except KeyError as e:
                            grid['validHosts'][row['instance_id']] = None
        for key in grid['validHosts'].keys():
            if grid['validHosts'][key] is None:
                del grid['validHosts'][key]

        if len(grid['validHosts']) > 0:
            # schedule the task...
            # {"accountId":1,"appId":"All Applications","devPhase":"","region":"","kvCheck":"{}","pbPath":"http://s3.amazonaws.com/msca-filedepot/testPing.yml"}
            taskVals = {"accountId":accountId, "appId":appId, "devPhase":request.vars.devPhase, "region":request.vars.region, "kvCheck":json.dumps(hostFilter), "pbPath":request.vars.pbPath}
            logger.debug(json.dumps(taskVals))
            taskName = os.path.splitext(os.path.basename(taskVals['pbPath']))[0]

            # Determine start_time
            myRunAt = datetime.datetime.strptime(request.vars.runAt,"%Y-%m-%d %H:%M:%S")
            if myRunAt < datetime.datetime.utcnow():
                # If the scheduled start_time is < now... set it to now+30s
                taskStartTime = datetime.datetime.utcnow()+datetime.timedelta(seconds=30)
                taskImmediate=True
            else:
                taskStartTime = myRunAt
                taskImmediate=False

            # Deterimine stop_time
            myStopAt = datetime.datetime.strptime(request.vars.stopAt,"%Y-%m-%d %H:%M:%S")
            if int(request.vars.repeatCount > 0):
                taskStopTime = None
            else:
                taskStopTime = myStopAt

            taskPeriod = int(request.vars.repeatPeriod)
            taskRepeats = int(request.vars.repeatCount)

            taskData = scheduler.queue_task(serverTask,pvars=taskVals,timeout=(60*60)*3,start_time=taskStartTime,stop_time=taskStopTime,period=taskPeriod,repeats=taskRepeats,sync_output=5,task_name=taskName)

            if taskData.id is None:
                logger.error("Error scheduling task: {0}".format(taskData.errors))
            else:
                taskGrid = {"taskID":taskData.id, "taskUUID":taskData.uuid, "hosts":grid['validHosts'].keys()}
                logger.debug("Scheduled task id {0} UUID {1}".format(taskData.id,taskData.uuid))
                return dict(grid=taskGrid, form=form)
            #return dict(grid=taskVals, form=form)
        else:
            logger.warn("Inputs found no hosts, not scheduling task")

    return dict(grid=grid,form=form)

@auth.requires_login()
def manageStatusInfo():
    if 'view' in request.args:
        statusId =  int(request.args[2])
        dbQuery = ((db.statusInfo.id==statusId)&((db.hostInfo.id==db.statusInfo.hostInfo_id)&(db.stateInfo.id==db.statusInfo.jobState)&(db.appTask.id==db.statusInfo.appTask_id)))
        s = db(dbQuery)
        #dbg.set_trace()
        row = s.select().first()
        instanceId = {"AWS Instance":row.hostInfo.instance_id}
        taskName = {"Task":row.appTask.name}
        jobState = {"State":row.stateInfo.name}
        startDate = {"Start Date":str(row.statusInfo.jobStartTime)}
        data = {'Job Information':[taskName,instanceId,jobState,startDate]}
        processRecap = False
        jobOutput = ""
        if row.statusInfo.jobResults:
	        jobOut = row.statusInfo.jobResults.splitlines()
	        for line in jobOut:
	            if len(line) < 1:
	                continue
	            line.strip()
	            if processRecap:
	                regex="ok=(\d+)\s+changed=(\d+)\s+unreachable=(\d+)\s+failed=(\d+)"
	                p = re.compile(regex)
	                #dbg.set_trace()
	                m = p.search(line)
	                if m:
	                    line = "{0} <font color='green'>ok={1}</font> <font color='#E6B800'>changed={2}</font> unreachable={3} <font color='red'>failed={4}</font>".format(line[0:m.start()],m.groups()[0],m.groups()[1],m.groups()[2],m.groups()[3])
	                jobOutput = jobOutput+line+"\n"
	                continue
	
	            if row.statusInfo.jobState < 4:
	                if len(line) < 1 or line[0] == "<":
	                    continue
	
	            if row.statusInfo.jobState == 4:
	                if len(line) < 1 or line[0] == "<":
	                    line = "<font color='blue'>{0}</font>".format(line)
	
	            if line[0:2] == "ok":
	                line = "<font color='green'>{0}</font>".format(line)
	            elif line[0:7] == "changed":
	                line = "<font color='#E6B800'>{0}</font>".format(line)
	            elif line[0:6] == "failed":
	                line = "<font color='red'>{0}</font>".format(line)
	
	            elif "***********" in line:
	                line = "<b>{0}</b>".format(line)
	
	            if "RECAP" in line:
	                processRecap = True
	
	            jobOutput = jobOutput+line+"\n"

        #print TABLE(TR(TD(B('AWS Instance')),TD(row.hostInfo.instance_id)),TR(TD(B('Task')),TD(row.appTask.name)))
        #return dict(instanceId=instanceId,taskName=taskName,jobState=jobState,startDate=startDate,data=data)
        return dict(data=data,jobOutput=XML(jobOutput))
    else:
        displayLengths = {'statusInfo.hostInfo_id': 10, 'statusInfo.appTask_id': 35, 'statusInfo.jobState': 12, 'statusInfo.jobResults':25}
        grid = SQLFORM.grid(db.statusInfo,orderby=~db.statusInfo.jobStartTime|~db.statusInfo.id,editable=False,
                            deletable=False,create=False,maxtextlengths=displayLengths)
        return dict(grid=grid)

@auth.requires_login()
def serverTaskInfo():
    if 'view' in request.args:
        taskData = scheduler.task_status(int(request.args[2]),output=True)
        grid = taskData
        #grid = {'status':taskData.scheduler_run.status, 
        if taskData.scheduler_task.status == "COMPLETED" or taskData.scheduler_task.status == "EXPIRED":
            data = {"id":int(taskData.scheduler_run.id), "status":taskData.scheduler_run.status, "workerName":taskData.scheduler_run.worker_name, "startTime":taskData.scheduler_run.start_time.isoformat(), "stopTime":taskData.scheduler_run.stop_time.isoformat(),"runNumber":"{0} of {1}".format(int(taskData.scheduler_task.times_run),int(taskData.scheduler_task.repeats)),"runResult":taskData.scheduler_run.run_result}
        else:
            data = {"status":taskData.scheduler_task.status,"nextRunTime":taskData.scheduler_task.next_run_time.isoformat(), "taskName":taskData.scheduler_task.task_name,"uuid":taskData.scheduler_task.uuid}
            return dict(data=data,jobOutput="")
        #data = ["id",taskData.scheduler_run.id, "status",taskData.scheduler_run.status, "workerName",taskData.scheduler_run.worker_name, "startTime",taskData.scheduler_run.start_time.isoformat(), "stopTime",taskData.scheduler_run.stop_time.isoformat()]
        processRecap = False
        jobOutput = ""
        jobOut = taskData.scheduler_run.run_output.splitlines()
        for line in jobOut:
            if len(line) < 1:
                continue
            line.strip()
            if processRecap:
                regex="ok=(\d+)\s+changed=(\d+)\s+unreachable=(\d+)\s+failed=(\d+)"
                p = re.compile(regex)
                #dbg.set_trace()
                m = p.search(line)
                if m:
                    line = "{0} <font color='green'>ok={1}</font> <font color='#E6B800'>changed={2}</font> unreachable={3} <font color='red'>failed={4}</font>".format(line[0:m.start()],m.groups()[0],m.groups()[1],m.groups()[2],m.groups()[3])
                jobOutput = jobOutput+line+"\n"
                continue

            if len(line) < 1 or line[0] == "<":
                line = "<font class=\"_verboseData\" color='blue'>{0}</font>".format(line)
            #if taskData.scheduler_run.status == "COMPLETED":
            #    if len(line) < 1 or line[0] == "<":
            #        continue

            #else:
            #    if len(line) < 1 or line[0] == "<":
            #        line = "<font color='blue'>{0}</font>".format(line)

            if line[0:2] == "ok":
                line = "<font color='green'>{0}</font>".format(line)
            elif line[0:7] == "changed":
                line = "<font color='#E6B800'>{0}</font>".format(line)
            elif line[0:6] == "failed":
                line = "<font color='red'>{0}</font>".format(line)

            elif "***********" in line:
                line = "<b>{0}</b>".format(line)

            if "RECAP" in line:
                processRecap = True

            jobOutput = jobOutput+line+"\n"

        return dict(data=data,jobOutput=XML(jobOutput))
    else:
        fieldsToShow = [db.scheduler_task.id,db.scheduler_task.task_name,db.scheduler_task.status,db.scheduler_task.uuid,db.scheduler_task.times_run,db.scheduler_task.times_failed,db.scheduler_task.next_run_time]
        grid = SQLFORM.grid(db.scheduler_task,orderby=~db.scheduler_task.next_run_time,editable=False,
            fields=fieldsToShow,deletable=False,create=False)

    return dict(grid=grid)


@auth.requires_login()
def testInstructions():
    return dict()

@auth.requires_login()
def testInstructionsResults():
        appName = request.vars.appName
        accountNumber = request.vars.accountNumber
        hostId = request.vars.hostId
        jobTaskId = 0
        query = ((((db.appTask.appInfo_id==db.appInfo.id)&((db.appInfo.name==appName)|(db.appInfo.name=="All Applications")))&(db.appTask.accountInfo_id==db.accountInfo.id)&((db.accountInfo.accountNumber==accountNumber)|(db.accountInfo.accountNumber=="000000000000"))&(db.appTask.pbInfo_id==db.pbInfo.id)&((db.appTask.devPhase==db.hostInfo.devPhase)|(db.appTask.devPhase == None)))&(db.appTask.enabled==True)&(db.hostInfo.id==hostId))
        s = db(query)
        rows = s.select(orderby=db.appTask.taskOrder)
        taskList = []
        for row in rows:
            try:
                jobTaskId = jobTaskId+1
                task = {}
                task = {'taskId':jobTaskId, 'pbPath':row.pbInfo.pbPath,'pbAccessKey':row.pbInfo.accessKey,
                        'pbSecret':row.pbInfo.secret,'appTaskId':row.appTask.id,'appTaskname':row.appTask.name,
                        'hostInfoId':hostId,'pbExtraVars':row.appTask.extraVars}
                taskList.append(task)
            except Exception as e:
                errorString = "One of us is sad (hint: it's not me): {0}".format(e)
                return dict(message="getInstructions",status="task assignment failure", errorMsg=errorString)
        return dict(message="getInstructions", appname=appName, accountnumber=accountNumber, data=taskList)
        #return dict(rows=rows)
    
def user():
    """
    exposes:
    http://..../[app]/default/user/login
    http://..../[app]/default/user/logout
    http://..../[app]/default/user/register
    http://..../[app]/default/user/profile
    http://..../[app]/default/user/retrieve_password
    http://..../[app]/default/user/change_password
    http://..../[app]/default/user/manage_users (requires membership in
    use @auth.requires_login()
        @auth.requires_membership('group name')
        @auth.requires_permission('read','table name',record_id)
    to decorate functions that need access control
    """
    return dict(form=auth())

@cache.action()
def download():
    """
    allows downloading of uploaded files
    http://..../[app]/default/download/[filename]
    """
    return response.download(request, db)


def call():
    """
    exposes services. for example:
    http://..../[app]/default/call/jsonrpc
    decorate with @services.jsonrpc the functions to expose
    supports xml, json, xmlrpc, jsonrpc, amfrpc, rss, csv
    """
    return service()


@auth.requires_signature()
def data():
    """
    http://..../[app]/default/data/tables
    http://..../[app]/default/data/create/[table]
    http://..../[app]/default/data/read/[table]/[id]
    http://..../[app]/default/data/update/[table]/[id]
    http://..../[app]/default/data/delete/[table]/[id]
    http://..../[app]/default/data/select/[table]
    http://..../[app]/default/data/search/[table]
    but URLs must be signed, i.e. linked with
      A('table',_href=URL('data/tables',user_signature=True))
    or with the signed load operator
      LOAD('default','data.load',args='tables',ajax=True,user_signature=True)
    """
    return dict(form=crud())
