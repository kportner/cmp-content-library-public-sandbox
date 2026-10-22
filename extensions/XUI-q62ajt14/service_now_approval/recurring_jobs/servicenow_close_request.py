"""
Hook to close a Service Catalog Request Record for Order an order when complete.
This hook should be created as an Orchestration Action at the Post-Order
Execution hook point
"""

import json
import os
from settings import PROSERV_DIR
from common.methods import set_progress
from itsm.servicenow.models.servicenow_itsm import ServiceNowITSM
from utilities.logger import ThreadLogger
from orders.models import CustomFieldValue
from itsm.servicenow.wrapper import ServiceNowWrapper

logger = ThreadLogger("Service Now Order Close")


def run(order, *args, **kwargs):
    """
    Grabs the Request ID, then sets the ServiceNow Request to Closed Complete
    on success or Closed Incomplete (if Job fails). Also writes IP address and
    Hostname to the Special Instructions Field
    """

    if not order:
        return False
    if order.blueprint and not order.blueprint.is_orderable:
        return False
    try:
        blueprint_order_items = get_bp_order_item(order)
        request_id = [value.str_value for value in blueprint_order_items.custom_field_values.filter(field__label="ServiceNow Order Submit SysID")]
        instructions = create_instructions(blueprint_order_items)
        order_items = blueprint_order_items
    except Exception as e:
        try:
            logger.debug(f'service_now_approval: BPOI not found with SNow ID trying '
                         f'SMOI. Error: {e}')
            smoi = get_smoi(order)
            request_id = [value.str_value for value in smoi.custom_field_values.filter(field__label="ServiceNow Order Submit SysID")]
            instructions = None
            order_items = smoi
        except Exception as e2:
            logger.debug(f'service_now_approval: SMOI not found with SNow ID. Error: '
                         f'{e2}')
            logger.warn("ServiceNow Request ID not on this order, continuing")
            return "SUCCESS", "", ""
    result = close_request(order, request_id, instructions, order_items)
    return result

def get_bp_order_item(order):
    # Find the order_item that has a reference to a servicenow request sys_id
    order_item = order.orderitem_set.filter(
        blueprintorderitem__isnull=False,
        blueprintorderitem__custom_field_values__field__name = 'ServiceNow Order Submit SysID'
    ).first()
    if not order_item:
        raise Exception(f'Blueprint order item could not be found')
    bp_order_item = order_item.cast()
    return bp_order_item


def get_smoi(order):
    # Find the order_item that has a reference to a servicenow request sys_id.
    # Even if there are multiple SMOIs on an order, they all have the same
    # SNow sys id - so only grabbing the first one.
    order_item = order.orderitem_set.filter(
        servermodorderitem__isnull=False,
        servermodorderitem__custom_field_values__field__name='ServiceNow Order Submit SysID'
    ).first()
    if not order_item:
        raise Exception(f'ServerMod order item could not be found')
    smoi = order_item.cast()
    return smoi


def create_instructions(bp_order_item):
    # Gather IP address, hostname for Servers, all Attribute type params from
    # Resource
    resource = bp_order_item.get_resource()
    servers = bp_order_item.get_servers()
    instructions = ''
    if resource:
        attributes = get_resource_attributes(resource)
        if attributes:
            instructions += f"Resource: {resource.name}. Fields: "
            instructions += f'{attributes}\r\n'
    if servers:
        for server in servers:
            instructions += f'Server: {server.hostname}, ' \
                            f'IP Address: {server.ip}\r\n'
    return instructions


def get_resource_attributes(resource):
    attributes_string = ''
    attributes = resource.attributes.all()
    for attribute in attributes:
        if attribute.field.show_as_attribute:
            field = attribute.field.name
            value = attribute.value
            attributes_string += f'{field}: {value}, '
    return attributes_string


def close_request(order, request_id, instructions, order_items):
    set_progress('Closing ServiceNow Request')
    for id in request_id:
        table_id = f"Table Name For {id}"
        table_name = order_items.custom_field_values.filter(field__label=table_id).first().str_value
        blueprint_id = order.blueprint_id
        blueprint_configurations = predefined_configurations(blueprint_id, table_name)
        for value in blueprint_configurations:
            connector_id = value.get("servicenow_connector")
            if ServiceNowITSM.objects.filter(id=connector_id).exists():
                snowitsm = ServiceNowITSM.objects.get(id=connector_id)
                # wrapper = snowitsm.get_api_wrapper()
                if snowitsm.retry_interval and snowitsm.retry_timeout:
                    wrapper = ServiceNowWrapper(snowitsm.ip, snowitsm.port, snowitsm.service_account, snowitsm.password, snowitsm.protocol, retry_interval=snowitsm.retry_interval, retry_timeout=snowitsm.retry_timeout)
                else:
                    wrapper = ServiceNowWrapper(snowitsm.ip, snowitsm.port, snowitsm.service_account, snowitsm.password, snowitsm.protocol)
                base_url = wrapper.service_now_instance_url.replace("/login.do", "")
                request_url = f"{base_url}/api/now/table/{table_name}/{id}"
                request_state, state, stage = get_state(order)
                data = {"request_state": request_state,  #str
                    "state": state,  # int
                    "stage": stage,  # workflow, accepts string
                }
                if instructions:
                    data["special_instructions"] = instructions
                headers = {'Accept': 'application/json',
                    'Content-Type': 'application/json'}
                json_data = json.dumps(data)
                try:
                    raw_response = wrapper.service_now_request(method="PUT",
                                                            url=request_url,
                                                            headers=headers,
                                                            body=json_data)
                    raw_response.raise_for_status()
                    response = raw_response.json()
                    logger.info(f'ServiceNow Request: {id} has been closed')
                except Exception as e:
                        return "FAILURE", f"Exception: {e}", ""
            else:
                set_progress(f'Not able to find the connector for the {value.get("servicenow_connector_name")} configuration, order will not sync to ServiceNow')
    return "", "", ""


def get_state(order):
    status = order.status
    logger.info(f'status: {status}')
    if status == 'FAILURE':
        state = ('closed_incomplete', 4, 'closed_incomplete')
    elif status == 'SUCCESS':
        state = ('closed_complete', 3, 'closed_complete')
    elif status == 'DENIED':
        state = ('closed_rejected', 3, 'closed_complete')
    else:
        raise Exception(f'Order status not supported. Status: {status}')
    return state


def predefined_configurations(blueprint_id, table_name):
    logger.info("Fetching the predefined configurations")
    custom_field_values = CustomFieldValue.objects.filter(field__namespace__name="servicenow_approvals_xui").order_by("id").values("txt_value")
    blueprint_configurations = []
    for rec in custom_field_values:
        data = json.loads(rec['txt_value'])
        if str(blueprint_id) in data["blueprint_id"] and table_name in data['table_name']:
            blueprint_configurations.append(data)
    if len(blueprint_configurations) == 0:
        for rec in custom_field_values:
            data = json.loads(rec['txt_value'])
            if data.get("default"):
                blueprint_configurations.append(data)
    blueprint_configurations = get_unique_configs(blueprint_configurations)
    return blueprint_configurations


def get_unique_configs(blueprint_configurations):
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