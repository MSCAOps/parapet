# -*- coding: utf-8 -*-

########################################
# These are the tasks that the scheduler can manage
#######################################

import logging
import json
import urllib2
import os
import subprocess
from gluon.scheduler import Scheduler
from gluon import serializers
from gluon import utils
from gluon import fileutils
import serverTask_config

# Let us be able to log things.
logger = logging.getLogger('web2py.app.parapet')
logger.setLevel(logging.DEBUG)

def task_add(a,b):
    logger.debug("passed in {0} and {1}".format(a,b))
    return a+b


def serverTask(accountId, appId, devPhase, region, kvCheck, pbPath=None):
    # TODO: it would be nice to store these in a nice protected dict
    # and then write out the key to disk only for running the playbook...
    # We could put all of them in and identify a default key. Then if we
    # have an entry for the ssh key identified by the host, use that....
    sshKeyFilePath = "/home/ec2-user/.ssh/msca-devops.pem"

    # Directory to write out inventories and playbooks...
    runtimeDir = "/data/parapet/"

    grid = {}
    grid['validHosts'] = {}
    logger.debug("Task UUID: {0}".format(W2P_TASK.uuid))
    logger.debug("Account ID: {0}".format(accountId))
    if int(accountId) == 1:
        logger.debug("Setting account Query to all accounts")
        accountQuery = db.hostInfo.accountNumber > 1
    else:
        accountQuery = db.hostInfo.accountNumber == accountId

    logger.debug("Application: '{0}'".format(appId))
    if appId == "All Applications":
        appQuery = db.hostInfo.app.like('%')
    else:
        appQuery = db.hostInfo.app == appId

    logger.debug("DevPhase: {0}".format(devPhase))
    if len(devPhase) > 1:
        devQuery = db.hostInfo.devPhase == devPhase
    else:
        logger.debug("Setting devPhase to %")
        devQuery = db.hostInfo.devPhase.like('%')

    logger.debug("Region: {0}".format(region))
    if len(region) > 1:
        regionQuery = db.hostInfo.region == region
    else:
        logger.debug("Setting region to %")
        regionQuery = db.hostInfo.region.like('%')

    logger.debug("hostFilter: {0}".format(kvCheck))
    hostFilter = json.loads(kvCheck)
    try:
        hostFilter['awsInfo']['ec2_state'] = 'running'
    except KeyError:
        hostFilter['awsInfo'] = {}
        hostFilter['awsInfo']['ec2_state'] = 'running'
    logger.debug("HF: {0}".format(hostFilter))

    # Get the hosts that match the base query
    dbQuery = ((accountQuery)&(appQuery)&(devQuery)&(regionQuery))
    s = db(dbQuery)
    rows = s.select()

    # Iterate through the core hosts and apply the hostFilter
    for row in rows:
        # Get the host data from the notes field
        hostNotes = json.loads(row['notes'])
        # Verify that all of the things in the hostFilter are true
        for key in hostFilter.keys():
            if hostNotes.has_key(key):
                for check in hostFilter[key].keys():
                    try:
                        if hostFilter[key][check] == hostNotes[key][check]:
                            if grid['validHosts'].has_key(row['instance_id']) is False:
                                # Passes the test, set the AWS instanceID to the databaseID
                                grid['validHosts'][row['instance_id']] = row['id']
                            # If this host has already failed a prior test, don't add it now
                            elif grid['validHosts'][row['instance_id']] is None:
                                pass
                        else:
                            # Host fails the test, set it to None (clean it up later)
                            grid['validHosts'][row['instance_id']] = None
                    except KeyError:
                        # If the host doesn't have a matching key, then it doesn't match the filter
                        grid['validHosts'][row['instance_id']] = None


    # Get rid of the hosts that don't match the hostFilter
    for key in grid['validHosts'].keys():
        if grid['validHosts'][key] is None:
            del grid['validHosts'][key]

    logger.debug("HostIDs: {0}".format(grid['validHosts'].values()))
    logger.debug("This search found {0} hosts".format(len(grid['validHosts'])))

    # Download and parse playbook file here... write it out as:
    #  runtimeDir/Task_UUID.yml
    # use serializers.loads_yaml()
    if pbPath:
        pbData = serializers.loads_yaml(urllib2.urlopen(pbPath).read())
        hostGroup = pbData[0]['hosts']
        fileutils.write_file(os.path.join(runtimeDir,W2P_TASK.uuid+".yml"),serializers.yaml(pbData))



    # Generate inventory file
    #  runtimeDir/Task_UUID.inv
    # Need to parse out teh playbook file first to determine what group we should put the hosts in.
    invHosts = "[{0}]\n".format(hostGroup)
    for row in db(db.hostInfo.id.belongs(grid['validHosts'].values())).select():
        hostNotes = serializers.loads_json(row.notes)
        if utils.is_valid_ip_address(hostNotes['awsInfo']['ec2_ip_address']):
            sshKeyFilePath = os.path.join(runtimeDir,W2P_TASK.uuid+hostNotes['awsInfo']['ec2_ip_address']+".key")
            try:
                thisHostKey = serverTask_config.keyData[hostNotes['awsInfo']['ec2_key_name']] 
                sshKeyFilePath = os.path.join(runtimeDir,W2P_TASK.uuid+hostNotes['awsInfo']['ec2_ip_address']+".key")
            except KeyError:
                logger.debug("Unable to find a key named {0} using default".format(hostNotes['awsInfo']['ec2_key_name']))
                thisHostKey = serverTask_config.keyData['default']

            fileutils.write_file(sshKeyFilePath,thisHostKey)
            os.chmod(sshKeyFilePath,0600)

            thisHostString = "{0} ansible_ssh_host={1} ansible_ssh_private_key_file={2} ansible_ssh_user=ec2-user\n".format(row.instance_id,hostNotes['awsInfo']['ec2_ip_address'],sshKeyFilePath)
            invHosts = "{0} {1}".format(invHosts,thisHostString)
        else:
            logger.warn("{0} is not a valid IP address".format(hostNotes['awsInfo']['ec2_ip_address']))

    fileutils.write_file(os.path.join(runtimeDir,W2P_TASK.uuid+".inv"),invHosts)

    # Run the task
    cmdLine = "/usr/bin/ansible-playbook -e 'parapetServer=true' -vvv -i {invFile} {pbFile}".format(invFile=os.path.join(runtimeDir,W2P_TASK.uuid+".inv"),pbFile=os.path.join(runtimeDir,W2P_TASK.uuid+".yml"))

    logger.debug("{0}".format(cmdLine))

    #ansibleOut = subprocess.Popen(cmdLine, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0]
    ansible = subprocess.Popen(cmdLine,shell=True,cwd=runtimeDir,stdout=subprocess.PIPE)
    while ansible.poll() is None:
        # Only 1 newline??
        print ansible.stdout.readline(),

    #logger.info(ansibleOut)
    #print ansibleOut
    try:
        keyFiles = fileutils.listdir(runtimeDir,expression="^"+W2P_TASK.uuid+".*\.key$", drop=False)
        for keyFile in keyFiles:
            logger.debug("Removing: {0}".format(keyFile))
            fileutils.recursive_unlink(keyFile)
    except:
        logger.error("Unable to remove key files")
    return 0


###
# Enable the scheduler... on the production systems, set migrate=False, just like on the DAL
scheduler = Scheduler(db, migrate=False, utc_time=True)
#scheduler = Scheduler(db, migrate=True, utc_time=True)
