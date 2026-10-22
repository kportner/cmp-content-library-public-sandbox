from django.core.exceptions import ObjectDoesNotExist
import openstack
from openstack import connection
from infrastructure.models import CustomField, Environment
from utilities.models import ConnectionInfo
from resourcehandlers.openstack.models import OpenStackHandler
from infrastructure.models import CustomField
from common.methods import set_progress

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

def generate_options_for_volume(control_value=None, **kwargs):
    if not control_value:
        return []

    rh = get_resource_handler(control_value)
    conn = generate_creds(rh)

    options = []

    for vol in conn.list_volumes():
        # Skip volumes that aren't available
        if vol.status != "available":
            continue

        # Get the complete volume object
        full_vol = conn.get_volume(vol.id)

        if full_vol.is_bootable:
            display_name = full_vol.name.strip() if full_vol.name else full_vol.id
            options.append((full_vol.id, display_name))

    return options
    
def generate_options_for_image(control_value=None, **kwargs):
    options = []
    if control_value:
        rh = get_resource_handler(control_value)
        conn = generate_creds(rh)
        images = conn.list_images()
        options= [(image.name) for image in images]
    return options

def generate_options_for_flavor(control_value=None, **kwargs):
    options = []
    if control_value:
        rh = get_resource_handler(control_value)
        conn = generate_creds(rh)
        flavors = conn.list_flavors()
        options = [(flavor.name) for flavor in flavors]
    return options

def generate_options_for_network(control_value=None, **kwargs):
    if not control_value:
        return []

    rh = get_resource_handler(control_value)
    conn = generate_creds(rh)
    options = []
    for net in conn.list_networks():
        if not net.is_router_external:
            options.append((net.name, net.name))
    return options
    
def generate_options_for_security_group(control_value=None, **kwargs):
    options = []
    if control_value:
        rh = get_resource_handler(control_value)
        conn = generate_creds(rh)
        groups = conn.list_security_groups()
        options = [(group.name) for group in groups]
    return options


def generate_options_for_key_pair_name(control_value=None, **kwargs):
    options = []
    if control_value:
        rh = get_resource_handler(control_value)
        conn = generate_creds(rh)
        keys = conn.list_keypairs()
        options = [(key.name) for key in keys]
    return options


def generate_options_for_availability_zone(control_value=None, **kwargs):
    options = []
    if not control_value:
        return [("", "-----First, Select Availability Zone-----")]
    if control_value:
        rh = get_resource_handler(control_value)
        conn = generate_creds(rh)
        zones = conn.list_availability_zone_names()
        options = [(zone) for zone in zones]

    return options


def generate_options_for_floating_ips(control_value=None, **kwargs):
    options = []
    if control_value:
        rh = get_resource_handler(control_value)
        conn = generate_creds(rh)
        floating_ips = conn.list_floating_ips()
        options = [(ip.floating_ip_address) for ip in floating_ips]
    return options


def generate_options_for_cloudbolt_environment(server=None, **kwargs):
    envs = Environment.objects.filter(
        resource_handler__resource_technology__name="OpenStack").values("id", "name")
    return [(env['id'], env['name']) for env in envs]


def get_floating_ip_pool(rh, **kwargs):
    conn = generate_creds(rh)
    pool_list = conn.list_floating_ip_pools()
    return [p['name'] for p in pool_list]

def get_floating_ip_pool(rh):
    conn = generate_creds(rh)
    pools = conn.list_floating_ip_pools()
    return pools[0]["name"] if pools else None

def create_required_custom_fields():
    CustomField.objects.get_or_create(
        name='env_id',
        defaults={
            'label': 'Environment ID',
            'description': 'Used by OpenStack blueprint',
            'type': 'INT',
        }
    )
    CustomField.objects.get_or_create(
        name='server_name', defaults={
            'label': 'Instance name', 'type': 'STR',
            'description': 'Name of the OpenStack BP instance',
        }
    )
    CustomField.objects.get_or_create(
        name='volume', defaults={
            'label': 'volume name', 'type': 'STR',
            'description': 'Name of the OpenStack bootable volume',
        }
    )

def run(job, logger=None, **kwargs):
    resource = kwargs.get('resource')

    env_id = '{{ cloudbolt_environment }}'
    env = Environment.objects.get(id=env_id)
    rh = env.resource_handler.cast()
    
    name = '{{ hostname }}'
    volume = '{{ volume }}'
    flavor = '{{ flavor }}'
    network = '{{ network }}'
    security_group = '{{ security_group }}'
    key_name = '{{ key_pair_name }}'
    availability_zone = '{{ availability_zone }}'
    floating_ip = '{{ floating_ips }}'
    
    pool = get_floating_ip_pool(rh)
    
    
    conn = generate_creds(rh)
    server = conn.create_server(
        name=name,
        flavor=flavor,
        boot_volume=volume,
        network=network,
        key_name=key_name,
        security_groups=security_group,
        auto_ip=True,
        ip_pool=pool,
        wait=True,
        timeout=180,
    )
    set_progress("Creating OpenStack node '{}' from boot volume '{}'".format(
            name, volume)
        )

    # Save cluster data on the resource
    create_required_custom_fields()
    resource = kwargs['resource']
    resource.env_id = env_id
    resource.server_name = name
    resource.volume = volume
    resource.name = name
    resource.save()

    return "SUCCESS","Openstack instance created with name '{}',flavor '{}', network '{}', " \
                     "key pair '{}', boot volume '{}', floating ip '{}', security_group(s) '{}'".format(
               name, flavor, network, key_name, volume, floating_ip, security_group), ""