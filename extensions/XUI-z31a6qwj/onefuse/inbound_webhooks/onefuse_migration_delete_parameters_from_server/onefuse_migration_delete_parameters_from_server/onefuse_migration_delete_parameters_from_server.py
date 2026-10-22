from infrastructure.models import Server
from infrastructure.models import CustomField
from utilities.exceptions import NotFoundException
import json
import jsonschema
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)

def inbound_web_hook_post(*args, parameters={}, **kwargs):
    if not parameters['cmp-vm-global-id']:
        raise Exception("Input parameter 'cmp-vm-global-id' not provided")        
    if not parameters['vm-name']:
        raise Exception("Input parameter 'vm-name' not provided")
    if not parameters['migration-task-name']:
        raise Exception("Input parameter 'migration-task-name' not provided")
    if not parameters['parameters-to-delete']:
        raise Exception("Input parameter 'parameters-to-delete' not provided")
    elif not valid_json(parameters['parameters-to-delete'], get_json_schema()):
        raise Exception(f"Input parameter 'parameters-to-delete' "
                        f"is not in a valid format. Format requirements: "
                        f"{get_json_schema()}")
    
    logger.info(f"Deleting Parameters for OneFuse Migration Task "
                f"\"{parameters['migration-task-name']}\" from "
                f"VM \"parameters['vm-name']\" with "
                f"CMP Global ID \"parameters['cmp-vm-global-id']\"")
    
    cmp_vm = Server.objects.get(global_id=parameters['cmp-vm-global-id'])
    if not cmp_vm:
        raise NotFoundException(f"Could not find CMP VM with "
                                f"Global ID {parameters['cmp-vm-global-id']}")
    
    cfvs_manager = cmp_vm.get_cfv_manager()
    
    for parameter_to_delete in parameters['parameters-to-delete']:
        try:
            cfvs_to_deleted = cfvs_manager.select_related("field").filter(
                                        field__name=parameter_to_delete['name']
                                    )
        except DoesNotExist:
            continue
        
        for cfv_to_deleted in cfvs_to_deleted:
            cfv_to_deleted.delete()
        
    cmp_vm.save()
    
    cmp_vm_all_parameters = cmp_vm.get_cf_values_as_dict()
    
    output = {
        'cmp-vm-global-id': parameters['cmp-vm-global-id'],
        'vm-name': parameters['vm-name'],
        'all-parameters-as-string': json.dumps(cmp_vm_all_parameters),
        'all-parameters': cmp_vm_all_parameters
    }
    return(output)
    
def valid_json(json_data, json_schema):
    try:
        jsonschema.validate(json_data, json_schema)
        return True
    except jsonschema.exceptions.ValidationError:
        return False

def get_json_schema():
    json_schema = {
        "type" : "array",
        "items" : {
            "type" : "object",
            "properties" : {
                "name" : {
                    "type" : "string"
                },
                "label" : {
                    "type" : "string"
                },
                "type" : {
                    "type" : "string"
                },
                "description" : {
                    "type" : ["string", "null"]
                },
                "value" : {
                    "type" : "string"
                }
            },
            "required":[
                "name"
            ],
        },
    }  
    return json_schema