from infrastructure.models import Server
from infrastructure.models import CustomField
from c2_wrapper import create_custom_field
import json
import jsonschema

def inbound_web_hook_post(*args, parameters={}, **kwargs):
    if not parameters['cmp-vm-global-id']:
        raise Exception("Input parameter 'cmp-vm-global-id' not provided")        
    if not parameters['vm-name']:
        raise Exception("Input parameter 'vm-name' not provided")
    if not parameters['migration-task-name']:
        raise Exception("Input parameter 'migration-task-name' not provided")
    if not parameters['parameters-to-add']:
        raise Exception("Input parameter 'parameters-to-add' not provided")
    elif not valid_json(parameters['parameters-to-add'], get_json_schema()):
        raise Exception(f"Input parameter 'parameters-to-add' is not "
                        f"in a valid format. Format requirements: "
                        f"{get_json_schema()}")
    
    cmp_vm = Server.objects.get(global_id=parameters['cmp-vm-global-id'])
    if not cmp_vm:
        raise NotFoundException(f"Could not find CMP VM with Global ID "
                                f"{parameters['cmp-vm-global-id']}")
    
    for parameter_to_add in parameters['parameters-to-add']:
        create_custom_field(name=parameter_to_add['name'],
                            label=parameter_to_add['label'],
                            description=parameter_to_add['description'],
                            type=parameter_to_add['type'],
                            show_as_attribute=False,
                            show_on_servers=False,
                            available_all_servers=False
                            )
        cmp_vm.set_value_for_custom_field(parameter_to_add['name'], 
                                          parameter_to_add['value'])
    
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
                "name",
                "label",
                "type",
                "description",
                "value"
            ],
        },
    }  
    return json_schema