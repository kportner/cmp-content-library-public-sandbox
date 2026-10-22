#!/bin/env python

"""
Recurring job to read VMware custom attributes from all VMware VMs managed by CB and set them on Custom Fields (
AKA Parameters) on Servers in CB.

Note that this creates a custom field for every uniquely named custom attribute on all servers in VMware. This may
lead to many Custom Fields being created in CloudBolt, so use with care.

The names of the custom fields are all prefixed with "vmware_cust_attr_" to make them easy to find.
"""

import sys

from django.utils.text import slugify
from pyVim.connect import SmartConnect

from resourcehandlers.vmware.models import VsphereResourceHandler

if __name__ == "__main__":
    import django
    import os

    os.environ["DJANGO_SETTINGS_MODULE"] = "settings"
    django.setup()


from common.methods import set_progress
from infrastructure.models import Server, CustomField
from jobs.models import Job
from resourcehandlers.vmware import pyvmomi_wrapper


def run(*args, **kwargs):
    """
    Loop across all vCenter Resource Handlers in CB, calling another method to import all of their servers' custom attrs
    """
    vcenters = VsphereResourceHandler.objects.all()
    svr_cnt = (
        Server.objects.filter(resource_handler__in=vcenters)
        .exclude(status="HISTORICAL")
        .count()
    )
    set_progress(
        f"Importing custom attributes from {svr_cnt} VMs on {len(vcenters)} vCenter(s)",
        total_tasks=svr_cnt,
        tasks_done=0,
    )
    for vcenter in vcenters:
        import_cust_attrs_for_resource_handler(vcenter)


def import_cust_attrs_for_resource_handler(vcenter: VsphereResourceHandler):
    """
    Loop across all servers for this vCenter Resource Handlers and import  their custom attrs.
    """
    servers = Server.objects.filter(resource_handler=vcenter).exclude(
        status="HISTORICAL"
    )
    svr_cnt = servers.count()
    if svr_cnt > 0:
        set_progress(f"Processing {svr_cnt} VMs on {vcenter}")

        vmware_wrapper = vcenter.get_api_wrapper()
        si = vmware_wrapper._get_connection()
        for server in servers:
            import_cust_attrs_for_server(server, si)


def import_cust_attrs_for_server(server: Server, si: SmartConnect):
    """
    Copy the custom attributes from a single VM in VMware to the Server record in CB.
    """
    vm = pyvmomi_wrapper.get_vm_by_name(si, server.get_vm_name())
    field_manager = si.content.customFieldsManager.field
    cust_attr_cnt = 0
    # Loop across all the custom attributes set on this VM
    for label, value in [
        (field.name, val.value)
        for field in field_manager
        for val in vm.customValue
        if field.key == val.key
    ]:
        # Construct a name for the CustomField that abides by Python's naming standards for variables
        name = "vmware_cust_attr_" + slugify(label)
        _, created = CustomField.objects.get_or_create(
            name=name,
            defaults={"type": "STR", "show_as_attribute": True, "label": label},
        )
        if created:
            set_progress(f"Created custom field {name} with label {label}")
        # Save the value of the custom field on the server object in the CloudBolt DB
        setattr(server, name, value)
        cust_attr_cnt += 1
    # Increment the progress bar by 1 for each server we process
    if cust_attr_cnt:
        # Only add a progress message if there were any cust attrs on the VM
        set_progress(f"Set {cust_attr_cnt} value(s) on {server}", increment_tasks=1)
    else:
        set_progress(increment_tasks=1)


if __name__ == "__main__":
    # For running from the command line when making changes to this plug-in for a fast dev-test cycle
    run(Job.objects.get(id=sys.argv[0]))
