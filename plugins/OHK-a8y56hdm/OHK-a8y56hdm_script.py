from django.core.exceptions import ObjectDoesNotExist
import openstack
from openstack import connection
from infrastructure.models import CustomField, Environment
from utilities.models import ConnectionInfo
from resourcehandlers.openstack.models import OpenStackHandler
from common.methods import set_progress
from resources.models import ResourceType, Resource


def get_resource_handler(env_id):
    env = Environment.objects.get(id=env_id)
    rh = env.resource_handler.cast()
    return rh

def generate_creds(rh):
    AUTH_URL = f"{rh.protocol}://{rh.ip}:{rh.port}/v3"
    conn = connection.Connection(
        region_name="RegionOne",
        auth={
            "auth_url": AUTH_URL,
            "username": rh.serviceaccount,
            "password": rh.servicepasswd,
            "project_id": rh.project_id,
            "user_domain_name": rh.domain,
            "project_domain_name": rh.domain,
        },
        compute_api_version="2.1",
        identity_interface="public",
        verify=False,
    )

    return conn


def run(job, **kwargs):
    resource = kwargs.pop('resources').first()
    
    env_id = resource.attributes.get(field__name='env_id').value
    rh = get_resource_handler(env_id)
    
    conn = generate_creds(rh)
    
    set_progress("Connection to OpenStack established")
    
    name = resource.attributes.get(field__name='server_name').value
    set_progress("Deleting volume instance {}".format(name))
    try:
        conn.delete_server(name_or_id=name)
    except Exception as error:
        return "FAILURE", "", f"{ error }"

    return "SUCCESS", "Server {} deleted".format(name), ""