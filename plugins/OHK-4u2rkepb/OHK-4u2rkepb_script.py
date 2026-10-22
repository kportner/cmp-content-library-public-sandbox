"""
The current code supports Access Policy Key Vaults only

Prerequisites:
    - Azure Key Vault must use the Access Policy authorization model.
      (Enable RBAC Authorization = False)
    - Key Vault must have Soft Delete enabled.
    - Key Vault must have Purge Protection enabled.
    - Key Vault must be enabled for Disk Encryption.
    - An RSA key (2048-bit or higher) must exist in the Key Vault.
    - The Disk Encryption Set (DES) managed identity must have the
      following Key Vault key permissions:
          * get
          * wrapKey
          * unwrapKey
          
"""
from common.methods import set_progress
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.compute.models import (
    DiskEncryptionSet,
    EncryptionSetIdentity,
    KeyForDiskEncryptionSet,
    SourceVault,
    Encryption,
    DiskUpdate,
)
from azure.mgmt.keyvault import KeyVaultManagementClient
from resourcehandlers.azure_arm.azure_wrapper import URI
import random
import string
from datetime import datetime as dt
import time


def generate_options_for_key_vault(server=None, **kwargs):
    options = []
    if not server:
        return []
    wrapper = server.resource_handler.cast().get_api_wrapper()
    client = KeyVaultManagementClient(
        credential=wrapper.credentials,
        subscription_id=wrapper.subscription_id,
    )
    resource_group = server.tech_specific_details().resource_group
    response = client.vaults.list_by_resource_group(
        resource_group_name=resource_group,
    )
    for item in response:
        options.append((item.id, item.name))
    return options

def generate_options_for_key(server=None, control_value=None, **kwargs):
    options = []
    if not server:
        return []
    wrapper = server.resource_handler.cast().get_api_wrapper()
    client = KeyVaultManagementClient(
        credential=wrapper.credentials,
        subscription_id=wrapper.subscription_id,
    )
    if control_value:
        resource_group = server.tech_specific_details().resource_group
        response = client.keys.list(
            resource_group_name=resource_group,
            vault_name=control_value.split("/")[-1],
        )
        for item in response:
            options.append((item.id, item.name))
    return options

def generate_options_for_key_version(server=None, control_value=None, **kwargs):
    options = []
    if not server:
        return []
    wrapper = server.resource_handler.cast().get_api_wrapper()
    client = KeyVaultManagementClient(
        credential=wrapper.credentials,
        subscription_id=wrapper.subscription_id,
    )
    if control_value:
        resource_group = server.tech_specific_details().resource_group
        response = client.keys.list_versions(
            resource_group_name=resource_group,
            vault_name=control_value.split("/")[-3],
            key_name=control_value.split("/")[-1],
        )
        for item in response:
            active = False
            version_object = item
            not_before = version_object.attributes.not_before
            expires = version_object.attributes.expires
            active = (
                    (not_before and not_before < int(dt.today().timestamp())) and (expires and expires > int(dt.today().timestamp()))
                ) or (
                    not not_before and not expires
                ) or (
                    (not_before and not_before < int(dt.today().timestamp())) and not expires
                ) or (
                    (not not_before) and (expires and expires > int(dt.today().timestamp()))
                )

            if active:
                options.append((version_object.key_uri_with_version, version_object.name))
    return options

def generate_options_for_key_type(**kwargs):
    options = ["EncryptionAtRestWithCustomerKey"]
    return options

def generate_options_for_disk_type(**kwargs):
    options = ["OS Disk", "Data Disk"]
    return options
    
def generate_options_for_disk_name(server=None, control_value=None, **kwargs):
    options = []
    if control_value:
        if control_value == "OS Disk":
            return [server.disks.filter(name="OS Disk")[0].uuid]
        else:
            return list(server.disks.all().exclude(name="OS Disk").values_list("uuid", flat=True))
    return options

def run(job, *args, **kwargs):
    res = ''.join(random.choices(string.ascii_letters, k=6))
    server = kwargs.get('server')
    key_vault = "{{ key_vault }}"
    key = "{{ key }}"
    key_version = "{{ key_version }}"
    key_type = "{{ key_type }}"
    disk_type = "{{ disk_type }}"
    disk_name = "{{ disk_name }}"
    wrapper = server.resource_handler.cast().get_api_wrapper()
    credentials = wrapper.credentials
    subscription_id = wrapper.subscription_id
    if server:
        try:
            resource_group = server.tech_specific_details().resource_group
            vm_name = server.get_vm_name()
            compute_client = ComputeManagementClient(credentials, subscription_id)
            vm = compute_client.virtual_machines.get(resource_group, vm_name)

            # create disk encryption set
            KeyForDiskEncryptionSet_object = KeyForDiskEncryptionSet(key_url=key_version,source_vault=SourceVault(id=key_vault))
            encryption_set = DiskEncryptionSet(
                 location=server.tech_specific_details().location,
                 identity=EncryptionSetIdentity(type="SystemAssigned"),
                 encryption_type="EncryptionAtRestWithCustomerKey",
                 active_key=KeyForDiskEncryptionSet_object,
            )
            de_set_response = compute_client.disk_encryption_sets.begin_create_or_update(
                 resource_group_name = resource_group,
                 disk_encryption_set_name = f"{key_vault.split('/')[-1]}-{key.split('/')[-1]}-{key_version.split('/')[-1]}-{res}",
                 disk_encryption_set = encryption_set
            )
            de_set = de_set_response.result()
            client = KeyVaultManagementClient(
                credential=credentials,
                subscription_id=subscription_id,
            )
            response = client.vaults.update_access_policy(
                resource_group_name=resource_group,
                vault_name=key_vault.split('/')[-1],
                operation_kind="add",
                parameters={
                    "properties": {
                        "accessPolicies": [
                            {
                                "tenantId": de_set.identity.tenant_id,
                                "objectId": de_set.identity.principal_id,
                                "permissions": {
                                    "certificates": [],
                                    "keys": [
                                        "get",
                                        "unwrapkey",
                                        "wrapkey"
                                    ],
                                    "secrets": []
                                }
                            },
                        ]
                    }
                },
            )
            
            time.sleep(5)
            vault = client.vaults.get(
                resource_group_name=resource_group,
                vault_name=key_vault.split("/")[-1]
            )

            set_progress(vault.properties.access_policies)
            
            async_vm_deallocate = compute_client.virtual_machines.begin_deallocate(resource_group, vm_name)
            set_progress("Started VM Deallocation")
            async_vm_deallocate.wait()
            set_progress("VM Deallocated")
            du = DiskUpdate(encryption=Encryption(disk_encryption_set_id = de_set.id, type = key_type))
            time.sleep(120)
            async_update = compute_client.disks.begin_update(
                resource_group,
                disk_name,
                du
            )
            async_update.wait()
            # starting the VM
            async_vm_start = compute_client.virtual_machines.begin_start(resource_group, vm_name)
            set_progress("Waiting for VM to start again")
            async_vm_start.wait()
            set_progress("VM is running now")
            set_progress(f"Disk {disk_name} for the VM {server.hostname} has been encrypted successfully.")
            return "SUCCESS", f"Disk {disk_name} for the VM {server.hostname} has been encrypted successfully.", ""
        except Exception as e:
            return "FAILURE", e, e
    else:
        return "WARNING", "Server not found", ""
