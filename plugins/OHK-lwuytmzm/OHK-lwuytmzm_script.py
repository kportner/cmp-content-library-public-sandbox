from common.methods import set_progress
from resourcehandlers.views import create_sync_vms_job
from resourcehandlers.aws.models import AWSHandler
from infrastructure.models import Server,CustomField
from orders.models import CustomFieldValue
from resources.models import Resource
from utilities.models.ssh_key import SSHKey, StoredSSHKey
from django.conf import settings
from accounts.models import UserProfile
from jobs.models import Job
import time

def run(job, *args, **kwargs):
    resource = kwargs.get('resource')
    blueprint = resource.blueprint
    proserv_path = getattr(settings, "PROSERV_DIR", None)
    set_progress(f"resource found is {resource}")
    base_name = resource.base_name.replace(" ","-")
    set_progress(f"base_name is {base_name}")
    key_name = resource.ec2_key_name
    rh = AWSHandler.objects.get(id = resource.aws_rh_id)
    servers_before_Sync = Server.objects.filter(status='ACTIVE',resource_handler_id=rh.id)   # Before Sync
    set_progress(f"servers before sync is {len(servers_before_Sync)}")
    
    user = resource.owner
    set_progress(f"Admin user found is {user}")
    sync_job = create_sync_vms_job(user,rh=rh)
    
    status = 'PENDING'
    # To check status of the sync job
    while status != 'SUCCESS':
        set_progress("Syncing and creating new server objects...")
        jb = Job.objects.get(id=sync_job.id)
        status = jb.status
        time.sleep(5)
    set_progress("Syncing and creating new server objects is completed...")
    
    servers_after_Sync  = Server.objects.filter(status='ACTIVE',resource_handler_id=rh.id)  #After Sync
    set_progress(f"servers after sync is {len(servers_after_Sync)}")

    ha_servers = [server for server in servers_after_Sync if base_name in server.hostname]
    ha_servers.sort(key = lambda item:item.hostname)
    
    server_number = 1
    server_dict = {}
    server_id_list = []
    for server in ha_servers:
        cfname = f"ha_server_{server_number}"
        cflabel = f"HA Server ({server_number}) "
        server.set_value_for_custom_field("username","ec2-user")
        CustomField.objects.get_or_create(
            name=cfname,
            defaults={
                "label": cflabel,
                "type": 'URL',
                'show_as_attribute': True,
                "description": 'Used by the HA Architecture blueprint'
            }
            )
        server_number += 1

        base_url = blueprint.get_cf_values_as_dict().get("order_base_url") if 'order_base_url' in blueprint.get_cf_values_as_dict().keys() else "http://localhost:8001/"
        setattr(resource, cfname, f"{base_url}servers/{server.id}/")
        server_id_list.append(server.id)
    
    #set_progress(f"servers id list is {server_id_list}")  #for test only
    
    ssh_keyname_field_name = "key_name"
    ssh_keyname_field_name = rh.ssh_keyname_field_name
    key_name_cf = CustomField.objects.get(name=ssh_keyname_field_name)
    key_name_cfv, __ = CustomFieldValue.objects.get_or_create(field=key_name_cf, str_value=key_name)
    fname = f"{key_name}.pem"
    f = open(f"{proserv_path}{fname}", 'r')
    material = f.read()
    StoredSSHKey.objects.update_or_create(
            name=key_name,
            resource_handler_id=rh.id,
            key_reference=key_name_cfv,
            defaults={"private_key": material},
        )
    CustomField.objects.get_or_create(
        name='server_ids',
        defaults={
            "label": 'Server ID',
            "type": 'STR',
            'show_as_attribute': False,
            "description": 'Used by the HA Architecture blueprint'
        }
        ) 
        
    resource.server_ids =",".join([str(id) for id in server_id_list])
    resource.save()
    return "SUCCESS", "New server objects are created and configured succcessfully ", ""