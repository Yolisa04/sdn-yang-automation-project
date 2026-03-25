#!/usr/bin/env python3
"""
Cisco IOS XR NETCONF Dual-Router Configuration Tool
Supports:
1. Interface Configuration (with GE shorthand expansion)
2. OSPF Routing Configuration (IOS XR)
3. Router Info Viewer (users, interfaces, OSPF, policies)

Imports: cisco-iosxr-config.yang and config-template.xml
"""
from ncclient import manager
from ncclient.operations.rpc import RPCError
import sys
import logging
import xml.etree.ElementTree as ET
from tabulate import tabulate

logging.basicConfig(level=logging.INFO)

# === Device Configuration ===
devices = {
    "R1": {
        "host": "192.168.162.2",
        "port": 830,
        "username": "cisco",
        "password": "cisco",
        "hostkey_verify": False,
        "device_params": {"name": "iosxr"},
        "allow_agent": False,
        "look_for_keys": False,
        "timeout": 60,
    },
    "R2": {
        "host": "192.168.162.4",
        "port": 830,
        "username": "cisco",
        "password": "cisco",
        "hostkey_verify": False,
        "device_params": {"name": "iosxr"},
        "allow_agent": False,
        "look_for_keys": False,
        "timeout": 60,
    },
}

# === YANG Namespaces ===
NS = {
    "base": "urn:ietf:params:xml:ns:netconf:base:1.0",
    "aaa_locald": "http://cisco.com/ns/yang/Cisco-IOS-XR-aaa-locald-cfg",
    "aaa_admin": "http://cisco.com/ns/yang/Cisco-IOS-XR-aaa-locald-admin-cfg",
    "ifmgr": "http://cisco.com/ns/yang/Cisco-IOS-XR-ifmgr-cfg",
    "ipv4": "http://cisco.com/ns/yang/Cisco-IOS-XR-ipv4-io-cfg",
    "ospf": "http://cisco.com/ns/yang/Cisco-IOS-XR-ipv4-ospf-cfg",
    "policy": "http://cisco.com/ns/yang/Cisco-IOS-XR-policy-repository-cfg",
}

# === Utility Functions ===
def connect_device(name):
    """Connect to a device and return manager object"""
    print(f"🔗 Connecting to {name} ({devices[name]['host']})...")
    try:
        conn = manager.connect(**devices[name])
        print(f"✅ Connected to {name}\n")
        return conn
    except Exception as e:
        print(f"❌ Failed to connect to {name}: {e}")
        sys.exit(1)

def push_config(device_name, config_xml):
    """Push configuration to device via NETCONF"""
    with connect_device(device_name) as m:
        m.edit_config(target="candidate", config=config_xml)
        m.commit()
        print(f"✅ {device_name}: Configuration committed.\n")

def normalize_interface(if_name):
    """Convert GE0/0/0 to GigabitEthernet0/0/0/0"""
    if if_name.upper().startswith("GE"):
        return "GigabitEthernet" + if_name[2:] + "/0"
    return if_name

def extract_error_message(xml_element):
    """Extract readable error message from NETCONF RPC-REPLY"""
    try:
        xml_str = ET.tostring(xml_element, encoding='unicode')
        print(f"\n   Full RPC Response:\n{xml_str}\n")
        root = ET.fromstring(xml_str)
        errors = []
        for elem in root.iter():
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if tag == 'error-message' and elem.text:
                errors.append(f"Message: {elem.text}")
            elif tag == 'error-severity' and elem.text:
                errors.append(f"Severity: {elem.text}")
            elif tag == 'error-type' and elem.text:
                errors.append(f"Type: {elem.text}")
            elif tag == 'error-app-tag' and elem.text:
                errors.append(f"App Tag: {elem.text}")
            elif tag == 'rpc-error':
                errors.append("RPC Error detected")
        return "\n   ".join(errors) if errors else "No error details found."
    except Exception as e:
        return f"Could not parse error: {str(e)}"

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
    """Apply interface configuration to specified router"""
    print(f"\n--- Configuring Interface on {router_name} ---")
    iface_input = input("Interface name (e.g., GigabitEthernet0/0/0/0 or GE0/0/0): ").strip()
    
    if iface_input.upper().startswith("GE"):
        iface_input = iface_input.upper().replace("GE", "")
        iface_input = iface_input.replace("//", "/").strip("/")
        iface = f"GigabitEthernet{iface_input}/0"
    else:
        iface = iface_input
    
    ip = input("IPv4 address: ").strip()
    mask = input("Subnet mask: ").strip()
    desc = input("Description: ").strip() or "NETCONF configured"
    
    config = f"""<config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <interface-configurations xmlns="http://cisco.com/ns/yang/Cisco-IOS-XR-ifmgr-cfg">
    <interface-configuration>
      <active>act</active>
      <interface-name>{iface}</interface-name>
      <description>{desc}</description>
      <ipv4-network xmlns="http://cisco.com/ns/yang/Cisco-IOS-XR-ipv4-io-cfg">
        <addresses>
          <primary>
            <address>{ip}</address>
            <netmask>{mask}</netmask>
          </primary>
        </addresses>
      </ipv4-network>
    </interface-configuration>
  </interface-configurations>
</config>"""
    
    print(f"🧩 Final expanded interface name: {iface}")
    push_config(router_name, config)

# === Option 2: OSPF Routing Configuration ===
def build_ospf_config(interface_name, area_id, process_id):
    """Build OSPF configuration XML"""
    return f"""<config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <ospf xmlns="http://cisco.com/ns/yang/Cisco-IOS-XR-ipv4-ospf-cfg">
    <processes>
      <process>
        <process-name>{process_id}</process-name>
        <default-vrf>
          <area-addresses>
            <area-area-id>
              <area-id>{area_id}</area-id>
              <running/>
              <name-scopes>
                <name-scope>
                  <interface-name>{interface_name}</interface-name>
                  <running/>
                </name-scope>
              </name-scopes>
            </area-area-id>
          </area-addresses>
        </default-vrf>
        <start/>
      </process>
    </processes>
  </ospf>
</config>"""

def push_ospf_config(router_label, interface_name, area_id, process_id):
    """Push OSPF configuration to router"""
    device = devices[router_label]
    print(f"\n=== Configuring {router_label} ===")
    print(f"Interface: {interface_name} | Area: {area_id} | Process: {process_id}")
    try:
        with manager.connect(**device) as m:
            print("✅ Connected to device.")
            config_xml = build_ospf_config(interface_name, area_id, process_id)
            try:
                m.edit_config(target="candidate", config=config_xml)
                m.commit()
                print(f"✅ OSPF configuration successfully applied to {router_label}.")
            except RPCError as e:
                print(f"❌ NETCONF RPC Error on {router_label}:")
                error_msg = extract_error_message(e.xml)
                print(f"   {error_msg}")
                print(f"\n   Debug Info:\n   - Interface: {interface_name}\n   - Area: {area_id}\n   - Process: {process_id}")
    except Exception as e:
        print(f"❌ Connection error on {router_label}: {e}")

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
    """Retrieve and display router configuration information"""
    choice = input("\nWhich router do you want to query? (R1/R2): ").strip().upper()
    if choice not in devices:
        print("❌ Invalid choice.")
        return
    with connect_device(choice) as m:
        xml_data = m.get_config(source="running").data_xml
    root = ET.fromstring(xml_data)
    
    # === Users ===
    users = []
    for ns_key in ["aaa_locald", "aaa_admin"]:
        for user in root.findall(f".//{{{NS[ns_key]}}}username"):
            name = user.findtext(f"{{{NS[ns_key]}}}name") or "-"
            group_elem = user.find(f".//{{{NS[ns_key]}}}usergroup-under-username")
            group = group_elem.findtext(f"{{{NS[ns_key]}}}name") if group_elem is not None else "-"
            secret = user.findtext(f"{{{NS[ns_key]}}}secret") or "-"
            users.append([name, group, secret])
    
    # === Interfaces ===
    interfaces = []
    for iface in root.findall(f".//{{{NS['ifmgr']}}}interface-configuration"):
        name = iface.findtext(f"{{{NS['ifmgr']}}}interface-name") or "-"
        desc = iface.findtext(f"{{{NS['ifmgr']}}}description") or "-"
        shutdown = "Yes" if iface.find(f"{{{NS['ifmgr']}}}shutdown") is not None else "No"
        ipv4_block = iface.find(f".//{{{NS['ipv4']}}}primary")
        ip = ipv4_block.findtext(f"{{{NS['ipv4']}}}address") if ipv4_block is not None else "unassigned"
        mask = ipv4_block.findtext(f"{{{NS['ipv4']}}}netmask") if ipv4_block is not None else "-"
        interfaces.append([name, ip, mask, shutdown, desc])
    
    # === OSPF ===
    ospf_entries = []
    for proc in root.findall(f".//{{{NS['ospf']}}}process"):
        pid = proc.findtext(f"{{{NS['ospf']}}}process-name") or "-"
        for iface in proc.findall(f".//{{{NS['ospf']}}}interface-name"):
            ospf_entries.append([pid, iface.text])
    
    # === Route Policies ===
    policies = []
    for policy in root.findall(f".//{{{NS['policy']}}}route-policy"):
        name = policy.findtext(f"{{{NS['policy']}}}route-policy-name") or "-"
        body = policy.findtext(f"{{{NS['policy']}}}rpl-route-policy") or "-"
        policies.append([name, body.strip() if body else "-"])
    
    print("\n👤 Local Users")
    print(tabulate(users, headers=["Username", "Group", "Secret"], tablefmt="fancy_grid") if users else "No users found.")
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
        print("\n=== NETCONF Dual-Router Operations Menu ===")
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
            print("Exiting NETCONF tool. Goodbye!\n")
            break
        else:
            print("❌ Invalid option. Try again.\n")

if __name__ == "__main__":
    main_menu()