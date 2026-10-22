import json
from json import JSONDecodeError

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext as _

from c2_wrapper import create_hook
from cbhooks.models import CloudBoltHook
from common.methods import set_progress
from extensions.views import admin_extension
from infrastructure.models import Server
from servicecatalog.models import ServiceBlueprint
from tabs.views import TabGroup
from tags.models import CloudBoltTag
from utilities.permissions import cbadmin_required
from utilities.decorators import dialog_view
from utilities.models import ConnectionInfo
from utilities.templatetags import helper_tags
from extensions.views import tab_extension, TabExtensionDelegate
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)


def get_docstring():
    return """
The OneFuse XUI for CloudBolt allows for the execution of OneFuse Codeless 
Integrations during the lifecycle of a CloudBolt Blueprint. This XUI relies
on the OneFuse Python Plugin (https://pypi.org/project/onefuse/) which will 
be installed during the setup step.

Installation Instructions:
1. Install the XUI in CloudBolt. The onefuse directory should end up at:
    /var/opt/cloudbolt/proserv/xui/onefuse
2. Restart Apache
    > systemctl restart httpd
2. Create a Connection Info for onefuse. This must be labelled as 'onefuse'
3. Execute the Configuration script.
    > python /var/opt/cloudbolt/proserv/xui/onefuse/configuration/setup.py

OneFuse Parameter usage ('name' : 'value_format'):
    'OneFuse_AnsibleTowerPolicy_<executionstring>_<uniqueName>' : '<onefusehost>:<policyname>:<hosts>:<limit>'
    'OneFuse_DnsPolicy_Nic<#>' : '<onefusehost>:<policyname>:<dnszones>'
    'OneFuse_IpamPolicy_Nic<#>' : '<onefusehost>:<policyname>'
    'OneFuse_ADPolicy' : '<onefusehost>:<policyname>'
    'OneFuse_NamingPolicy' : '<onefusehost>:<policyname>'
    Property Toolkit properties:
        'OneFuse_PropertyToolkit' : '<onefusehost>:true'
        'OneFuse_SPS_<uniqueName>' : '<staticpropertysetname>'
        'OneFuse_CreateProperties_<uniqueName>' : '{"key":"<key>","value":"<value>"}'
    'OneFuse_ScriptingPolicy_<executionstring>_<uniqueName>' : '<onefusehost>:<policyname>'
    'OneFuse_ServiceNowCmdbPolicy_<executionstring>_<uniqueName>' : '<onefusehost>:<policyname>'
    'OneFuse_PluggableModulePolicy_<executionstring>_<uniqueName>' : '<onefusehost>:<policyname>'

    Valid Execution Strings for Ansible Tower and Scripting:
        HostnameOverwrite
        PreCreateResource
        PreApplication (only valid when configuration manager used)
        PostProvision

"""


def get_onefuse_connection_infos():
    tags = CloudBoltTag.objects.filter(name__iexact='onefuse')
    connection_infos = []
    for tag in tags:
        conn_infos = ConnectionInfo.objects.filter(labels=tag)
        for conn_info in conn_infos:
            connection_infos.append(conn_info)
    return connection_infos


@admin_extension(title="OneFuse Integration",
                 description="OneFuse integration library for CloudBolt "
                             "scripts and plugins.")
def onefuse_admin(request, **kwargs):
    context = {
        'docstring': get_docstring(),
        'a': 'b',
        'connection_infos': get_onefuse_connection_infos()
    }

    admin_context = {
        "tabs": TabGroup(
            template_dir="onefuse/templates",
            context=context,
            request=request,
            tabs=[
                # First tab uses template 'groups/tabs/tab-main.html'
                # (_("Configuration"), 'configuration', {}),
                # Tab 2 is conditionally-shown in this slot and
                # uses template 'groups/tabs/tab-related-items.html'
                (_("OneFuse Connections"), "connectioninfo", {}),
                (_("Documentation"), "documentation", {}),
            ],
        )
    }
    return render(request, 'onefuse/templates/onefuse_admin.html',
                  context=admin_context)


@dialog_view
def setup_onefuse(request):
    """
    View for launching the OneFuse setup script.
    """
    if request.method == 'POST':
        hook = CloudBoltHook.objects.get(name="OneFuse CloudBolt Plugin "
                                              "Configuration")
        job = hook.run_as_job()[0]
        msg = format_html(
            _("Job {job_name} has been created to check rule(s).").format(
                job_name=helper_tags.render_simple_link(job)
            )
        )

        messages.info(request, msg)
        return HttpResponseRedirect('/onefuse_admin')
    else:
        create_onefuse_setup_hook()
        content = (
            'Setup OneFuse?')
        action_url = reverse(
            'setup_onefuse')

        return {
            'title': 'Confirm OneFuse Setup',
            'content': content,
            'use_ajax': True,
            'action_url': action_url,
            'submit': 'Setup',
        }


@dialog_view
def create_onefuse_endpoint(request):
    """
    View for launching the OneFuse setup script.
    """
    if request.method == 'POST':
        hook = CloudBoltHook.objects.get(name="OneFuse CloudBolt Plugin "
                                              "Configuration")
        job = hook.run_as_job()[0]
        msg = format_html(
            _("Job {job_name} has been created to check rule(s).").format(
                job_name=helper_tags.render_simple_link(job)
            )
        )

        messages.info(request, msg)
        return HttpResponseRedirect('/onefuse_admin')
    else:
        create_onefuse_setup_hook()
        content = (
            'Setup OneFuse?')
        action_url = reverse(
            'setup_onefuse')

        return {
            'title': 'Confirm OneFuse Setup',
            'content': content,
            'use_ajax': True,
            'action_url': action_url,
            'submit': 'Setup',
        }


def create_onefuse_setup_hook():
    onefuse_hook = {
        'name': "OneFuse CloudBolt Plugin Configuration",
        'description': ("Configure the OneFuse CloudBolt Plugin"),
        'hook_point': None,
        'module': '/var/opt/cloudbolt/proserv/xui/onefuse/configuration/setup.py',
    }
    create_hook(**onefuse_hook)


class OneFuseServerTabDelegate(TabExtensionDelegate):

    def should_display(self):
        server = self.instance
        cfvs = server.get_cf_values_as_dict()
        for key in cfvs.keys():
            if key.find('OneFuse_') == 0:
                return True


@tab_extension(model=Server, title='OneFuse Integrations',
               delegate=OneFuseServerTabDelegate)
def onefuse_integrations_tab(request, obj_id):
    server = Server.objects.get(id=obj_id)
    context = {
        "server": server,
        "onefuse_objects": get_onefuse_objects_data(server)
    }
    return render(request, 'onefuse/templates/server_tab.html',
                  context=context)


def get_onefuse_objects_data(server):
    cfvs = server.get_cf_values_as_dict()
    onefuse_prefixes = get_onefuse_prefixes()
    onefuse_objects = []
    for key, value in cfvs.items():
        for prefix in onefuse_prefixes:
            if key.find(prefix) == 0:
                try:
                    json_value = json.loads(value)
                except JSONDecodeError:
                    continue
                data = {}
                data['policy_type'] = get_policy_type_from_prefix(prefix)
                data['policy_name'] = json_value['_links']['policy']['title']
                suffix = key.replace(prefix, '')
                data['suffix'] = suffix
                data['endpoint'] = json_value['endpoint']
                data['mo_data'] = get_mo_data_for_prefix(prefix, json_value)
                onefuse_objects.append(data)
    return onefuse_objects


def get_policy_type_from_prefix(prefix):
    return prefix.replace("OneFuse_", "").replace("_", " ")


def get_mo_data_for_prefix(prefix, json_value):
    mo_data = ""
    if prefix == 'OneFuse_Naming':
        mo_data += f'Name: {json_value["name"]}<br>'
        mo_data += f'ID: {json_value["id"]}<br>'
        try:
            mo_data += f'DNS Suffix: {json_value["dnsSuffix"]}'
        except KeyError:
            pass
    elif prefix == 'OneFuse_Ipam_':
        mo_data += f'IP Address: {json_value["ipAddress"]}<br>'
        mo_data += f'ID: {json_value["id"]}<br>'
        mo_data += f'Hostname: {json_value["hostname"]}<br>'
    elif prefix == 'OneFuse_Dns_':
        mo_data += f'Name: {json_value["name"]}<br>'
        mo_data += f'ID: {json_value["id"]}<br>'
        for r in json_value["records"]:
            try:
                mo_data += f'{r["type"].upper()} Record: {r["name"]}: '
                mo_data += f'{r["value"]}<br>'
            except KeyError:
                continue
    elif prefix == 'OneFuse_AD':
        mo_data += f'Name: {json_value["name"]}<br>'
        mo_data += f'ID: {json_value["id"]}<br>'
        mo_data += f'Final OU: {json_value["finalOu"]}<br>'
    elif prefix == 'OneFuse_AnsibleTower_':
        mo_data += f'Hosts: {", ".join(json_value["hosts"])}<br>'
        mo_data += f'ID: {json_value["id"]}<br>'
        mo_data += f'Inventory: {json_value["inventoryName"]}<br>'
    elif prefix == 'OneFuse_Scripting_':
        mo_data += f'Hostname: {json_value["hostname"]}<br>'
        mo_data += f'ID: {json_value["id"]}<br>'
    elif prefix == 'OneFuse_ServiceNowCmdb':
        mo_data += f'ID: {json_value["id"]}<br>'
        for ci in json_value["configurationItemsInfo"]:
            try:
                mo_data += f'CI: {ci["ciName"]} ({ci["ciClassName"]})<br>'
            except KeyError:
                continue
    # TODO: Add other prefixes
    return mo_data


def get_onefuse_prefixes():
    return [
        'OneFuse_Naming',
        'OneFuse_AD',
        'OneFuse_Ipam_',
        'OneFuse_Dns_',
        'OneFuse_AnsibleTower_',
        'OneFuse_Scripting_',
        'OneFuse_ServiceNowCmdb',
        'OneFuse_PluggableModule_',
    ]
