"""
CloudBolt Plug-in that creates snapshot and an Image for an OpenStack VM.
"""
import time
from resourcehandlers.openstack.models import OpenStackServerInfo
from common.methods import set_progress
from utilities.logger import ThreadLogger
from infrastructure.models import Server

logger = ThreadLogger(__name__)


def wait_for_snapshot(connection, snapshot_id, timeout=500):
    """
    Waits for a snapshot to be active and have a non-zero size.

    :param connection: The OpenStack connection object.
    :param snapshot_id: ID of the image to wait for.
    :param timeout: Maximum time (in seconds) to wait for the image. Default is 5 minutes.
    :return: The image object if successful, or None if timed out.
    """
    start_time = time.time()
    while True:
        snapshot = connection.compute.get_image(snapshot_id)
        if snapshot and snapshot.status == "ACTIVE" and snapshot.size > 0:
            return snapshot
        elif time.time() - start_time > timeout:
            set_progress(f"Timed out waiting for snapshot {snapshot_id} to be ready.")
            return None
        time.sleep(10)  # Sleep for 10 seconds before checking again


def wait_for_volume(connection, volume_id, timeout=500):
    """
    Waits for a volume to be active and have a non-zero size.

    :param connection: The OpenStack connection object.
    :param image_id: ID of the image to wait for.
    :param timeout: Maximum time (in seconds) to wait for the image. Default is 5 minutes.
    :return: The image object if successful, or None if timed out.
    """
    start_time = time.time()
    while True:
        volume = connection.volume.get_volume(volume_id)
        if volume and volume.status == "available" and volume.size > 0:
            return volume
        elif time.time() - start_time > timeout:
            set_progress(f"Timed out waiting for volume {volume_id} to be ready.")
            return None
        time.sleep(10)  # Sleep for 10 seconds before checking again


def wait_for_instance(
    connection, instance_id, desired_state="ACTIVE", timeout=600, poll_interval=10
):
    """
    Wait for an OpenStack instance to reach the desired state.

    Args:
        connection (openstack.connection.Connection): The OpenStack connection object.
        instance_id (str): The ID of the instance to monitor.
        desired_state (str): The state that the instance should reach. Default is 'ACTIVE'.
        timeout (int): The maximum number of seconds to wait for the instance to reach the desired state. Default is 600 seconds.
        poll_interval (int): The number of seconds between status checks. Default is 10 seconds.

    Returns:
        bool: True if the instance reached the desired state, False otherwise (e.g., due to a timeout).
    """
    end_time = time.time() + timeout

    while time.time() < end_time:
        instance = connection.compute.get_server(instance_id)
        if instance.status == desired_state:
            return True
        time.sleep(poll_interval)

    return False


def run(job, *args, **kwargs):
    server = job.server_set.first()
    owner = job.owner
    rh = server.resource_handler.cast()
    # Fetch snapshot name from kwargs; but default it to action input.
    name = kwargs.get("new_server_name", "{{new_server_name}}")
    description = "{{ description }}"
    job.set_progress("Checking server {} for snapshot...".format(server))
    location = OpenStackServerInfo.objects.get(server=server).location
    wrapper = rh.get_api_wrapper(location)
    openstack_server = wrapper.connection.compute.find_server(server.hostname)
    if not openstack_server.image:
        error = f"No Image found for {openstack_server.id}: Client Error for url: {rh.protocol}://{rh.ip}:8774/v2.1/images/{openstack_server.id}, Image not found."
        return ("FAILURE", "", error)
    snapshot = rh.create_snapshot(server, name, description)
    new_snapshot_id = snapshot.identifier
    snapshotname = snapshot.name
    volume_size = int(snapshot.server.disk_size or 20)

    try:
        ready_snapshot = wait_for_snapshot(wrapper.connection, new_snapshot_id)
        if ready_snapshot:
            set_progress(f"snapshot created {new_snapshot_id} name: {snapshotname}")

            volume_name = f"{snapshotname}_vol"

            volres = wrapper.connection.block_store.create_volume(
                size=volume_size,
                image_id=new_snapshot_id,
                name=volume_name,
            )

            volume_id = volres["id"]
            ready_volume = wait_for_volume(wrapper.connection, volume_id)
            if ready_volume:
                set_progress(f"Volume  created {volume_id} name: {volume_name}")
                flavor_name = openstack_server.flavor.original_name
                flavor = wrapper.connection.compute.find_flavor(flavor_name)
                if not flavor:
                    raise Exception(f"Flavor '{flavor_name}' not found")

                network_name = next(iter(openstack_server.addresses))
                network = wrapper.connection.network.find_network(network_name)
                network_id = network.id
                
                instance_name = f"{snapshotname}_instance"
                keypair_name = openstack_server.key_name

                set_progress(f"Booting VM {instance_name} from volume {volume_id}")
                new_instance = wrapper.connection.compute.create_server(
                    name=instance_name,
                    flavor_id=flavor.id,
                    image_id=snapshot.identifier,
                    key_name=keypair_name,
                    networks=[{"uuid": network_id}],
                )
                # Wait for VM to be active
                ready_instance = wait_for_instance(wrapper.connection, new_instance.id)
                if ready_instance:
                    new_server = wrapper.connection.compute.find_server(instance_name)
                    mac_addresses = []
                    ip_addresses = []

                    for _, network_info in new_server.addresses.items():
                        for address_info in network_info:
                            if "mac_addr" in address_info:
                                mac_addresses.append(address_info["mac_addr"])
                            if "addr" in address_info:
                                ip_addresses.append(address_info["addr"])

                    env = server.environment
                    svr = Server(
                        status="ACTIVE",
                        hostname=new_instance.name,
                        mac="".join(mac_addresses),
                        ip="".join(ip_addresses),
                        owner=owner,
                        group=server.group,
                        environment=env,
                        resource_handler=env.resource_handler,
                        provision_engine=env.provision_engine,
                        os_build=server.os_build,
                        os_family=server.os_family,
                        power_status="POWERON",
                        resource_handler_svr_id=new_server.id,
                    )
                    svr.save()
                    vm_dict = wrapper.get_vm_by_id(
                        svr.resource_handler_svr_id, location
                    )
                    rh.update_tech_specific_server_details(svr, vm_dict, dry_run=False)
                    svr.refresh_info()
                    logger.info(
                        f"Created new CloudBolt server record with ID {svr.id}."
                    )
                    set_progress(f"VM {instance_name} booted successfully")

    except Exception as err:
        return ("FAILURE", "", err)
    return ("SUCCESS", "Openstack Clone created", "")