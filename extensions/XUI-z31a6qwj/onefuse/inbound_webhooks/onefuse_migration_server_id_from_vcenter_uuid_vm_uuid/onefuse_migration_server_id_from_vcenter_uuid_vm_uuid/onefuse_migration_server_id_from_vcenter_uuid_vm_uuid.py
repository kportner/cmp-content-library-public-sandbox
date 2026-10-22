from infrastructure.models import Server
from resourcehandlers.vmware.models import VsphereResourceHandler
import resourcehandlers.vmware.pyvmomi_wrapper as pyvmomi_wrapper
from utilities.exceptions import NotFoundException
import uuid
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)

def inbound_web_hook_get(*args, parameters={}, **kwargs):
    if not parameters['vm-name']:
        raise Exception("Input parameter 'vm-name' not provided")
    if not parameters['migration-task-name']:
        raise Exception("Input parameter 'migration-task-name' not provided")
    if not parameters['vcenter-instanceuuid']:
        raise Exception("Input parameter 'vcenter-instanceuuid' not provided")
    elif not is_valid_uuid(parameters['vcenter-instanceuuid']):
        raise Exception("Input parameter 'vcenter-instanceuuid' "
                        "is not a valid UUID") 
    if not parameters['vm-instanceuuid']:
        raise Exception("Input parameter 'vm-instanceuuid' not provided")
    elif not is_valid_uuid(parameters['vm-instanceuuid']):
        raise Exception("Input parameter 'vm-instanceuuid' is not a valid UUID")
    
    logger.info(f"Finding Global ID for OneFuse Migration Task "
                f"\"{parameters['migration-task-name']}\" for "
                f"VM \"parameters['vm-name']\" with "
                f"VMware VM UUID \"parameters['vm-instanceuuid']\" on "
                f"VMware vCenter UUID \"{parameters['vcenter-instanceuuid']}\"")
    
    all_vc_rhs = VsphereResourceHandler.objects.all()
    found_vcenter = None
    for a_vc_rh in all_vc_rhs:
        si = a_vc_rh.get_api_wrapper().si_connection        
        
        if si.content.about.instanceUuid == parameters['vcenter-instanceuuid']:
            found_vcenter = si
            rh_id = a_vc_rh.id
            break
        else:
            pyvmomi_wrapper.close_connection(si)
    
    if not found_vcenter:
        raise NotFoundException(f"Could not find vCenter Resource Handler "
                                f"with ID {parameters['vcenter-instanceuuid']}")
    else:
        search_index = found_vcenter.content.searchIndex
        vcenter_vm = search_index.FindByUuid(
                                uuid=parameters['vm-instanceuuid'],
                                vmSearch=True,
                                instanceUuid=True)
        if not vcenter_vm:
            raise NotFoundException(f"Could not find vCenter VM "
                                    f"with instanceUuid "
                                    f"{parameters['vm-instanceuuid']}")
        else:
            vcenter_vm_uuid = vcenter_vm.config.uuid
            cmp_vm = Server.objects.get(
                                resource_handler_svr_id=vcenter_vm_uuid, 
                                resource_handler_id=rh_id)
            if not cmp_vm:
                raise NotFoundException(f"Could not find CMP VM "
                                        f"with resource_handler_svr_id "
                                        f"{vcenter_vm_uuid}")
            else:
                output = {
                            'cmp-vm-global-id': cmp_vm.global_id,
                            'vm-name': parameters['vm-name']
                         }
                return(output)

def is_valid_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False