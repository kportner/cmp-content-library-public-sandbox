CloudBolt ARM Template XUI
==========================
The CloudBolt ARM Template XUI allows you to present Azure Resource Manager (ARM) Templates as CloudBolt Blueprints. This gives you the ability to quickly add support for new Azure resource types via the creation of an ARM template. CloudBolt handles the Self-Service and Governance surrounding the submission of the ARM template, as well as manages the provisioning of the ARM Template and providing a means for Lifecycle automation surrounding ARM Templates.

A Note on ARM Templates
-----------------------
There are two very important facets of ARM Templates that you must understand prior to using this XUI.
1. ARM Templates are by nature NOT stateful. When you deploy an ARM template there isn't an easy way to destroy all resources created by that template - unless all resources were placed in the same resource group - then you could delete the resource group, but you can also deploy resources from an ARM template across resource groups. We address this behavior of ARM Templates by capturing all of the Resources created by the ARM template and storing their IDs to the CloudBolt Blueprint so that they can be deprovisioned when the Resource is destroyed.
2. ARM Templates will overwrite objects in Azure if there is an existing object in the target Resource Group with the same name. If you do not wish for existing resources to be overwritten, it is recommended that you put some controls in place to prevent the overwrite of existing resources. CloudBolt OneFuse can help by providing unique standardized names for resources and would be a good way to prevent this condition.

Installation
------------
This XUI can be installed from the CloudBolt Content Library. Once downloaded to your CloudBolt instance, you will need to restart Apache on the CloudBolt node(s) that host the Apache web service. ::

    systemctl restart apache

Prerequisites
-------------
- This XUI was developed against CloudBolt 9.4.7 Older versions should be compatible, but backwards compatibility is not guaranteed.

Create a Connection Info for Source Control
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1. Create a new Connection Info for Source control if you don't already have one.
    a. Go to Admin > Connection Info > New Connection Info
    b. Input most of the information for the endpoint as requested. For the Password field, you will want to input an API Token generated that has at least read access to the particular ARM template.
    c. Before saving the Connection Info, it must be labelled as azure_devops, github or gitlab

Usage
-----
To manage (add, update, delete) CloudBolt Blueprints backed by ARM Templates, go to ``Admin > Admin Extensions > ARM Template Library``.

Add An ARM Template
^^^^^^^^^^^^^^^^^^^
To create a new Blueprint from an ARM Template, select the ``Create new ARM Template Blueprint`` button.

:Name:
    The name of the Blueprint created in CloudBolt
:Resource Type:
    CloudBolt Resource Type for the Blueprint
:Connection Info:
    Connection Info where the ARM Template is stored
:ARM URL:
    URL to the ARM Template File
:Allowed Environments:
    Select which CloudBolt Environments are eligible to be used for deployment - this will use the

CloudBolt ARM Blueprints can be Synchronized with Source Control, Edited, and deleted by selecting the appropriate icon next to the blueprint in question.

Behavior
--------

Currently Supported Source Control Repositories
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
- GitHub
- Azure DevOps
- GitLab

Supported Parameter Types
^^^^^^^^^^^^^^^^^^^^^^^^^
Only the Following Azure Parameter types are currently supported by this XUI. Objects types are not currently supported
- string
- int
- bool
- array
- secureString

Outputs
^^^^^^^
Outputs from an ARM template will be written back to CloudBolt as parameters on the Resource created from the Blueprint. This allows the template author to define what information will be displayed in CloudBolt.

All ARM Template Output types are supported, but array, object and secureObject types will be converted to a JSON formatted string value.

Allowed Values
^^^^^^^^^^^^^^
Allowed Values declared in ARM Templates will be read in to the CloudBolt blueprint and used to create dropdown values for each parameter.

Default Values
^^^^^^^^^^^^^^
If no Allowed Values are set and there is a Default Value specified for an ARM Template parameter, that default value will be created a single option for the dropdown. Default values are only created the first time a parameter is imported in to CloudBolt.

Minimum and Maximum Values
^^^^^^^^^^^^^^^^^^^^^^^^^^
Minimum and Maximum Values in (minLength, minValue, maxLength, maxValue) constraints in an ARM template will be used to create similar constraints in CloudBolt

Django Templated Parameters
^^^^^^^^^^^^^^^^^^^^^^^^^^^
CloudBolt Parameters leveraged with ARM Templates can accept templated values. For example, to template the value for the ``ARM Deployment Name`` field, to be cloudbolt_7873487 where 7873487 is the CloudBolt Job ID - you would pass in ``cloudbolt_{{ job.id }}``. The following is available as part of the context to use in templating:
- resource
- environment
- group
- job

Parameter Creation Order
^^^^^^^^^^^^^^^^^^^^^^^^
CloudBolt Parameters are created in the order that they show in the ARM template. On subsequent synchronizations of the ARM template, parameters for new values found in the ARM template will show below the original parameters. TO fix this, go to ``Admin > Parameter Display Sequence``, use the browser search function to search for ``arm_<bp_id>`` Where pb_id is the ID of the CloudBolt blueprint. You should see all Parameters that are associated with the particular blueprint and can reorder them to the desired sequence.
