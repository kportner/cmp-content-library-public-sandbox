from infrastructure.models import Server
from utilities.exceptions import NotFoundException
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)

def inbound_web_hook_get(*args, parameters={}, **kwargs):
    if not parameters['vm-name']:
        raise Exception("Input parameter 'vm-name' not provided")
    if not parameters['migration-task-name']:
        raise Exception("Input parameter 'migration-task-name' not provided")
    if not parameters['nic-index']:
        raise Exception("Input parameter 'nic-index' not provided")
    if not parameters['ipv4-address']:
        raise Exception("Input parameter 'ipv4-address' not provided")
    
    logger.info(f"Finding Global ID for OneFuse Migration Task "
                f"\"{parameters['migration-task-name']}\" for "
                f"VM \"parameters['vm-name']\" with "
                f"VMware VM UUID \"parameters['vm-instanceuuid']\" on "
                f"VMware vCenter UUID \"parameters['vcenter-instanceuuid']\"")
    
    try:
        cmp_vm = Server.objects.get(hostname=parameters['vm-name'], 
                                    nics__ip=parameters['ipv4-address'], 
                                    nics__index=parameters['nic-index'])
    except DoesNotExist:
        raise NotFoundException(f"Could not find CMP VM name "
                                f"{parameters['vm-name']} and IP "
                                f"{parameters['ipv4-address']} on "
                                f"NIC{parameters['nic-index']} ")

    output = {
        'cmp-vm-global-id': cmp_vm.global_id,
        'vm-name': parameters['vm-name']
    }
    return(output)