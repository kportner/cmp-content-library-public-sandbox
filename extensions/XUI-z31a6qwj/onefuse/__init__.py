"""
OneFuse Upstream Provider for CloudBolt

Enables the execution of OneFuse policies via CloudBolt Actions. Currently
offers codeless integrations for Ansible Tower, BlueCat IPAM/DNS, InfoBlox
IPAM/DNS, Men & Mice Micetro IPAM/DNS, SolarWinds IPAM, Microsoft DNS,
Microsoft Active Directory, ServiceNow, Scripting, F5 and more. For more
information, visit the <a href="https://onefuse.cloudbolt.io/">
OneFuse Community Site</a>
"""
from common.methods import set_progress
from xui.onefuse.config import run_config
from xui.onefuse.globals import XUI_PATH
from utilities.logger import ThreadLogger


logger = ThreadLogger(__name__)

__version__ = "2023.1.1"
__credits__ = 'Cloudbolt Software, Inc.'

# explicit list of extensions to be included instead of
# the default of .py and .html only
ALLOWED_XUI_EXTENSIONS = [".js", ".css", ".png", ".py", ".html", ".svg", ".md",
                          ".json"]

run_config(__version__)
