"""
This plugin action upgrades VM Tools and the hardware version on a vCenter VM.
"""
import sys
import time
import pyVmomi

from common.methods import set_progress
from infrastructure.models import Server
from resourcehandlers.vmware.pyvmomi_wrapper import get_vm_by_uuid, wait_for_tasks
from resourcehandlers.vmware.models import VsphereResourceHandler
from resourcehandlers.vmware.vmware_41 import TechnologyWrapper


def get_vmware_service_instance(vcenter_rh):
    """
    This function is to get connection to Service Instance

    :param vcenter_rh: vCenter Resource Handler Object
    :return: Service Instance Connection
    """
    assert isinstance(vcenter_rh, VsphereResourceHandler)
    vcenter_rh.init()

    wc = vcenter_rh.resource_technology.work_class
    assert isinstance(wc, TechnologyWrapper)

    return wc._get_connection()


def run(job, logger=None, server=None, **kwargs):
    si = None

    for server in job.server_set.all():
        if not si:
            si = get_vmware_service_instance(server.resource_handler.cast())

        vm = get_vm_by_uuid(si, server.resource_handler_svr_id)

        assert isinstance(vm, pyVmomi.vim.VirtualMachine)

        set_progress(f"Current HW Version: {vm.config.version}")

        server.refresh_info()
        server_original_power_status = server.power_status

        tools_error = ""

        # Power on VM if needed
        if server_original_power_status != "POWERON":
            set_progress("Server is off. Turning it on to upgrade VMware Tools.")
            task = vm.PowerOnVM_Task()
            wait_for_tasks(si, [task])

        # Check VMware Tools status and upgrade if possible
        vm.Reload()
        
        tools_running = False
        
        set_progress("Checking VMware Tools status")
        
        for _ in range(12):  # Wait up to 2 minutes
            vm.Reload()
        
            if vm.guest.toolsRunningStatus == "guestToolsRunning":
                tools_running = True
                break
        
            time.sleep(10)
        
        if tools_running:
        
            vm.Reload()
        
            tools_status = vm.guest.toolsVersionStatus2
            tools_type = getattr(vm.guest, "toolsInstallType", "Unknown")
        
            set_progress(f"VMware Tools Status: {tools_status}")
            set_progress(f"VMware Tools Type: {tools_type}")

            # Oracle Linux 8 (open-vm-tools) reports guestToolsUnmanaged.
            # In this case VMware cannot upgrade the tools through vCenter.
            # current plugin is now correctly handling Oracle Linux 8. 
            # The remaining limitation is a VMware API limitation: UpgradeTools_Task() cannot upgrade open-vm-tools 
            # because the guest OS owns that package.

            if tools_status == "guestToolsUnmanaged":
                set_progress(
                    "VMware Tools are managed by the guest operating system "
                    "(open-vm-tools). Skipping VMware Tools upgrade."
                )
            else:
                set_progress("Upgrading VMware Tools")
        
                try:
                    task = vm.UpgradeTools_Task()
                    wait_for_tasks(si, [task])
        
                    vm.Reload()
        
                    set_progress(
                        f"VMware Tools status after upgrade: "
                        f"{vm.guest.toolsVersionStatus2}"
                    )
        
                except Exception as e:
                    tools_error = f"Failed to upgrade VMware Tools: {e}"
                    set_progress(
                        f"{tools_error}. Will still try to upgrade hardware version."
                    )
        else:
            set_progress(
                "VMware Tools is not running. Skipping VMware Tools upgrade."
            )

        # Power off VM for hardware upgrade
        set_progress("Powering off server to upgrade HW version")
        task = vm.PowerOffVM_Task()
        wait_for_tasks(si, [task])

        # Create snapshot before upgrade
        set_progress("Creating snapshot")

        task = vm.CreateSnapshot_Task(
            f"version4hw-{time.time()}",
            "Pre Hardware Upgrade Snapshot",
            False,
            True,
        )
        wait_for_tasks(si, [task])

        failure_msg = ""
        already_upgraded = False

        # Upgrade virtual hardware
        try:
            set_progress("Updating HW version")

            # Let VMware select the latest supported hardware version
            task = vm.UpgradeVM_Task()
            wait_for_tasks(si, [task])

        except Exception as e:
            error_msg = str(e)

            if (
                "AlreadyUpgraded" in error_msg
                or "already up-to-date" in error_msg.lower()
            ):
                already_upgraded = True
                set_progress(
                    "Hardware version is already at the latest supported version."
                )
            else:
                failure_msg = (
                    f"Failed to upgrade hardware version: {error_msg}"
                )
                set_progress(
                    f"{failure_msg}. Will now return VM to original power state."
                )

        # Restore original power state
        if server_original_power_status == "POWERON":
            set_progress("Server was originally on, so power it on again")
            task = vm.PowerOnVM_Task()
            wait_for_tasks(si, [task])

        # Hardware upgrade failure should fail the job
        if failure_msg:
            return "FAILURE", "", failure_msg

        # Refresh VM and report final version
        vm.Reload()

        if already_upgraded:
            success_msg = (
                f"Hardware version {vm.config.version} is already up-to-date."
            )
        else:
            success_msg = (
                f"Hardware upgraded successfully. Current version: "
                f"{vm.config.version}"
            )

        set_progress(success_msg)

        # Show VMware Tools failure in Errors section
        # while keeping overall job SUCCESS
        return "SUCCESS", "", tools_error

    return "", "", ""


if __name__ == "__main__":
    """
    This is only executed when this script is run from the command line to ease
    development and debugging.
    """
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <server_id>")
        sys.exit(1)

    s = Server.objects.get(id=sys.argv[1])
    print(run(None, None, s))
