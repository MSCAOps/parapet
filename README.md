README
=======

parapet is a system to allow you to register your machines into logical groups,
define ansible playbooks, and assign a set of playbooks to a machine group.

This allows you to have reusable playbooks for simple tasks such as:

* Install base OS updates and provision storage
* Install common utilities such as
 * Java
 * Monitoring Software
 * etc.

It then allows you to have specific playbooks for tasks that should only occur on a specific type of machine (e.g. an app-server, memcache, etc.)

System Hierarchy
--------------------

Machines are grouped according to the following hierarchy:

* Accounts
 * Originally named for the fact that we are managing machines in several different AWS accounts but could easily be re-used for any sort of general container (e.g. Development, Staging, Production servers.)
* Applications
 * The finer grained control of what playbooks to run on a particular host.
* Playbooks
 * A link to the actual YAML file that makes up the ansible playbook. Currently, you can reference a playbook using file://, http[s]://, tower://, s3://
* Tasks
 * This is where the real work is done, you assign a combination of Account, Application, and Playbook to create a task. You can create more than one task for the combination of Account and Application allowing you to build your system up from a variety of playbooks.

Accounts
----------

This is a generic key/value dataset of an account number and a friendly name. The client machine should pass in the account number when registering with the parapet server. We use our AWS accounts here. If you create an account with the account number of `000000000000` then that will be used as a generic "All Accounts" bucket for all hosts.

Applications
--------------
This is a generic key/value dataset of an application name and description. The client machine should pass in the application name when registering with the parapet server. We use the application name that we use in our Auto Scaling Groups (those familiar with Asgard from Netflix will understand this concept.) If you create an Application with the name `All Applications` then that will be used as a generic application bucket for all hosts. 

Playbooks
-----------
The location for the parapet client to find/download the ansible playbook that will be run. Our parapet client supports the following URI types for the playbook path:

* file://
 * Used to indicate that the YAML file exists on the client's local file system. This may be a playbook that is part of a machine image.
* http[s]://
 * This indicates that the parapet client should download the YAML file from a remote HTTP or HTTPS host. 
* tower://
 * This indicates that the parapet client should actually call into the Ansible Tower system to request a playbook to be run on/from the tower system.
* s3://
* This indicates that the parapet client should retrieve the YAML file from an S3 bucket. 

The playbooks screen also allows you to set the following attributes on a playbook:

* Name
 * A generic name for the playbook that will be used when assigning the task.
* Key
 * Depending on the URI for the playbook path, this means either the AWS KEY for s3://, Username for HTTP[S]:// URLs that require basic auth, or a playbook ID for a tower:// URI
* Secret
 * Depending on the URI for the playbook path, this means either the AWS SECRET for s3://, Password for HTTP[S]:// URLs that require basic auth, or a Host Config Key for tower://
* Description
 * Free form field for describing things.

Tasks
------
This is the meat of parapet, it allows you to assign playbooks to the combination of Account, Application, and some other fields that are described here.

* Task Name
 * Generic name for the task that will show up in the status screen as well as the parapet client log
* AWS Account
 * A drop down list of items configured in the Account datastore
* Application
 * A drop down list of the items configured in the Application datastore
* Playbook
 * A drop down list of items configured in the Playbook
* Development Phase
 * Used to allow yet another free-form identifier for differentiating hosts that have a common account and application intersection.
* Extra Vars
 * Space separated key=value pairs used to define extra variables that will be passed into the ansible-playbook command using the -e parameter.
* Encrypted Vars
 * A path to an ansible-vault file that will be downloaded and then passed to the ansible-playbook command using -e@value_file (it's up to the client to be able to determine how to pass in the password to the ansible-playbook command. Our client is able to determine it from information available on the host.)
* Run Order
 * Allows you finer grained control over the order in which playbooks are assigned to the client. By default it will be the order that you create the tasks, but if you create them out of order, you can modify that run order here. Smaller numbers run before larger numbers.
* Enabled (checkbox)
 * Allows you to temporarily disable a task if required.

***
One day, more words will be here as you need to manually populate the status table and also describe how to use the View menus.
