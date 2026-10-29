import shared_modules.test_shared_module
import shared_modules.test_shared_module as test_shared_module
from common.methods import set_progress

def run(job, *args, **kwargs):
    param1 = "{{param1}}"
    param2 = "{{param2}}"
    param3 = "{{param3}}"
    slider = "{{slider}}"
    
    set_progress(f"param1: {param1}")
    set_progress(f"param2: {param2}")
    set_progress(f"param3: {param3}")
    
    set_progress(test_shared_module.display_message())

    return {"status": "SUCCESS", "output_message": "Sample output message"}