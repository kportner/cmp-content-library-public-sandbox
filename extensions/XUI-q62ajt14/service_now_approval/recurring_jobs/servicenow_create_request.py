"""
Hook to add ServiceNow Request Record for Order when submitted.
This hook should be created as an Orchestration Action at the Order Submission
hook point
"""
import os
import json
import requests
from django.contrib.auth.models import User
from common.methods import set_progress
from utilities.logger import ThreadLogger
from orders.models import get_current_time, ActionJobOrderItem, \
    BlueprintOrderItem, ServerModOrderItem, ProvisionServerOrderItem
from settings import PROSERV_DIR
from jobs.models import Job
from costs.models import CustomFieldRate
from itsm.servicenow.models.servicenow_itsm import ServiceNowITSM
from urllib.parse import urlencode
from orders.models import CustomFieldValue
import re
from common.str import to_snake_case
from itsm.servicenow.wrapper import ServiceNowWrapper


logger = ThreadLogger("Service Now Order Submit")


def run(order, *args, **kwargs):
    if not order:
        return False
    blueprint_order_items, server_mod_order_items = get_order_items(order)
    if not blueprint_order_items and not server_mod_order_items:
        logger.info(f'service_now_approval: ServiceNow approval is only configured for '
                    f'BluePrintOrderItem, and ServerModOrderItem types. '
                    f'Auto-approving order because none of these types were '
                    f'included')
        order.approve()
        return "SUCCESS", "", ""
    blueprint_id = order.blueprint_id
    if blueprint_id and not order.blueprint.is_orderable:
        return "FAILURE", "Exception: Blueprint not orderable", ""
    blueprint_configurations = predefined_configurations(blueprint_id)
    if blueprint_configurations:
        for value in blueprint_configurations:
            connector_id = value.get("servicenow_connector")
            s = value.get("table_name")
            table_name = s[s.find("(")+1:s.find(")")]
            extra_data = value.get("data")
            if ServiceNowITSM.objects.filter(id=connector_id).exists():
                snowitsm = ServiceNowITSM.objects.get(id=connector_id)
                # wrapper = snowitsm.get_api_wrapper()
                if snowitsm.retry_interval and snowitsm.retry_timeout:
                    wrapper = ServiceNowWrapper(snowitsm.ip, snowitsm.port, snowitsm.service_account, snowitsm.password, snowitsm.protocol, retry_interval=snowitsm.retry_interval, retry_timeout=snowitsm.retry_timeout)
                else:
                    wrapper = ServiceNowWrapper(snowitsm.ip, snowitsm.port, snowitsm.service_account, snowitsm.password, snowitsm.protocol)
                base_url = wrapper.service_now_instance_url.replace("/login.do", "")
                sysid_for_req_by, sysid_for_req_for = get_sysid_for_users(snowitsm,
                                                                    base_url, order)
                if blueprint_order_items:
                    order_items = blueprint_order_items
                elif server_mod_order_items:
                    order_items = server_mod_order_items
                approval_field_name = value.get("approval_field_name")
                result, approval_status, error_status = create_service_request(
                    wrapper, base_url, order, sysid_for_req_by, sysid_for_req_for, order_items, table_name, extra_data, approval_field_name)

                if not error_status:
                    return result
            else:
                set_progress(f'Not able to find the connector for the {value.get("servicenow_connector_name")} configuration, order will not sync to ServiceNow')
    elif not blueprint_configurations:
        set_progress(f'No configuration found for the blueprint ({order.blueprint.name}) of this order: {order.id}, so skipping it from servicenow approval process.')


def get_order_items(order):
    logger.info("Fetching order items")
    blueprint_order_items, server_mod_order_items = None, None
    blueprint_order_items = get_blueprint_order_item(order)
    if not blueprint_order_items:
        server_mod_order_items = get_server_mod_order_items(order)
    return blueprint_order_items, server_mod_order_items


def get_blueprint_order_item(order):
    logger.info("Fetching Blueprint Order Items")
    order_items = order.orderitem_set.all()
    for order_item in order_items:
        real_order_item = order_item.cast()
        real_order_item_type = type(real_order_item)
        if real_order_item_type == BlueprintOrderItem:
            return real_order_item
    return None


def get_server_mod_order_items(order):
    logger.info("Fetching Server Mod Order Items")
    order_items = order.orderitem_set.all()
    server_mod_order_items_list = []
    for order_item in order_items:
        real_order_item = order_item.cast()
        order_item_type = type(real_order_item)
        if order_item_type == ServerModOrderItem:
            server_mod_order_items_list.append(real_order_item)
    return server_mod_order_items_list


def predefined_configurations(blueprint_id):
    logger.info("Fetching the predefined configurations")
    custom_field_values = CustomFieldValue.objects.filter(field__namespace__name="servicenow_approvals_xui").order_by("id").values("txt_value")
    blueprint_configurations = []
    for rec in custom_field_values:
        data = json.loads(rec['txt_value'])
        if str(blueprint_id) in data["blueprint_id"]:
            blueprint_configurations.append(data)
    if len(blueprint_configurations) == 0:
        for rec in custom_field_values:
            data = json.loads(rec['txt_value'])
            if data.get("default"):
                blueprint_configurations.append(data)
    blueprint_configurations = get_unique_configs(blueprint_configurations)
    return blueprint_configurations


def get_unique_configs(blueprint_configurations):
    logger.info("Fetching the unique configurations")
    unique_blueprint_configurations = []
    for rec in blueprint_configurations:
        rec_bps = set(rec['blueprint_id'])
        if len(unique_blueprint_configurations) > 0:
            for obj in unique_blueprint_configurations:
                can_append = False
                obj_bps = set(obj['blueprint_id'])
                if not (rec_bps & obj_bps) or not rec['table_name'] == obj['table_name']:
                    can_append = True
            if can_append:
                unique_blueprint_configurations.append(rec)
        else:
            unique_blueprint_configurations.append(rec)
    return unique_blueprint_configurations


def get_sysid_for_users(snowitsm, base_url, order):
    logger.info("Fetching sys id for user")
    # Requested By
    requested_by = order.owner.user
    sysid_for_req_by = sysid_username_then_email(requested_by, base_url,
                                                snowitsm, order)
    # Requested For
    sysid_for_req_for = sysid_for_req_by
    if order.recipient:
        recipient = order.recipient.user
        sysid_for_req_for = sysid_username_then_email(recipient, base_url,
                                                    snowitsm, order)
    return sysid_for_req_by, sysid_for_req_for


def sysid_username_then_email(user, base_url, snowitsm, order):
    """
    Try to get the sysid for the CloudBolt user first by username, if that
    doesn't work try email.
    """
    logger.info("Fetching sys id for user with username or email")
    user_name = user.username
    try:
        sysid = get_snow_user_sys_id(user_name, base_url, snowitsm, order)
    except Exception as e:
        if str(e).find('Unable to find data matching order owner') == 0:
            # If user can't be found using username, try email
            user_name = user.email
            sysid = get_snow_user_sys_id(user_name, base_url, snowitsm, order)
        else:
            raise
    return sysid


def get_snow_user_sys_id(user_name, base_url, snowitsm, order):
    logger.info("Fetching servicenow id for user")
    snow_user_data = lookup_ci(table_name='sys_user',
                            ci_query={'user_name': user_name},
                            base_url=base_url,
                            return_ci=['sys_id'],
                            conn=snowitsm)
    if not snow_user_data:
        err = 'Unable to find data matching order owner in ServiceNow. '
        err += f'requested_by: {user_name} --> order: {order.id}'
        logger.warning(err)
        raise Exception(err)

    sysid = snow_user_data['sys_id']
    if not sysid:
        err = f"ServiceNow sys_id for '{user_name}' not found"
        raise Exception(err)
    return sysid


def lookup_ci(table_name=None, ci_name=None, ci_value=None, ci_query=None,
              base_url=None, return_ci='sys_id', sysparm_query=True,
              conn=None):
    ci_value_data = None
    if ci_query:
        query = urlencode(ci_query)
    else:
        prefix = "sysparm_query"
        if not sysparm_query:
            query = urlencode({ci_name: ci_value})
        else:
            query = urlencode({prefix: f"{ci_name}={ci_value}"})

    url = base_url + f"/api/now/table/{table_name}?{query}"
    response = requests.get(
        url=url,
        auth=(conn.service_account, conn.password),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        timeout=5.0
    )
    try:
        # if a list of values are sent for return, then populate a dictionary
        if isinstance(return_ci, list):
            ci_value_data = {}
            for item in return_ci:
                ci_value_data[item] = response.json()["result"][0][item]
        else:
            if return_ci == "*":
                # return everything we got back
                ci_value_data = response.json()["result"][0]
            else:
                ci_value_data = response.json()["result"][0][return_ci]
    except Exception:
        pass
    return ci_value_data


def create_service_request(wrapper, base_url, order, req_by, req_for, order_item, table_name, extra_data, approval_field_name):
    set_progress("ServiceNow Create Request")
    request_url = f"{base_url}/api/now/table/{table_name}"
    description, rate, server, resource = create_description_and_rate(order, order_item)
    data = {"requested_by": req_by,
            "requested_for": req_for,
            "description": description,
            "price": str(rate),
            }
    group = order.group
    local_variables = locals()
    extra_payload = get_extra_payload(extra_data, local_variables)
    data.update(extra_payload)
    headers = {'Accept': 'application/json',
               'Content-Type': 'application/json'}

    json_data = json.dumps(data)

    try:
        raw_response = wrapper.service_now_request(method="POST",
                                                   url=request_url,
                                                   headers=headers,
                                                   body=json_data)
        response = raw_response.json()
        sys_id = response["result"].get("sys_id")
        request_number = response["result"].get("number")
        if not sys_id:
            raise NameError("ServiceNow sys_id not found")
        if not request_number:
            raise NameError("ServiceNow Request Number not found")
        else:
            if type(order_item) == BlueprintOrderItem:
                add_servicenow_info_to_oi(order_item, request_number, sys_id, table_name)
            elif type(order_item) == list:
                for smoi in order_item:
                    add_servicenow_info_to_oi(smoi, request_number, sys_id, table_name)
        # Check approved and auto-approve in CB if already approved
        approval_status = response['result'].get(approval_field_name)
        return ("", "", ""), approval_status, True
    except Exception as e:
        cancel_order(order)
        return ("FAILURE", f"Exception: {e}", ""), "", False


def create_description_and_rate(order, order_item):
    logger.info("Creating description and rate")
    rate = order.get_rate()
    server = {}
    resource = {}
    if type(order_item) == BlueprintOrderItem:
        item_descriptions = []
        description = f'Blueprint request for Blueprint: ' \
                      f'{order.blueprint.name}\r\n Order: {order.id}\r\n'
        item_count = 1
        for bpia in order_item.blueprintitemarguments_set.all():
            cfvs = get_clean_custom_field_values(bpia)
            si = bpia.service_item
            if si.real_type.name == 'provision server service item':
                rate = update_rate_for_bpia(bpia, rate, cfvs)
                # Gather data for Server Service Item
                rh = bpia.environment.resource_handler
                server = {to_snake_case(key): value for key, value in cfvs.items()}
                server.update({
                    "os_build": bpia.os_build,
                    "environment": bpia.environment,
                    "hostname": bpia.hostname
                })
                item_description = f'Item {item_count}: {si.name}, Type: Server,' \
                                   f' Resource handler: {rh.name}, Environment: ' \
                                   f'{bpia.environment}, OS Build: ' \
                                   f'{bpia.os_build.name} '
            else:
                # Gather data for any other type
                item_description = f'Item {item_count}: {si.name}'
            if cfvs:
                cfv_list = [f'{key}: {cfvs[key]}' for key in cfvs.keys()]
                item_description += ', '
                item_description += ', '.join(cfv_list)
            item_descriptions.append(item_description)
            item_count += 1
            resource = {
                "name": si.name
            }

        for item in item_descriptions:
            description += f'  - {item}\r\n'
        resource.update({
            "description": description,
            "blueprint": order.blueprint,
            "group": order.group,
            "misc_rate": rate
        })
    elif type(order_item) == list:
        description = f'Request for Server Modification(s)\r\n Order: ' \
                      f'{order.id}\r\n'
        rate = 0
        for smoi in order_item:
            server = smoi.server
            rate += smoi.get_rate()
            description += f'\t> Server: {server.hostname}\r\n' \
                           f'\t   Modifications:\r\n'
            deltas = smoi.delta()
            for key in deltas.keys():
                description += f'\t\t- {key}: {deltas[key]}\r\n'
    return description, rate, server, resource


def get_clean_custom_field_values(bpia):
    logger.info("Clean custom field values")
    # Go through custom fields for an object and remove all password fields
    custom_fields = {}
    cfvs = bpia.get_cfv_manager().all()
    for cfv in cfvs:
        if cfv.field.type != 'PWD':
            custom_fields[cfv.field.label] = cfv.value
    preconfigs = bpia.preconfiguration_values.all()
    for preconfig in preconfigs:
        for pre_cfv in preconfig.get_cfv_manager().all():
            if pre_cfv.field.type != 'PWD':
                custom_fields[pre_cfv.field.label] = pre_cfv.value
    return custom_fields


def update_rate_for_bpia(bpia, rate, cfvs):
    logger.info("Updating rate for blueprint order item")
    # CPU and Mem values in preconfigurations are not working in CB - this will
    # find if the bpia has a preconfig using cpu_cnt or mem and update rates
    supported_types = ["cpu_cnt", "mem_size"]
    preconfig_values = bpia.preconfiguration_values.all()
    for preconfig_value in preconfig_values:
        for cfv in preconfig_value.get_cfv_manager().all():
            if cfv.field.name in supported_types:
                env = bpia.environment
                # First check if a rate is set for the field/env
                cfr = get_cfr(env, cfv)
                if not cfr:
                    logger.warning(f"service_now_approval: No rates were found for "
                                   f"field: {cfv.field.name}. Continuing")
                    continue
                cf_rate = cfr.rate
                cfv_value = cfv.value
                quantity = cfvs.get("quantity") if cfvs.get("quantity") else 1
                rate += (cf_rate * cfv_value * quantity)
    return rate


def get_cfr(env, cfv):
    logger.info("Getting custom field rate")
    cfr = CustomFieldRate.objects.filter(
        environment=env, custom_field=cfv.field
    )
    if not cfr:
        # Then get the global rate for the field if env rate not
        # set
        cfr = CustomFieldRate.objects.filter(
            environment=None, custom_field=cfv.field
        )
    if cfr.count() > 1:
        logger.warning(f"service_now_approval: More than 1 rate was found "
                       f"for field: {cfv.field.name}. The first "
                       f"rate will be selected")
    return cfr.first()


def add_servicenow_info_to_oi(oi,request_number, sys_id, table_name):
    logger.info("Creating custom fields")
    from orders.views import add_cfvs_to_order_item
    add_cfvs_to_order_item(
        oi, {"ServiceNow Order Request Number": request_number}
    )
    add_cfvs_to_order_item(
        oi, {"ServiceNow Order Submit SysID": sys_id}
    )
    order_key = f"Table Name For {sys_id}"
    add_cfvs_to_order_item(
        oi, {order_key: table_name}
    )


def get_approver():
    logger.info("Fetching approver")
    approver, created = User.objects.get_or_create(
        email="service-now@noreply.com",
        defaults={"username": "service-now@noreply.com",
                  "first_name": "Service",
                  "last_name": "Now"})
    return approver


def approve_order(order):
    logger.info("Approving order")
    approver = get_approver()
    profile = approver.userprofile
    order.approved_by = profile
    order.approved_date = get_current_time()
    order.status = 'ACTIVE'
    order.save()

    logger.debug('Before order event saved')
    history_msg = f"The '{order}' has been approved through ServiceNow by: {profile.user.get_full_name()}"
    order.add_event("APPROVED", history_msg, profile=profile)
    logger.debug('After order event saved')

    parent_job = None

    # Saving job objects will cause them be kicked off by the
    # job engine within a minute
    jobs = []
    order_items = [oi.cast() for oi in order.orderitem_set.filter()]
    for order_item in order_items:
        jobtype = getattr(order_item, "job_type", None)
        if not jobtype:
            # the job type will default to the first word of the class type
            # ex. "provision", "decom"

            jobtype = str(order_item.real_type).split(" ", 1)[0]
        quantity = 1

        # quantity is a special field on order_items.  If an
        # order_item has the quantity field, kick off that many
        # jobs
        if (
                hasattr(order_item, "quantity")
                and order_item.quantity is not None
                and order_item.quantity != ""
        ):
            quantity = int(order_item.quantity)
        for i in range(quantity):
            job = Job(
                job_parameters=order_item,
                type=jobtype,
                owner=order.owner,
                parent_job=parent_job,
            )
            job.save()

            # Associate the job with any server(s)
            # This may seem unnecessary because it's done when most jobs
            # run, but it's needed at the very least for scheduled server
            # modification jobs (for changing resources) so they show up on
            # the server as scheduled before they actually run

            # Since ActionJobOrderItem can contain just a resource and not
            # a server, we need to have extra logic here
            if isinstance(order_item, ActionJobOrderItem):
                if order_item.server:
                    servers = [order_item.server]
            else:
                servers = []
                if hasattr(order_item, "server"):
                    servers = [order_item.server]
                elif hasattr(order_item, "servers"):
                    servers = order_item.servers.all()
                for server in servers:
                    server.jobs.add(job)

            jobs.append(job)

    # If it didn't make any jobs, just call it done
    if not jobs:
        order.complete("SUCCESS")

    msg = 'order complete'
    logger.info(f"&nbsp;&nbsp;&nbsp;&nbsp;Order approved: {order.id}")
    return msg


def reject_order(order):
    logger.info("Rejecting order")
    approver = get_approver()
    profile = approver.userprofile
    order.approved_by = profile
    order.approved_date = get_current_time()
    order.denied_reason = 'Order denied in ServiceNow'
    order.status = 'DENIED'
    order.save()


def cancel_order(order):
    logger.info("Cancelling order")
    approver = get_approver()
    profile = approver.userprofile
    order.approved_by = profile
    order.approved_date = get_current_time()
    order.denied_reason = 'Order Cancelled in ServiceNow'
    order.status = 'CANCELED'
    order.save()


def get_extra_payload(extra_data, local_variables):
    final_response = {}
    for key, value in extra_data.items():
        if "{" in value:
            variable = re.findall(r'{(.*?)\}', value)
            for cv in variable:
                try:
                    if "." in cv:
                        new_cv = [sub_v for sub_v in cv.split(".")]
                        if not type(local_variables.get(new_cv[0])).__name__ == "dict":
                            value = value.replace("{"+cv+"}", str(getattr(local_variables.get(new_cv[0]), new_cv[1], "")))
                        else:
                            value = value.replace("{"+cv+"}", str(local_variables.get(new_cv[0])[new_cv[1]]))
                    else:
                        value = value.replace("{"+cv+"}", str(local_variables.get(cv)))
                except KeyError:
                    value = value
        final_response[key] = value
    return final_response
