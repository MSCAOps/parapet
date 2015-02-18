# -*- coding: utf-8 -*-

#########################################################################
## This scaffolding model makes your app work on Google App Engine too
## File is released under public domain and you can use without limitations
#########################################################################

## if SSL/HTTPS is properly configured and you want all HTTP requests to
## be redirected to HTTPS, uncomment the line below:
# request.requires_https()

if not request.env.web2py_runtime_gae:
    ## if NOT running on Google App Engine use SQLite or other DB
    #db = DAL('sqlite://storage.sqlite',pool_size=1,check_reserved=['all'])
    ## Development DAL -- Do development here!
    #db = DAL('mysql://parapet:Samsung266%@localhost/parapet',pool_size=1,check_reserved=['all'],lazy_tables=True)
    ## Production DAL:
    ### Enable this and go to DB Admin to update prod database
    #db = DAL('mysql://parapet:Samsung266%@parapetdb.cb9kgmsywwd0.us-west-2.rds.amazonaws.com/parapet',pool_size=5,check_reserved=['all'], migrate_enabled=True, fake_migrate_all=False)
    ### Enable this, package, deploy
    db = DAL('mysql://parapet:Samsung266%@parapetdb.cb9kgmsywwd0.us-west-2.rds.amazonaws.com/parapet',pool_size=5,check_reserved=['all'], migrate_enabled=True, fake_migrate_all=True,lazy_tables=True)
    session.connect(request, response, db=db)
else:
    ## connect to Google BigTable (optional 'google:datastore://namespace')
    db = DAL('google:datastore')
    ## store sessions and tickets there
    session.connect(request, response, db=db)
    ## or store session in Memcache, Redis, etc.
    ## from gluon.contrib.memdb import MEMDB
    ## from google.appengine.api.memcache import Client
    ## session.connect(request, response, db = MEMDB(Client()))

## by default give a view/generic.extension to all actions from localhost
## none otherwise. a pattern can be 'controller/function.extension'
response.generic_patterns = ['*'] if request.is_local else ['*.json']
## (optional) optimize handling of static files
# response.optimize_css = 'concat,minify,inline'
# response.optimize_js = 'concat,minify,inline'
## (optional) static assets folder versioning
# response.static_version = '0.0.0'
#########################################################################
## Here is sample code if you need for
## - email capabilities
## - authentication (registration, login, logout, ... )
## - authorization (role based authorization)
## - services (xml, csv, json, xmlrpc, jsonrpc, amf, rss)
## - old style crud actions
## (more options discussed in gluon/tools.py)
#########################################################################

from gluon.tools import Auth, Crud, Service, PluginManager, prettydate
auth = Auth(db)
crud, service, plugins = Crud(db), Service(), PluginManager()

## create all tables needed by auth if not custom tables
auth.define_tables(username=True, signature=False)

## configure email
mail = auth.settings.mailer
mail.settings.server = 'logging' or 'smtp.gmail.com:587'
mail.settings.sender = 'you@gmail.com'
mail.settings.login = 'username:password'

## configure auth policy
auth.settings.registration_requires_verification = False
auth.settings.registration_requires_approval = True
auth.settings.reset_password_requires_verification = True

## if you need to use OpenID, Facebook, MySpace, Twitter, Linkedin, etc.
## register with janrain.com, write your domain:api_key in private/janrain.key
from gluon.contrib.login_methods.rpx_account import use_janrain
use_janrain(auth, filename='private/janrain.key')

#########################################################################
## Define your tables below (or better in another model file) for example
##
## >>> db.define_table('mytable',Field('myfield','string'))
##
## Fields can be 'string','text','password','integer','double','boolean'
##       'date','time','datetime','blob','upload', 'reference TABLENAME'
## There is an implicit 'id integer autoincrement' field
## Consult manual for more options, validators, etc.
##
## More API examples for controllers:
##
## >>> db.mytable.insert(myfield='value')
## >>> rows=db(db.mytable.myfield=='value').select(db.mytable.ALL)
## >>> for row in rows: print row.id, row.myfield
#########################################################################

## after defining tables, uncomment below to enable auditing
# auth.enable_record_versioning(db)

db.define_table('accountInfo',
                Field('accountNumber', length=25, unique=True, label="AWS Account Number"),
                Field('friendlyName', length=25, unique=True, label="Common Name"),
                format='%(friendlyName)s')


db.define_table('hostInfo',
                Field('instance_id', length=25, unique=True, label="Instance ID", comment="AWS Instance ID"),
                Field('accountNumber', 'reference accountInfo'),
                Field('region', length=25, label="Region", comment="AWS Region"),
                Field('app', length=25, label="Application", comment="Application Name"),
                Field('instanceType', length=25, label="Machine Size", comment="AWS Instance Type"),
                Field('devPhase', length=25, label="Development Phase"),
                Field('notes', 'text', requires=IS_JSON()),
                format='%(instance_id)s')

db.define_table('appInfo',
                Field('name', length=25, unique=True, label="Application Name"),
                Field('description', 'text'),
                format='%(name)s')


db.define_table('pbInfo',
                Field('name', length=75, unique=True, label="Playbook Name"),
                Field('pbPath', length=255, unique=True, label="Path to playbook", comment="Supports: file://, tower://, http[s]://, s3://"),
                Field('accessKey', length=50, default=None,label="Key", comment="AWS KEY, Username, or playbook ID for tower"),
                Field('secret', length=75, default=None, label="Secret", comment="AWS Secret, Password, or Host Config Key for tower"),
                Field('description', 'text'),
                format='%(name)s')

db.define_table('appTask',
                Field('name', length=75, unique=False, notnull=True, label="Task Name"),
                Field('accountInfo_id', 'reference accountInfo', label="AWS Account"),
                Field('appInfo_id', 'reference appInfo', label="Application"),
                Field('pbInfo_id', 'reference pbInfo', label="Playbook", required=True),
                Field('devPhase', length=25, default=None, label="Development Phase", comment="Leave blank for all phases"),
                Field('extraVars', length=512, default=None, label="Extra Vars", comment="Passed to ansible-playbook (e.g. key1=value1 key2=value2)"),
                Field('encVars', length=512, default=None, label="Encrypted Vars", comment="Path to ansible-vault file"),
                Field('taskOrder', 'integer', label="Run Order", comment="Lower runs earlier in the order", default=1000),
                Field('enabled', 'boolean', label="Enabled", default=True),
                format='%(name)s')

db.define_table('stateInfo',
                Field('name', length=50, unique=True, notnull=True, label="Job State"),
                format='%(name)s')


db.define_table('statusInfo',
                Field('hostInfo_id', 'reference hostInfo', label="AWS Instance"),
                Field('appTask_id', 'reference appTask', label="Application"),
                Field('jobState', 'reference stateInfo', label="State"),
                Field('jobStartTime', 'datetime', label="Start Time"),
                Field('jobResults', 'text', label="Results"),
                )


db.define_table('serverInfo',
                Field('region', length=25, unique=True, required=True, label='Region', comment='AWS Region'),
                Field('rest_url', length=256, required=True, label='REST URL', comment='URL of OpsView server REST API'),
                Field('last_change', 'datetime', label='Last Change', comment='Time of the most recent action'),
                format='%(region)s')


db.define_table('monitorMap',
                Field('serverInfo_id', 'reference serverInfo', required=True, label='OpsView Server'),
                Field('accountInfo_id', 'reference accountInfo', required=True, label='Account', comment='AWS Account'),
                Field('phase', length=25, label='Phase'),
                # ^- these three should be a unique tuple / multicolumn primarykey
                # not sure how to get web2py to enforce that

                Field('hostgroup', length=25, label='Host Group'),
                Field('slave_name', length=128),
                format=lambda r: '-'.join(filter(None, (r.serverInfo_id, r.accountInfo_id, r.phase))))
