#!/usr/local/bin/python

"""
Requires CloudBolt 7.1 rc1 or better. 

Note that this gives requesters the ability to create new OS Builds that are available to other 
users who can request servers in the environment that the server belongs to.
"""

import sys

from resourcehandlers.vmware import pyvmomi_wrapper
from utilities.events import add_server_event
from utilities.logger import ThreadLogger

if __name__ == '__main__':
    import django
    django.setup()

from utilities.exceptions import IllegalStateException, NameInUseException
from common.methods import set_progress
from infrastructure.models import Server
from resourcehandlers.vmware.pyvmomi_wrapper import get_vm_by_uuid, wait_for_tasks, \
    is_vmware_tools_ok
from resourcehandlers.vmware.models import VsphereResourceHandler

logger = ThreadLogger(__name__)


def get_vmware_service_instance(vcenter_rh):
    """    
    :return: the pyvmomi service instance object that represents a connection to vCenter, 
    and which can be used for making API calls.  
    """
    assert isinstance(vcenter_rh, VsphereResourceHandler)
    vcenter_rh.init()
    wc = vcenter_rh.resource_technology.work_class
    return wc._get_connection()


def create_os_build_for_template(handler, server, vm, template_name, os_build_name):
    """
    Calls into the resource handler's logic for adding a template. This is the same logic used 
    when importing templates/images in the UI.
    
    Also associates the new OSB with the environment (unless the env is Unassigned, in which 
    case a message is shown explaining the situation)
    
    :return: The OSBuild object 
    """
    osbuild_attribute, _ = handler.add_template(
        template_name, os_build_name, os_family=server.os_family, reported_os=vm.config.guestId,
        total_disk_size=server.disk_size, toolsStatus=vm.guest.toolsStatus)
    osb = osbuild_attribute.os_build
    set_progress("A new OS Build was created with name '{}' and ID {}".format(osb.name, osb.id))
    env = server.environment
    if env.name == "Unassigned":
        set_progress("The OS Build will not be enabled for the server's environment, since the "
                     "server's environment is unassigned")
    else:
        osb.environments.add(env)
        set_progress("The OS Build was enabled in this server's environment ({})".format(env.name))
    return osb


def check_vmware_tools_status(vm):
    """
    Check if the VMware tools is installed and up-to-date, raise an IllegalStateException if not.
    """
    status = is_vmware_tools_ok(vm)
    if not status:
        msg = "{} This will prevent CloudBolt from provisioning from a template created " \
              "from this VM. Please install the latest version of VMware tools on the VM before " \
              "cloning it to a template.".format(
            status.msg)
        raise IllegalStateException(msg)


def get_template_and_os_build_names():
    template_name = "{{ template_name }}"
    if not template_name or "{{" in template_name:
        # Use a default name for the template
        template_name = '{} template'.format(vm.name)

    os_build_name = "{{ os_build_name }}"
    if not os_build_name or "{{" in os_build_name:
        # Use a the same name for the OSB as for the template by default
        os_build_name = template_name
    return template_name, os_build_name


def run(job, server, **kwargs):
    handler = server.resource_handler.cast()
    si = get_vmware_service_instance(handler)
    vm = get_vm_by_uuid(si, server.resource_handler_svr_id)
    check_vmware_tools_status(vm)
    template_name, os_build_name = get_template_and_os_build_names()

    set_progress("Starting task to clone the VM to template '{}'".format(template_name))
    task = pyvmomi_wrapper.clone_vm_to_template(vm, template_name)
    add_server_event('INFO', server, "Server cloned to template '{}'".format(template_name),
                     job=job, profile=job.owner)
    try:
        wait_for_tasks(si, [task])
    except NameInUseException:
        logger.exception("Error when cloning VM to template")
        raise NameInUseException("The name '{}' is already in use by another template or VM, "
                                 "please try again with a different one.".format(template_name))

    create_os_build_for_template(handler, server, vm, template_name, os_build_name)
    return "", "", ""


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('  Usage:  {} <server_id>'.format(sys.argv[0]))
        sys.exit(1)

    s = Server.objects.get(id=sys.argv[1])
    print(run(None, s))