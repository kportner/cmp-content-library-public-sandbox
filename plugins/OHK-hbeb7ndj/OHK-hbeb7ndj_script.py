#!/usr/bin/env python
"""
To set this up, on your CB server:
 * `pip install usaddress`
 * `cd /var/opt/cloudbolt/proserv/`
 * `git clone https://github.com/gamagori/pizzapi.git`
 *  Navigate to the cloned pizzapi repository: cd /var/opt/cloudbolt/proserv/pizzapi
 
This action intentionally fetches the raw Domino's menu response instead of using
pizzapi.Menu.from_store().
Some current Domino's menu responses can contain category references to products
that are not present in the Products/PreconfiguredProducts sections.
The action therefore uses the live "Variants" data directly.
If you order this blueprint from CloudBolt, and it fails, check your email, it is possible that
the pizza order completed but there was an error when checking the status of the order.

NOTE ON MULTI-ITEM CARTS: "menu_category", "menu", "price", and "quantity" live inside the
"add_menu" paneldynamic (the shopping cart), so they can have one value PER CART ROW, not a
single value. CloudBolt's double-curly-brace blueprint-parameter templating only ever resolves a single,
flat, top-level value per parameter name -- it cannot reach into a paneldynamic row -- so run()
does NOT use "{{ menu }}" / "{{ price }}" / "{{ quantity }}" / "{{ menu_category }}" for these
fields. Instead it reads the raw submitted Custom Form data directly off this job's OrderItem
(job.parent_job.order_item.get_cf_values_as_dict()["custom_form_data"], a JSON string -- verified
against a real job via the Django shell) and pulls the full cart out of its "add_menu" array.

"""
import re
import time
import copy
from types import SimpleNamespace
import sys
PIZZAPI_PATH = "/var/opt/cloudbolt/proserv/pizzapi"
if PIZZAPI_PATH not in sys.path:
    sys.path.insert(0, PIZZAPI_PATH)

# usaddress and pizzapi are prerequisites installed by the CloudBolt admin (see module
# docstring), not always present at blueprint-import time. Importing them lazily here lets
# CloudBolt load this module (e.g. to discover generate_options_for_* functions during
# blueprint import) even before the prerequisites are installed; run() below raises a clear
# error if they are still missing when someone actually tries to place an order.
try:
    import usaddress
    from pizzapi.payment import PaymentObject
    from pizzapi.address import Address
    from pizzapi.order import Order
    from pizzapi.customer import Customer
    from pizzapi.track import track_by_phone
    from pizzapi.urls import Urls
    from pizzapi.utils import request_json
    PREREQ_IMPORT_ERROR = None
except ImportError as exc:
    usaddress = PaymentObject = Address = Order = Customer = None
    track_by_phone = Urls = request_json = None
    PREREQ_IMPORT_ERROR = exc
from datetime import datetime
from types import SimpleNamespace
import requests
import json

from common.methods import set_progress

from utilities.logger import ThreadLogger
logger = ThreadLogger(__name__)

STORE_SEARCH_URL = "https://order.dominos.com/power/store-locator"

def get_store(store_id):
    store = SimpleNamespace()
    store.id = str(store_id)
    # store.urls = Urls(store.id)
    store.urls = Urls()
    return store

def get_store_details(store):
    """
    Equivalent to pizzapi's Store.get_details(), reimplemented directly because get_store() above
    returns a lightweight SimpleNamespace (not a real pizzapi.store.Store instance) -- so it never
    has pizzapi's own get_details() method. This calls the exact same endpoint pizzapi's
    Store.get_details() does: request_json(self.urls.info_url(), store_id=self.id).
    """
    return request_json(store.urls.info_url(), store_id=store.id)

def generate_options_for_store(control_value=None, control_value_dict=None, **kwargs):
    """
    Returns all OPEN Domino's stores for a ZIP code.
    """
    if not control_value:
        return [("", "Please enter the ZIP Code.")]
    control_value_dict = control_value_dict or {}
    zip_code = (control_value or control_value_dict.get("zip_code","") or kwargs.get("zip_code",""))
    logger.info("ZIP CODE = %s", zip_code)
    if not zip_code:
        return [("", "Please enter a ZIP Code.")]
    try:
        response = requests.get(STORE_SEARCH_URL, params={"c": zip_code,"type": "Delivery",}, timeout=20,)

        response.raise_for_status()

        data = response.json()
        logger.info("STORE RESPONSE = %s", data)
        stores = data.get("Stores", [])
        # Some Domino's endpoints return a dict instead of a list
        if isinstance(stores, dict):
            stores = list(stores.values())
        if not stores:
            return [("", "No Domino's stores found.")]
        options = []
        seen = set()
        for store in stores:
            store_id = str(store.get("StoreID"))
            if store_id in seen:
                continue
            
            seen.add(store_id)
            
            # Skip stores that cannot accept delivery
            if not store.get("IsOnlineNow", False):
                continue
            
            if not store.get("AllowDeliveryOrders", False):
                continue
            
            # Some stores only expose ServiceIsOpen

            service_open = (
                store.get("ServiceIsOpen", {})
                     .get("Delivery", True)
            )
            if not service_open:
                continue
            
            # Address
            address = (
                store.get("AddressDescription")
                or "%s, %s, %s %s" % (
                    store.get("Address", {}).get("Street", ""),
                    store.get("Address", {}).get("City", ""),
                    store.get("Address", {}).get("Region", ""),
                    store.get("Address", {}).get("PostalCode", ""),
                )
            )
            address = (address.replace("\r", "").replace("\n", ", ").strip())
            # Delivery ETA
            eta = ""
            delivery = (store.get("ServiceMethodEstimatedWaitMinutes", {}).get("Delivery", {}))
            if delivery:
                minimum = delivery.get("Min")
                maximum = delivery.get("Max")
                if minimum is not None and maximum is not None:
                    eta = " | 🚚 Delivery: %s-%s mins" % (minimum,maximum,)
            # Carryout ETA
            carryout = (store.get("ServiceMethodEstimatedWaitMinutes", {}).get("Carryout", {}))
            if carryout:
                minimum = carryout.get("Min")
                maximum = carryout.get("Max")
                if minimum is not None and maximum is not None:
                    eta += " | 🛍 Carryout: %s-%s mins" % (minimum,maximum,)
            display = "%s%s" % (address,eta,)
            options.append((store_id,display,))
        options.sort(key=lambda x: x[1].lower())
        logger.info("STORE OPTIONS = %s", options)
        if not options:
            return [("", "No open Domino's stores found.")]
        return options
    except Exception:
        logger.exception("Unable to load Domino's stores")
        return [("", "Unable to load Domino's stores.")]


def get_live_menu_data(store):
    """
    Fetch the raw Domino's menu response without constructing pizzapi.Menu.
    The raw response contains "Variants", which is what pizzapi.Order.add_item()
    ultimately uses to construct Products in the order.
    """
    menu_data = request_json(store.urls.menu_url(),store_id=store.id,lang="en",)
    if not isinstance(menu_data, dict):
        raise Exception("Domino's returned an invalid menu response for store %s."% store.id)
    variants = menu_data.get("Variants")
    if not isinstance(variants, dict) or not variants:
        raise Exception("No menu variants were returned for Domino's store %s."% store.id)
    return menu_data
    
def generate_options_for_menu_category(control_value=None, **kwargs):
    if not control_value:
        return [("", "Please select a store first.")]
    try:
        store = get_store(control_value)
        menu_data = get_live_menu_data(store)

        # Get Food categories from the live Domino's menu
        food = (menu_data.get("Categorization", {}).get("Food", {}))
        categories = food.get("Categories", [])
        options = []

        # Icons for Domino's menu categories
        category_icons = {
            "Pizza": "🍕",
            "Sandwich": "🥪",
            "Pasta": "🍝",
            "Wings": "🍗",
            "Bread": "🥖",
            "GSalad": "🥗",
            "Chips": "🍟",
            "Drinks": "🥤",
            "Dessert": "🍰",
            "Sides": "🍴",
        }

        # Add normal Domino's menu categories
        for category in categories:
            name = category.get("Name")
            code = category.get("Code")
            if not name or not code:
                continue

            # Get icon for known category. Use a generic icon for any future/unknown category.
            icon = category_icons.get(
                code,
                "🍽️"
            )
            display_name = "%s %s" % (
                icon,
                name
            )
            options.append(
                (
                    code,
                    display_name
                )
            )

        # Sort normal categories alphabetically.
        options.sort(
            key=lambda x: x[1].lower()
        )

        logger.info(
            "Loaded %s menu categories for store %s",
            len(options),
            control_value
        )
        return options
    except Exception:
        logger.exception(
            "Unable to load categories"
        )
        return []
    
def generate_options_for_menu(control_value=None, control_value_dict=None, **kwargs):
    # Eventually we could make the menu options depend on the address chosen, fetch the menu for
    # the closest store, and then filter it down to the options that do not require customization
    control_value_dict = control_value_dict or {}
    logger.info("control_value = %s", control_value)
    logger.info("control_value_dict = %s", control_value_dict)
    store_id = control_value_dict.get("store")
    selected_category = control_value_dict.get("menu_category")
    if not store_id:
        return [("", "Please enter the ZIP Code.")]
    if not selected_category:
        return [("", "Please select a menu category first.")]
    try:
        store = get_store(store_id)
        menu_data = get_live_menu_data(store)
        
        # MENU
        products = menu_data.get("Products", {})
        variants = menu_data.get("Variants", {})
        if variants:
            logger.info("VARIANT SAMPLE = %s",next(iter(variants.values())))
        food = (menu_data.get("Categorization", {}).get("Food", {}))
        categories = food.get("Categories", [])
        # Collect all product codes recursively
        product_codes = set()
        def collect_products(category):
            product_codes.update(category.get("Products", []))
            for child in category.get("Categories", []):
                collect_products(child)
        for category in categories:
            if category.get("Code") == selected_category:
                collect_products(category)
                break
        if not product_codes:
            return []
        options = []
        seen = set()
        # Convert Product -> Variants
        for product_code in product_codes:
            product = products.get(product_code)
            # Normal Products

            if product:
                for variant_code in product.get("Variants", []):
                    variant = variants.get(variant_code)
                    if not variant:
                        continue
                    code = variant.get("Code") or variant_code
                    if code in seen:
                        continue
                    seen.add(code)
                    display = (variant.get("Name") or product.get("Name")or code)

                    # Get live price from Domino's API

                    price = variant.get("Price")
                    if price not in (None, ""):
                        try:
                            display = "%s - $%.2f" % (display,float(price),)
                        except (TypeError, ValueError):
                            logger.warning("Invalid price '%s' for variant %s",price,code,)
                            display = "%s - $%s" % (display,price,)
                   
                    size = (variant.get("Size") or "")
                    if size and size.lower() not in display.lower():
                        display = "%s (%s)" % (display, size)
                    options.append((code, display))
                    
            # Some product codes are already variants
            elif product_code in variants:
                variant = variants[product_code]
                code = variant.get("Code") or product_code
                if code in seen:
                    continue
                seen.add(code)
                display = (variant.get("Name") or code)
                # Get live price from Domino's API

                price = variant.get("Price")
                if price not in (None, ""):
                    try:
                        display = "%s - $%.2f" % (display,float(price),)
                    except (TypeError, ValueError):
                        logger.warning("Invalid price '%s' for variant %s",price,code,)
                        display = "%s - $%s" % (display,price,)
                size = (variant.get("SizeCode") or variant.get("Size") or "")

                if size and size.lower() not in display.lower():
                    display = "%s (%s)" % (display, size)
                options.append((code, display))
        options.sort(key=lambda x: x[1].lower())
        logger.info("Loaded %s menu items for category %s",len(options),selected_category,)
        return options
    except Exception:
        logger.exception("Unable to load menu")
        return [("", "Unable to load menu.")]
        
def generate_options_for_price(control_value=None, control_value_dict=None, **kwargs):
    control_value_dict = control_value_dict or {}
    store_id = control_value_dict.get("store")
    menu_code = control_value_dict.get("menu")

    logger.info("PRICE store=%s menu=%s",store_id, menu_code)
    if not store_id:
        return [("", "Please select a store first.")]
    if not menu_code:
        return [("", "Please select a menu item first.")]
        
    try:
        store = get_store(store_id)
        menu_data = get_live_menu_data(store)
        
        # Normal Price Menu
        variants = menu_data.get("Variants", {})
        variant = variants.get(menu_code)
        
        if not variant:
            return [("", "Price not available.")]
            
        price = variant.get("Price")
        
        if price in (None, ""):
            return [("", "Price not available.")]
            
        price = float(price)
        price_value = str(price)
        
        logger.info("Price for menu item %s: %s",menu_code,price,)

        return {
            "initial_value": price_value,
            "options": [(price_value, price_value)],
        }
    except Exception:
        logger.exception("Unable to load menu price")
        return [("", "Price not available.")]

def parse_address(full_address):
    """
    Takes a full_address string and return a pizzapi Address
    """
    if not full_address or not full_address.strip():
        raise ValueError("Delivery address is required.")
    addr_parts = usaddress.tag(full_address)[0]
    required_fields = ("AddressNumber","PlaceName","StateName","ZipCode",)
    missing_fields = [field for field in required_fields if not addr_parts.get(field)]
    if missing_fields:
        raise ValueError("Could not parse the delivery address. Missing: %s"% ", ".join(missing_fields))
    addr_line_one = full_address.split(",", 1)[0].strip()
    if not addr_line_one:
        raise ValueError("Could not determine the street address.")
    address = Address(
        addr_line_one,
        addr_parts["PlaceName"],
        addr_parts["StateName"],
        addr_parts["ZipCode"],
    )
    return address
    
def get_payment():
    cc_number = "{{ credit_card_number }}"
    cc_expiration = "{{ credit_card_expiration }}"
    cc_pin = "{{ credit_card_pin }}"
    cc_zip = "{{ credit_card_zip }}"
    return PaymentObject(cc_number,cc_expiration,cc_pin,cc_zip,)
    
def create_order(store, customer, address):
    """
    Create a pizzapi Order without calling Order.__init__().
    The installed pizzapi Order constructor executes:
        self.menu = Menu.from_store(...)
    Menu.from_store() constructs pizzapi.Menu, whose old category parser can
    fail when current Domino's categorization references a product that is
    absent from the returned product dictionaries.
    We do NOT need the category hierarchy to place an order. add_item() only
    requires:
        self.menu.variants[code]
    Therefore this function initializes the same Order attributes used by the
    installed pizzapi Order class, but supplies the live raw Variants directly.
    This avoids:
      * modifying pizzapi/menu.py
      * modifying pizzapi/order.py
      * globally monkey-patching Menu.from_store()
      * concurrency problems caused by temporary class-level monkey patches
    """
    menu_data = get_live_menu_data(store)
    variants = copy.deepcopy(menu_data.get("Variants", {}))
    if not variants:
        raise Exception("No orderable menu variants were returned for store %s."% store.id)

    # Deliberately bypass Order.__init__ because that invokes Menu.from_store(), which is the source of: PRODUCT NOT FOUND: 5260 CouponPizza
    order = Order.__new__(Order)
    order.store = store
    order.menu = SimpleNamespace(variants=variants)
    order.customer = customer
    order.address = address
    # Match the installed pizzapi Order constructor. We use store.urls because it is already configured for the same country/market as the Store object.
    order.urls = store.urls
    order.data = {
        "Address": {
            "Street": address.street,
            "City": address.city,
            "Region": address.region,
            "PostalCode": address.zip,
            "Type": "House",
        },
        "Coupons": [],
        "CustomerID": "",
        "Extension": "",
        "OrderChannel": "OLO",
        "OrderID": "",
        "NoCombine": True,
        "OrderMethod": "Web",
        "OrderTaker": None,
        "Payments": [],
        "Products": [],
        "Market": "",
        "Currency": "",
        "ServiceMethod": "Delivery",
        "Tags": {},
        "Version": "1.0",
        "SourceOrganizationURI": "order.dominos.com",
        "LanguageCode": "en",
        "Partners": {},
        "NewUser": True,
        "metaData": {},
        "Amounts": {},
        "BusinessDate": "",
        "EstimatedWaitMinutes": "",
        "PriceOrderTime": "",
        "AmountsBreakdown": {},
    }
    return order
    
def wait_for_order(phone):
    """
    Loop and wait until the order is delivered
    :return: None
    """
    # Example status_dict that we get back from the API:
    # OrderedDict([('Version', '1.5'), ('AsOfTime', '2018-08-03T11:03:37'), ('StoreAsOfTime',
    # '2018-08-03T11:08:23'), ('StoreID', '7231'), ('OrderID', '2018-08-03#50446'), ('Phone',
    # '5035551234'), ('ServiceMethod', 'Delivery'), ('AdvancedOrderTime', None),
    # ('OrderDescription', '1 Large (14") Hand Tossed Pacific Veggie'),
    # ('OrderTakeCompleteTime', '2018-08-03T11:02:14'), ('TakeTimeSecs', '2'), ('CsrID',
    # 'Power'), ('CsrName', None), ('OrderSourceCode', 'Web'), ('OrderStatus', 'Oven'),
    # ('StartTime', '2018-08-03T11:02:14'), ('MakeTimeSecs', '83'), ('OvenTime',
    # '2018-08-03T11:03:37'), ('OvenTimeSecs', None), ('RackTime', None), ('RackTimeSecs', '0'),
    #  ('RouteTime', None), ('DriverID', None), ('DriverName', None), ('OrderDeliveryTimeSecs',
    # None), ('DeliveryTime', None), ('OrderKey', '723189446303'), ('ManagerID', '5298'),
    # ('ManagerName', 'Rachel')])
    order_status = ""
    prog_msg = ""
    while order_status != "Complete":
        status_dict = track_by_phone(phone)
        if not status_dict:
            logger.warning("No tracking information returned for phone %s",phone,)
            time.sleep(10)
            continue
        order_desc = status_dict.get("OrderDescription", "")
        order_desc = order_desc.replace("\n", ", ")
        order_status = status_dict.get("OrderStatus", "")
        if order_status in ["Oven", "Routing Station"]:
            display_status = "in the %s." % order_status
        else:
            display_status = order_status
        new_prog_msg = "Your order of %s is %s" % (order_desc,display_status,)
        if new_prog_msg != prog_msg:
            prog_msg = new_prog_msg
            set_progress(prog_msg)
        time.sleep(10)
        
def show_delivery_wait_times(store_details):
    """
    Display estimated delivery wait time when Domino's provides it.
    """
    try:
        delivery_times = (store_details.get("ServiceMethodEstimatedWaitMinutes", {}).get("Delivery"))
        if not delivery_times:
            logger.info("Delivery wait time was not returned by the store.")
            return
        # Keep the original logic for reference:
        # delivery_times = store_details['ServiceMethodEstimatedWaitMinutes']['Delivery']
        # min = delivery_times['Min']
        # max = delivery_times['Max']
        # set_progress(f"Delivery time: {min}-{max} minutes")
        min_wait = delivery_times.get("Min")
        max_wait = delivery_times.get("Max")
        if min_wait is None or max_wait is None:
            return
        set_progress("Delivery time: %s-%s minutes"% (min_wait, max_wait))
    except Exception:
        # Delivery-time display should not prevent an otherwise valid order.
        logger.exception("Unable to determine the estimated delivery time.")
        
def get_order_id(result):
    # This method is not currently used, but will be needed if we go back to tracking orders by
    # order ID instead of phone #.
    order_obj = result.get("Order", None)
    if not order_obj:
        logger.warning("Could not fetch the 'Order' key from the result.")
        return
    order_id = order_obj.get("OrderID", None)
    set_progress("Order ID: %s" % order_id)
    return order_id
    
def phone_number_to_int(phone):
    """
    Converts a string phone number to an integer, as needed by track_by_phone()
    >>> phone_number_to_int('503-555-1234')
    5035551234
    >>> phone_number_to_int('503.555.1234')
    5035551234
    """
    phone = re.sub(r"\D", "", str(phone))
    if not phone:
        raise ValueError("Recipient phone number is invalid.")
    return int(phone)
    
def get_cart_items_from_form(job):
    """
    "menu_category", "menu", "price", and "quantity" live inside the "add_menu" paneldynamic
    (one set of values per cart row), so CloudBolt's double-curly-brace blueprint-parameter templating --
    which only ever resolves a single flat value per parameter name -- can't be used for them.
    Reads the raw submitted Custom Form data off this job's OrderItem and returns a list of
    {"pizza_code": ..., "quantity": ..., "row": ..., "menu_category": ...} dicts, one per cart
    row, in submission order.
    """
    res_data = job.parent_job.order_item.get_cf_values_as_dict()
    custom_form_data = json.loads(res_data.get("custom_form_data"))
    # logger.info("=" * 80)
    # logger.info("CUSTOM FORM DATA")
    # logger.info("=" * 80)
    # logger.info("%s", json.dumps(custom_form_data, indent=2, default=str))
    # logger.info("=" * 80)

    add_menu_data = custom_form_data.get("add_menu", [])
    logger.info("=" * 80)
    logger.info("ADD MENU DATA")
    logger.info("=" * 80)
    logger.info("%s", json.dumps(add_menu_data, indent=2, default=str))
    logger.info("=" * 80)

    if not isinstance(add_menu_data, list) or not add_menu_data:
        raise ValueError("Add at least one item to your cart before ordering.")

    cart_items = []
    for row_index, item in enumerate(add_menu_data, start=1):
        if not isinstance(item, dict):
            continue
        menu_category = str(item.get("plugin-bdi-zkekarzt.menu_category") or "").strip()
        pizza_code = str(item.get("plugin-bdi-zkekarzt.menu") or "").strip()
        price = item.get("plugin-bdi-zkekarzt.price")
        quantity_value = item.get("plugin-bdi-zkekarzt.quantity")
        logger.info("CART ITEM %s", row_index)
        logger.info("Menu Category = %s", menu_category)
        logger.info("Menu = %s", pizza_code)
        logger.info("Price = %s", price)
        logger.info("Quantity = %s", quantity_value)
        if not pizza_code:
            raise ValueError("Cart item %d is missing a menu selection." % row_index)
        try:
            quantity = int(quantity_value if quantity_value not in (None, "") else 1)
        except (TypeError, ValueError):
            raise ValueError("Cart item %d has an invalid quantity." % row_index)
        if quantity < 1:
            raise ValueError("Cart item %d quantity must be at least 1." % row_index)
        cart_items.append({"pizza_code": pizza_code, "quantity": quantity, "row": row_index, "menu_category": menu_category})

    if not cart_items:
        raise ValueError("Add at least one item to your cart before ordering.")
    return cart_items
    
def run(job, *args, **kwargs):
    if PREREQ_IMPORT_ERROR is not None:
        raise Exception(
            "Missing required dependencies (%s). Before ordering, install the prerequisites on "
            "this CloudBolt server: `pip install usaddress` and `git clone "
            "https://github.com/gamagori/pizzapi.git` into /var/opt/cloudbolt/proserv/."
            % PREREQ_IMPORT_ERROR
        )
    # since "menu"/"quantity"/etc. live one-per-row inside the "add_menu" paneldynamic and CloudBolt's templating only resolves flat top-level values.
    cart_items = get_cart_items_from_form(job)

    zip_code = "{{ zip_code }}".strip()
    menu = "{{ menu }}".strip()
    price = "{{ price }}".strip()
    quantity_value = "{{ quantity }}".strip()
    menu_category = "{{ menu_category }}".strip()

    user = job.owner.user
    test_only = "{{ test_only }}" == "True"
    if test_only:
        set_progress("Only testing, will not order the pizza.")
    else:
        set_progress("This is not a test, the pizza will be ordered.")
    full_address = "{{ full_address }}".strip()
    phone = "{{ recipient_phone }}".strip()
    # .strip() then removes the leading/trailing whitespace/newlines.
    selected_store_id = """{{ store }}""".strip()
    if not full_address:
        raise ValueError("A delivery address is required.")
    if not phone:
        raise ValueError("A recipient phone number is required.")

    address = parse_address(full_address)
    customer = Customer(user.first_name,user.last_name,user.email,phone,)
    
    store = get_store(selected_store_id)
    store_details = get_store_details(store)
    logger.info("store_details = %s",store_details,)

    if store_details.get("IsOpen") is False:
        raise Exception("The selected Domino's store is currently closed.")

    if store_details.get("IsOnlineNow") is False:
        raise Exception("The selected Domino's store is currently unavailable for online ordering.")

    if store_details.get("AllowDeliveryOrders") is False:
        raise Exception("The selected Domino's store is not currently accepting delivery orders.")
        
    store_name = (store_details.get("StreetName") or store_details.get("AddressDescription") or store.id)
    set_progress("Using selected Domino's Store #%s: %s" % (store.id,store_name,))
    
    show_delivery_wait_times(store_details)
    set_progress("Constructing the order")
    
    # Use the live raw menu instead.
    order = create_order(store,customer,address,)

    for cart_item in cart_items:
        pizza_code = cart_item["pizza_code"]
        quantity = cart_item["quantity"]
        row = cart_item["row"]
        menu_category = cart_item.get("menu_category")

        # Regular menu item (Pizza, Sandwich, Wings, etc.).
        if pizza_code not in order.menu.variants:
            raise Exception(
                "Selected pizza '%s' (cart item %d) is no longer available at Domino's store %s. "
                "Refresh the order form and select an available pizza."
                % (pizza_code, row, store.id)
            )
        # set_progress("Adding %dx pizza (%s)." % (quantity, pizza_code))
        set_progress("Adding %dx %s (%s)." % (quantity, menu_category.lower(), pizza_code))
        order.add_item(pizza_code, qty=quantity)

    set_progress("Preparing payment information...")

    card = get_payment()

    try:
        if test_only:
            set_progress("Validating your order with Domino's...")
            result = order.pay_with(card)
        else:
            set_progress("Submitting your order to Domino's...")
            result = order.place(card)

    except Exception as exc:
        logger.exception("Domino's request failed.")

        error_message = str(exc)

        if "ServiceMethodNotAllowed" in error_message:
            raise Exception("Domino's could not authorize Delivery for the selected store and delivery address. Please verify the delivery address and try again.")

        if "PriceInformationRemoved" in error_message:
            raise Exception("One or more menu items are no longer available. Please refresh the menu and try again.")

        if "InvalidAddress" in error_message:
            raise Exception("Domino's could not validate the delivery address.")

        raise Exception("Domino's could not process the request.\n\n%s" % error_message)

    if not isinstance(result, dict):
        raise Exception("Domino's returned an unexpected response.")
        
    # Remove payment information before logging the response.
    order_result = result.get("Order")
    if isinstance(order_result, dict):
        order_result.pop("Payments", None)
        
    logger.info("result = %s",result,)
    status_items = result.get("StatusItems") or []
    if not status_items and isinstance(order_result, dict):
        status_items = order_result.get("StatusItems") or []

    if not status_items:
        raise Exception("Domino's response did not contain an order status.")

    status_codes = [str(item.get("Code", "")).upper() for item in status_items if isinstance(item, dict) and item.get("Code")]

    logger.info("Domino's order status codes: %s",status_codes,)

    if "SUCCESS" in status_codes:
        status = "SUCCESS"
    elif "FAILURE" in status_codes:
        status = "FAILURE"
    elif status_codes:
        status = status_codes[-1]
    else:
        raise Exception("Domino's returned an empty order status.")
        
    if status == "SUCCESS" and not test_only:
        tracking_phone = phone_number_to_int(phone)
        wait_for_order(tracking_phone)
        return status,"Delivered! Enjoy your pizza.","",
        
    if status == "SUCCESS" and test_only:
        return status,"Order validation completed successfully. No pizza was ordered.",""
    return status, "", ""
    
if __name__ == "__main__":
    import doctest
    doctest.testmod()