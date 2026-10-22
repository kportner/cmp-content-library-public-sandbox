from os import path

# Logging
VERBOSE_LOGGING = True

# OneFuse Certificate Validation
VERIFY_CERTS = False

# XUI Global Configs
XUI_NAME = __name__.split('.')[1]
# Returns the path of the parent XUI dir
XUI_PATH = path.dirname(path.abspath(__file__))
# The path of the XUI folder
ROOT_PATH = path.dirname(XUI_PATH)

# Upstream Provider
UPSTREAM_VERSION = '2022.3.1'

# Property Toolkit
STATIC_PROPERTY_SET_PREFIX = 'OneFuse_SPS_'  # Global Prefix
MAX_RUNS = 3
IGNORE_PROPERTIES = ["OneFuse_VRA7_Props", "OneFuse_VRA8_Props",
                     "OneFuse_TF_Props"]
UPSTREAM_PROPERTY = "OneFuse_CB_Props"
