"""
This CloudBolt plugin is designed to do the following:
- Find Server objects in CloudBolt with OneFuse parameters set
- Use the brownfield ingest in OneFuse to migrate the OneFuse objects to a new
  instance of OneFuse
- Update the CloudBolt Server object with the new OneFuse objects
- Allow for the filtering of what servers to migrate - either an entire group
  at a time or a single server

Prerequisites:
- OneFuse Python Module version 2022.3.1 or greater must be installed on the
  CMP system.
"""

import json

from django.db.models import Q
from accounts.models import Group
from common.methods import set_progress
from infrastructure.models import Server
from onefuse.cloudbolt_admin import CbOneFuseManager, Utilities
from xui.onefuse.globals import VERIFY_CERTS
from utilities.logger import ThreadLogger
from xui.onefuse.views import get_onefuse_connection_infos

logger = ThreadLogger(__name__)
utilities = Utilities(logger)


def generate_options_for_source_onefuse(resource=None, **kwargs):
    conn_infos = get_onefuse_connection_infos()
    result_conn_infos = []
    for conn_info in conn_infos:
        result_conn_infos.append((conn_info.name, conn_info.name))
    return result_conn_infos


def generate_options_for_destination_onefuse(field, control_value=None, **kwargs):
    if not control_value:
        return [("", "------First select the source onefuse------")]
    result_conn_infos = []
    conn_infos = get_onefuse_connection_infos()
    for conn_info in conn_infos:
        if conn_info.name != control_value:
            result_conn_infos.append((conn_info.name, conn_info.name))
    return result_conn_infos


def generate_options_for_module(resource=None, **kwargs):
    return [
        (("OneFuse_Naming", "ingest_name"), "Naming"),
        (("OneFuse_AD", "ingest_ad"), "Active Directory"),
        (("OneFuse_Ipam", "ingest_ip_address"), "IPAM"),
        (("OneFuse_Dns", "ingest_dns_reservation"), "DNS"),
        (("OneFuse_PropertyToolkit", None), "Property Toolkit"),
        (("all_modules", None), "All Supported Modules")
    ]


def get_all_modules():
    return [
        ("OneFuse_Naming", "ingest_name"),
        ("OneFuse_AD", "ingest_ad"),
        ("OneFuse_Ipam", "ingest_ip_address"),
        ("OneFuse_Dns", "ingest_dns_reservation"),
        ("OneFuse_PropertyToolkit", None),
    ]


def generate_options_for_group_filter(resource=None, **kwargs):
    groups = Group.objects.filter(~Q(name="Unassigned"), ~Q(name="Default"))
    return [(g.id, g.name) for g in groups]


def generate_options_for_server(field, control_value=None, **kwargs):
    if not control_value:
        return [("", "------Please select a group to filter servers for------")]
    else:
        servers = Server.objects.filter(Q(group__id=control_value),
                                        ~Q(status='HISTORICAL'))
    return [(s.id, s.hostname) for s in servers]


def run(job, **kwargs):
    source_onefuse = "{{ source_onefuse }}"
    destination_onefuse = "{{ destination_onefuse }}"
    module = eval("{{ module }}")
    group_filter = "{{ group_filter }}"
    server_id = "{{server}}"
    logger.debug(f"Dictionary of keyword args passed to this "
                 f"plug-in: {kwargs.items()}")
    source_ofm = get_onefuse_endpoint(source_onefuse)
    destination_ofm = get_onefuse_endpoint(destination_onefuse)
    if server_id:
        servers = Server.objects.filter(id=int(server_id))
    elif group_filter:
        servers = Server.objects.filter(Q(group=group_filter),
                                        ~Q(status='HISTORICAL'))
    else:
        servers = Server.objects.filter(~Q(group__name="Unassigned"),
                                        ~Q(group__name="Default"),
                                        ~Q(status='HISTORICAL'))
    prefix, method_name = module
    set_progress(f'Found {len(servers)} servers from Group filter')
    for server in servers:
        if prefix == "all_modules":
            modules = get_all_modules()
            for module in modules:
                loop_prefix, loop_method_name = module
                onefuse_policies = get_onefuse_policies(server, loop_prefix)
                migrate_onefuse_policies_for_server(server, onefuse_policies,
                                                    loop_prefix, source_onefuse,
                                                    destination_onefuse,
                                                    source_ofm,
                                                    destination_ofm,
                                                    loop_method_name)
        else:
            onefuse_policies = get_onefuse_policies(server, prefix)
            migrate_onefuse_policies_for_server(server, onefuse_policies,
                                                prefix, source_onefuse,
                                                destination_onefuse,
                                                source_ofm, destination_ofm,
                                                method_name)


def migrate_onefuse_policies_for_server(server, onefuse_policies, prefix,
                                        source_onefuse, destination_onefuse,
                                        source_ofm, destination_ofm,
                                        method_name):
    for policy in onefuse_policies:
        policy_key = policy[0]
        mo = policy[1]
        # logger.debug(f"Evaluating Server: {server.hostname}, for migration "
                     # f"of policy_key: {policy_key}")
        if prefix == "OneFuse_PropertyToolkit" or \
                policy_key.find("Policy") > -1:
            endpoint, postfix = mo.split(':', 1)
            if endpoint == source_onefuse:
                set_progress(f'Migrating policy_key: {policy_key} for server: '
                             f'{server}')
                new_value = f'{destination_onefuse}:{postfix}'
                server.set_value_for_custom_field(policy_key, new_value)
                server.save()
            else:
                logger.debug(f'Endpoint: {endpoint} does not match '
                             f'source_onefuse: {source_onefuse}. Skipping '
                             f'migration of policy_key: {policy_key}')
        else:
            mo_json = json.loads(mo)
            if mo_json["endpoint"] == source_onefuse:
                set_progress(f'Migrating policy_key: {policy_key}for server: '
                             f'{server}')
                common_data = get_common_ingest_data(mo_json, source_ofm)
                new_mo = ingest_mo(mo_json, method_name, destination_ofm,
                                   destination_onefuse, common_data)
                update_server(server, new_mo, policy_key)
            else:
                logger.debug(f'Endpoint: {mo_json["endpoint"]} does not'
                             f'match source_onefuse: {source_onefuse}. '
                             f'Skipping migration of policy_key: '
                             f'{policy_key}')
    return None


def ingest_mo(mo, method_name, ofm, endpoint, common_data):
    policy_name, template_properties, tracking_id = common_data
    command_string = f"{method_name}(mo, ofm, policy_name, " \
                     f"template_properties, tracking_id)"
    new_mo = eval(command_string)
    new_mo["endpoint"] = endpoint
    return new_mo


def ingest_name(mo, ofm, policy_name, template_properties, tracking_id):
    name = mo["name"]
    dns_suffix = mo["dnsSuffix"]
    new_mo = ofm.ingest_name(policy_name, name, dns_suffix,
                             tracking_id=tracking_id,
                             template_properties=template_properties)
    return new_mo


def ingest_ad(mo, ofm, policy_name, template_properties, tracking_id):
    name = mo["name"]
    final_ou = mo["finalOu"]
    build_ou = mo["buildOu"]
    state = mo["state"]
    security_groups = mo["securityGroups"]
    new_mo = ofm.ingest_ad(policy_name, name, final_ou, build_ou, state,
                             security_groups, tracking_id=tracking_id,
                             template_properties=template_properties)
    return new_mo


def ingest_ip_address(mo, ofm, policy_name, template_properties, tracking_id):
    ip_address = mo["ipAddress"]
    hostname = mo["hostname"]
    subnet = mo["subnet"]
    primary_dns = mo["primaryDns"]
    secondary_dns = mo["secondaryDns"]
    dns_suffix = mo["dnsSuffix"]
    dns_search_suffixes = mo["dnsSearchSuffixes"]
    gateway = mo["gateway"]
    netmask = mo["netmask"]
    network = mo["network"]
    nic_label = mo["nicLabel"]
    new_mo = ofm.ingest_ip_address(policy_name, ip_address, hostname, subnet,
                                   primary_dns, secondary_dns, dns_suffix,
                                   dns_search_suffixes, gateway, netmask,
                                   network, nic_label=nic_label,
                                   tracking_id=tracking_id,
                                   template_properties=template_properties)
    return new_mo


def ingest_dns_reservation(mo, ofm, policy_name, template_properties,
                           tracking_id):
    name = mo["name"]
    records = mo["records"]
    new_mo = ofm.ingest_dns_reservation(policy_name, name, records,
                                        tracking_id=tracking_id,
                                        template_properties=template_properties)
    return new_mo


def get_common_ingest_data(mo, ofm):
    policy_name = mo["_links"]["policy"]["title"]
    job_href = mo["_links"]["jobMetadata"]["href"]
    template_properties, tracking_id = get_job_data(job_href, ofm)
    return policy_name, template_properties, tracking_id


def get_job_data(job_href, ofm):
    # Return template properties and tracking ID for a OneFuse MO job href
    job_id = job_href.split('/')[5]
    job_json = ofm.get_job_json(job_id)
    payload = job_json["requestInfo"]["payload"]
    template_properties = json.loads(payload)["templateProperties"]
    tracking_id = job_json["jobTrackingId"]
    return template_properties, tracking_id


def get_onefuse_policies(server, prefix):
    properties_stack = server.get_cf_values_as_dict()
    onefuse_policies = []
    for key in properties_stack.keys():
        if key.find(prefix) == 0 and key != "OneFuse_AD_State":
            onefuse_policies.append((key, properties_stack[key]))
    return onefuse_policies


def get_onefuse_endpoint(onefuse_endpoint):
    ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS, logger=logger)
    return ofm


def update_server(server, new_mo, policy_key):
    new_mo_str = json.dumps(new_mo)
    server.set_value_for_custom_field(policy_key, new_mo_str)
    server.save()
    return None
