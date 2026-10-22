from common.methods import set_progress


def run(job, *args, **kwargs):
    """
        This server action will change OS Guest Patching for both Windows and Linux
        This server action supports only Azure VM
        For more details on OS Guest Patching read 'https://learn.microsoft.com/en-us/azure/virtual-machines/automatic-vm-guest-patching'
    """
    set_progress("This will show up in the job details page in the CB UI, and in the job log")

    # Example of how to fetch arguments passed to this plug-in ('server' will be available in
    # some cases)
    server = kwargs.get('server')
    rh = server.resource_handler.cast()

    if rh.resource_technology.name == 'Azure':
        existing_patch_mode = '{{existing_patch_mode}}'
        new_os_patch_mode = '{{new_patch_mode}}'
        wrapper = rh.get_api_wrapper()
        vm_name = server.hostname
        resource_group_name = server.azurearmserverinfo.resource_group
        vm_object = wrapper.compute_client.get_vm_object(vm_name, resource_group_name)
        if check_if_os_is_supported(vm_object):
            existing_patch_mode = ""
            if vm_object.os_profile.linux_configuration:
                os_profile = vm_object.os_profile.linux_configuration
                if not(os_profile.provision_vm_agent):
                    vm_object.os_profile.provision_vm_agent = True
                existing_patch_mode = vm_object.os_profile.linux_configuration.patch_settings.patch_mode
                vm_object.os_profile.linux_configuration.patch_settings.patch_mode = new_os_patch_mode
            elif vm_object.os_profile.windows_configuration:
                """
                    Note :- For Windows VMs, the property osProfile.windowsConfiguration.enableAutomaticUpdates can only be set when the VM is first created. 
                    This impacts certain patch mode transitions. 
                    Switching between AutomaticByPlatform and Manual modes is supported on VMs that have osProfile.windowsConfiguration.enableAutomaticUpdates=false. 
                    Similarly switching between AutomaticByPlatform and AutomaticByOS modes is supported on VMs that have osProfile.windowsConfiguration.enableAutomaticUpdates=true. 
                    
                """
                os_profile = vm_object.os_profile.windows_configuration
                # if not(vm_object_w.os_profile.windows_configuration.enable_vm_agent_platform_updates):
                #     return "FAILURE", f"the server '{vm_name}' has disabled 'VM Agent Platform Updates'","Server Settings disallowed updates"
                if new_os_patch_mode != "":
                    existing_patch_mode = vm_object.os_profile.windows_configuration.patch_settings.patch_mode
                    vm_object.os_profile.windows_configuration.patch_settings.patch_mode = new_os_patch_mode
            update_result = wrapper.compute_client.virtual_machines.begin_create_or_update(
                resource_group_name, vm_name, vm_object
            )
            return "SUCCESS", f"OS Guest Patching mode of '{vm_name}' is changed from '{existing_patch_mode}' to '{new_os_patch_mode}'", "Patch Mode Changed"
        else:
            return "FAILURE", f"This server action is not compatible with os type of server '{vm_name}'", "Not Compatible OS Type"
    else:
        return "FAILURE", f"This server action is not compatible with '{rh.resource_technology.name}'", "Not Compatible Server Action"

def generate_options_for_existing_patch_mode(*args, **kwargs):
    server = kwargs.get("server", None)
    if server:
        rh = server.resource_handler.cast()
        wrapper = rh.get_api_wrapper()
        vm_name = server.hostname
        resource_group_name = server.azurearmserverinfo.resource_group
        vm_object = wrapper.compute_client.get_vm_object(vm_name, resource_group_name)
        existing_patch_mode = vm_object.os_profile.linux_configuration.patch_settings.patch_mode if vm_object.os_profile.linux_configuration else vm_object.os_profile.windows_configuration.patch_settings.patch_mode
        return [("",existing_patch_mode)]
        
def generate_options_for_new_patch_mode(*args, **kwargs):
    """
    Get all Azure patch modes that can be configured for this Server.
    """
    server = kwargs.get("server", None)
    if server:
        rh = server.resource_handler.cast()
        wrapper = rh.get_api_wrapper()
        vm_name = server.hostname
        resource_group_name = server.azurearmserverinfo.resource_group
        vm_object = wrapper.compute_client.get_vm_object(vm_name, resource_group_name)
        if check_if_os_is_supported(vm_object):
            existing_patch_mode = ""
            if vm_object.os_profile.linux_configuration:
                options = [("AutomaticByPlatform","AutomaticByPlatform"),("ImageDefault","ImageDefault")] 
                existing_patch_mode = vm_object.os_profile.linux_configuration.patch_settings.patch_mode
                return  [patchmode for patchmode in options if patchmode[0] != existing_patch_mode]
            elif vm_object.os_profile.windows_configuration: 
                automatic_updates = vm_object.os_profile.windows_configuration.enable_automatic_updates
                existing_patch_mode = vm_object.os_profile.windows_configuration.patch_settings.patch_mode
                if automatic_updates:
                    options = [("AutomaticByPlatform","AutomaticByPlatform"),("AutomaticByOS","AutomaticByOS")]
                    return  [patchmode for patchmode in options if patchmode[0] != existing_patch_mode]
                elif not(automatic_updates):
                    if existing_patch_mode == "AutomaticByOS":
                        # Switching between AutomaticByOS and Manual modes is not supported.
                        return [("","--can not chamge mode from AutomaticByOS to Manual")]
                    elif existing_patch_mode == "AutomaticByPlatform":
                        return [("Manual","Manual")]
        else:
            pass
    return None
    
def check_if_os_is_supported(vm_object):
    """
    This method will check if os type is compatible for guest patching or not
    """
    is_os_supports_patching = False
    publisher = vm_object.storage_profile.image_reference.publisher
    offer = vm_object.storage_profile.image_reference.offer
    sku = vm_object.storage_profile.image_reference.sku
    if publisher in Supported_os_image.keys():
        if offer in Supported_os_image.get(publisher).keys():
            if sku in Supported_os_image[publisher][offer].split(","):
                is_os_supports_patching = True
    return is_os_supports_patching
            
WindowsServer_sku = """2008-R2-SP1,2012-R2-Datacenter,2012-R2-Datacenter-gensecond,2012-R2-Datacenter-smalldisk,2012-R2-Datacenter-smalldisk-g2,2016-Datacenter,2016-datacenter-gensecond,
2016-Datacenter-Server-Core,2016-datacenter-smalldisk,2016-datacenter-with-containers,2019-Datacenter,2019-Datacenter-Core,2019-datacenter-gensecond,2019-datacenter-smalldisk,2019-datacenter-smalldisk-g2,
2019-datacenter-with-containers,2022-datacenter,2022-datacenter-smalldisk,2022-datacenter-smalldisk-g2,2022-datacenter-g2,2022-datacenter-core,2022-datacenter-core-g2,2022-datacenter-azure-edition,
2022-datacenter-azure-edition-core,2022-datacenter-azure-edition-core-smalldisk,2022-datacenter-azure-edition-smalldisk
"""
Supported_os_image = {'Canonical':{'UbuntuServer':'16.04-LTS,16.04.0-LTS,18.04-LTS,18.04-LTS-gen2','0001-com-ubuntu-pro-bionic':'pro-18_04-lts','0001-com-ubuntu-server-focal':'20_04-lts,20_04-lts-gen2',
'0001-com-ubuntu-pro-focal':'pro-20_04-lts,pro-20_04-lts-gen2','0001-com-ubuntu-server-jammy':'22_04-lts,22_04-lts-gen2'},'microsoftcblmariner':{'cbl-mariner':'cbl-mariner-1,1-gen2,cbl-mariner-2,cbl-mariner-2-gen2'},
'microsoft-aks':{'aks':'aks-engine-ubuntu-1804-202112'},'Redhat':{'RHEL':'7.2,7.3,7.4,7.5,7.6,7.7,7.8,7_9,7-RAW,7-LVM,8,8.1,81gen2,8.2,82gen2,8_3,83-gen2,8_4,84-gen2,8_5,85-gen2,8_6,86-gen2,8-lvm,8-lvm-gen2','RHEL-RAW':'8-raw, 8-raw-gen2'},
'OpenLogic':{'CentOS':'7.2,7.3,7.4,7.5,7.6,7.7,7_8,7_9,7_9-gen2,8.0,8_1,8_2,8_3,8_4,8_5','centos-lvm':'7-lvm,8-lvm'},'SUSE':{'sles-12-sp5':'gen1,gen2','sles-15-sp2':'gen1,gen2'},
'MicrosoftWindowsServer':{'WindowsServer':WindowsServer_sku}}