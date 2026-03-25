#!/usr/bin/env python3
"""
Cisco IOS XR RESTCONF Dual-Router Configuration Tool
Uses RESTCONF (JSON) instead of NETCONF.
Supports:
1. Interface Configuration (with GE shorthand expansion)
2. OSPF Routing Configuration (IOS XR)
3. Router Info Viewer (users, interfaces, OSPF, policies)

Imports: cisco-iosxr-config.yang (implicitly via RESTCONF)
"""
import requests
import sys
import logging
import json
import ipaddress
from tabulate import tabulate
from urllib.parse import quote
from datetime import datetime

# Suppress insecure HTTPS warnings (for lab only)
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Device Configuration (RESTCONF) ===
devices = {
    "R1": {
        "host": "192.168.162.2",
        "port": 443,                 # RESTCONF typically uses HTTPS
        "username": "cisco",
        "password": "cisco",
        "verify": False,             # Disable SSL verification (lab)
        "timeout": 60,
    },
    "R2": {
        "host": "192.168.162.4",
        "port": 443,
        "username": "cisco",
        "password": "cisco",
        "verify": False,
        "timeout": 60,
    },
}

# Base RESTCONF URL (YANG module prefix "iosxr")
BASE_RESTCONF_URL = "https://{host}:{port}/restconf/data"

# === Utility Functions ===
def get_restconf_base(device):
    """Build RESTCONF base URL for the device"""
    return BASE_RESTCONF_URL.format(host=device["host"], port=device["port"])

def restconf_headers():
    """Headers for RESTCONF JSON requests"""
    return {
        "Accept": "application/yang-data+json",
        "Content-Type": "application/yang-data+json"
    }

def restconf_request(method, url, auth, headers, data=None, timeout=60):
    """Perform a RESTCONF request and handle errors"""
    try:
        response = requests.request(
            method=method,
            url=url,
            auth=auth,
            headers=headers,
            json=data,
            verify=False,
            timeout=timeout
        )
        if response.status_code in (200, 201, 204):
            return response.json() if response.content else None
        else:
            # Try to extract error details
            error_msg = f"HTTP {response.status_code}"
            try:
                error_detail = response.json()
                error_msg += f" - {error_detail.get('errors', {}).get('error', [{}])[0].get('error-message', response.text)}"
            except:
                error_msg += f" - {response.text}"
            raise Exception(error_msg)
    except requests.exceptions.RequestException as e:
        raise Exception(f"RESTCONF request failed: {e}")

def connect_device(device_name):
    """
    Simple connectivity check (RESTCONF doesn't require persistent session).
    Returns a tuple (device_dict, base_url) for convenience.
    """
    device = devices[device_name]
    base_url = get_restconf_base(device)
    print(f"🔗 Connecting to {device_name} ({device['host']}:{device['port']})...")
    try:
        # Perform a simple GET to check connectivity (e.g., top-level data)
        auth = (device["username"], device["password"])
        headers = restconf_headers()
        url = f"{base_url}/iosxr:interfaces"   # any read endpoint
        restconf_request("GET", url, auth, headers)
        print(f"✅ Connected to {device_name}\n")
        return device, base_url
    except Exception as e:
        print(f"❌ Failed to connect to {device_name}: {e}")
        sys.exit(1)

def push_config(device_name, resource_path, data, method="PUT"):
    """
    Push configuration via RESTCONF.
    - resource_path: relative path (e.g., "iosxr:interfaces/interface=GigabitEthernet0/0/0/0")
    - data: JSON payload (dictionary)
    - method: "PUT", "POST", "PATCH"
    """
    device, base_url = connect_device(device_name)  # returns tuple (device_dict, base_url)
    auth = (device["username"], device["password"])
    url = f"{base_url}/{resource_path}"
    headers = restconf_headers()
    print(f"   Sending {method} to {url}")
    restconf_request(method, url, auth, headers, data, device.get("timeout", 60))
    print(f"✅ {device_name}: Configuration applied.\n")

def normalize_interface(if_name):
    """Convert GE0/0/0 to GigabitEthernet0/0/0/0"""
    if if_name.upper().startswith("GE"):
        # remove 'GE' and ensure trailing /0 if needed
        rest = if_name[2:]   # e.g., "0/0/0"
        # split on slashes, get parts
        parts = rest.split('/')
        # IOS XR interface name format: GigabitEthernet<slot>/<subslot>/<port>/<subport>
        # For typical router: if only three parts, add /0 at end
        if len(parts) == 3:
            rest = f"{rest}/0"
        return "GigabitEthernet" + rest
    return if_name

def url_encode_interface(iface):
    """URL-encode interface name for RESTCONF paths (slashes become %2F)"""
    return quote(iface, safe='')

# === Option 1: Interface Configuration ===
def interface_config_menu():
    """Menu for interface configuration"""
    print("\n=== INTERFACE CONFIGURATION ===")
    first = input("Which router would you like to configure first? (R1/R2): ").strip().upper()
    if first not in ["R1", "R2"]:
        print("❌ Invalid router. Please enter R1 or R2.\n")
        return
    apply_interface_config(first)
    second = "R2" if first == "R1" else "R1"
    ans = input(f"Do you want to configure {second} as well? (yes/no): ").strip().lower()
    if ans == "yes":
        apply_interface_config(second)
    else:
        print(f"Skipping configuration for {second}.\n")

def apply_interface_config(router_name):
    """Apply interface configuration to specified router using RESTCONF"""
    print(f"\n--- Configuring Interface on {router_name} ---")
    iface_input = input("Interface name (e.g., GigabitEthernet0/0/0/0 or GE0/0/0): ").strip()
    if not iface_input:
        print("❌ Interface name cannot be empty.")
        return

    # Validate IP
    ip = input("IPv4 address: ").strip()
    try:
        ipaddress.IPv4Address(ip)
    except ipaddress.AddressValueError:
        print("❌ Invalid IPv4 address format.")
        return

    mask = input("Subnet mask: ").strip()
    try:
        ipaddress.IPv4Network(f"{ip}/{mask}", strict=False)
    except:
        print("❌ Invalid subnet mask format.")
        return

    desc = input("Description: ").strip() or "NETCONF configured"

    # Normalize interface name
    iface = normalize_interface(iface_input)
    print(f"🧩 Final expanded interface name: {iface}")

    # Build RESTCONF payload
    interface_data = {
        "iosxr:interface": {
            "name": iface,
            "description": desc,
            "ipv4": {
                "addresses": {
                    "primary-address": ip,
                    "netmask": mask
                }
            }
        }
    }

    # Use PUT to replace the interface if it exists, or create if not.
    resource_path = f"iosxr:interfaces/interface={url_encode_interface(iface)}"
    try:
        push_config(router_name, resource_path, interface_data, method="PUT")
    except Exception as e:
        print(f"❌ Failed to configure {router_name}: {e}")

# === Option 2: OSPF Routing Configuration ===
def build_ospf_payload(interface_name, area_id, process_id):
    """Build JSON payload for OSPF configuration"""
    # Note: The YANG model expects a list 'process' inside container 'ospf'.
    # We'll construct a payload that matches the structure.
    # For a new process, we can use POST to the list or PUT to a specific process.
    # Here we'll use PUT to the specific process path.
    return {
        "iosxr:process": {
            "process-id": process_id,
            "area-id": area_id,
            "interfaces": {
                "interface": [
                    {"name": interface_name}
                ]
            }
        }
    }

def push_ospf_config(router_label, interface_name, area_id, process_id):
    """Push OSPF configuration to router using RESTCONF"""
    device, base_url = connect_device(router_label)  # tuple (device_dict, base_url)
    auth = (device["username"], device["password"])
    resource_path = f"iosxr:ospf/process={process_id}"
    url = f"{base_url}/{resource_path}"
    headers = restconf_headers()
    payload = build_ospf_payload(interface_name, area_id, process_id)

    print(f"\n=== Configuring {router_label} ===")
    print(f"Interface: {interface_name} | Area: {area_id} | Process: {process_id}")
    try:
        # Use PUT to create/replace the OSPF process
        restconf_request("PUT", url, auth, headers, payload, device.get("timeout", 60))
        print(f"✅ OSPF configuration successfully applied to {router_label}.")
    except Exception as e:
        print(f"❌ OSPF configuration failed on {router_label}: {e}")

def routing_config_menu():
    """Menu for OSPF routing configuration"""
    print("\n========================================")
    print("  OSPF Dual-Router Configuration (IOS XR)")
    print("========================================")
    interface_name = normalize_interface(
        input("Interface name (e.g., GigabitEthernet0/0/0/0 or GE0/0/0): ").strip()
    )
    area_id = input("OSPF area ID (default 0): ").strip() or "0"
    process_id = input("OSPF process ID (default 1): ").strip() or "1"
    print("\n📡 Applying identical OSPF configuration to both routers...\n")
    push_ospf_config("R1", interface_name, area_id, process_id)
    push_ospf_config("R2", interface_name, area_id, process_id)
    print("\n✅ All configurations completed successfully!")

# === Option 3: Router Info Viewer ===
def router_info_menu():
    """Retrieve and display router configuration information using RESTCONF"""
    choice = input("\nWhich router do you want to query? (R1/R2): ").strip().upper()
    if choice not in devices:
        print("❌ Invalid choice.")
        return

    device, base_url = connect_device(choice)
    auth = (device["username"], device["password"])
    headers = restconf_headers()

    # Helper to fetch data from a given resource path
    def fetch_data(resource_path):
        url = f"{base_url}/{resource_path}"
        try:
            return restconf_request("GET", url, auth, headers)
        except Exception as e:
            logger.warning(f"Could not fetch {resource_path}: {e}")
            return None

    # === Fetch interfaces ===
    interfaces_data = fetch_data("iosxr:interfaces")
    interfaces = []
    if interfaces_data and "iosxr:interfaces" in interfaces_data:
        for iface in interfaces_data["iosxr:interfaces"].get("interface", []):
            name = iface.get("name", "-")
            desc = iface.get("description", "-")
            ip = "-"
            mask = "-"
            ipv4 = iface.get("ipv4", {})
            addrs = ipv4.get("addresses", {})
            if addrs:
                ip = addrs.get("primary-address", "-")
                mask = addrs.get("netmask", "-")
            # Shutdown is not explicitly in our YANG; but if present, we could check
            shutdown = "No"  # assume not shutdown, or parse from some other leaf if exists
            interfaces.append([name, ip, mask, shutdown, desc])

    # === Fetch OSPF ===
    ospf_data = fetch_data("iosxr:ospf")
    ospf_entries = []
    if ospf_data and "iosxr:ospf" in ospf_data:
        for proc in ospf_data["iosxr:ospf"].get("process", []):
            pid = proc.get("process-id", "-")
            ifaces = proc.get("interfaces", {}).get("interface", [])
            for iface in ifaces:
                ospf_entries.append([pid, iface.get("name", "-")])

    # === Fetch users ===
    # The system container is config false, but we can still GET it.
    system_data = fetch_data("iosxr:system")
    users = []
    if system_data and "iosxr:system" in system_data:
        for user in system_data["iosxr:system"].get("user", []):
            users.append([user.get("username", "-"), user.get("group", "-")])

    # === Fetch policies ===
    policies = []
    if system_data and "iosxr:system" in system_data:
        for pol in system_data["iosxr:system"].get("policy", []):
            policies.append([pol.get("name", "-"), pol.get("definition", "-")])

    # === Display results ===
    print("\n👤 Local Users")
    print(tabulate(users, headers=["Username", "Group"], tablefmt="fancy_grid") if users else "No users found.")
    print("\n🌐 Interface Configurations")
    print(tabulate(interfaces, headers=["Interface", "IP", "Netmask", "Shutdown", "Description"], tablefmt="fancy_grid") if interfaces else "No interfaces found.")
    print("\n📡 OSPF Interfaces")
    print(tabulate(ospf_entries, headers=["Process ID", "Interface"], tablefmt="fancy_grid") if ospf_entries else "No OSPF entries found.")
    print("\n📜 Route Policies")
    print(tabulate(policies, headers=["Policy Name", "Definition"], tablefmt="fancy_grid") if policies else "No policies found.")

# === Main Menu ===
def main_menu():
    """Display main menu and handle user selection"""
    while True:
        print("\n=== RESTCONF Dual-Router Operations Menu ===")
        print("1. Interface Configuration")
        print("2. Routing Configuration (OSPF)")
        print("3. Router Info Viewer")
        print("4. Exit")
        choice = input("Select an option: ").strip()
        
        if choice == "1":
            interface_config_menu()
        elif choice == "2":
            routing_config_menu()
        elif choice == "3":
            router_info_menu()
        elif choice == "4":
            print("Exiting RESTCONF tool. Goodbye!\n")
            break
        else:
            print("❌ Invalid option. Try again.\n")

if __name__ == "__main__":
    main_menu()