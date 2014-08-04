# -*- coding: utf-8 -*-
# this file is released under public domain and you can use without limitations

from gluon.debug import dbg
import re

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
