from flask import Flask, render_template, request, jsonify
import json
import time
import requests
from datetime import datetime
import logging

# Try to import ncclient, but don't fail if it's not available
try:
    from ncclient import manager
except ImportError:
    manager = None

# Suppress ncclient logging noise
logging.getLogger("ncclient").setLevel(logging.ERROR)

app = Flask(__name__)

# ODL Controller configuration
ODL_CONTROLLER = {
    'host': '192.168.162.3',
    'port': 8181,
    'username': 'admin',
    'password': 'admin'
}

# Initial router configs
configs = {
    "R1": {
        "hostname": "Router1",
        "interface": "GigabitEthernet0/0/0",
        "ipAddress": "192.168.162.2",
        "netmask": "255.255.255.0",
        "description": "Connection to ODL",
        "ospfEnabled": False,
        "ospfProcessId": 1,
        "ospfArea": 0
    },
    "R2": {
        "hostname": "Router2",
        "interface": "GigabitEthernet0/0/0",
        "ipAddress": "192.168.162.4",
        "netmask": "255.255.255.0",
        "description": "Connection to ODL",
        "ospfEnabled": False,
        "ospfProcessId": 1,
        "ospfArea": 0
    }
}

devices = [
    {"id": "R1", "name": "Router1", "ip": "192.168.162.2", "status": "connected"},
    {"id": "R2", "name": "Router2", "ip": "192.168.162.4", "status": "connected"},
    {"id": "ODL", "name": "ODL Controller", "ip": "192.168.162.3", "status": "active"}
]

def check_odl_status():
    """Check if ODL controller is active by connecting to RESTCONF API"""
    url = f"http://{ODL_CONTROLLER['host']}:{ODL_CONTROLLER['port']}/rests/data/network-topology:network-topology"
    
    try:
        response = requests.get(
            url,
            auth=(ODL_CONTROLLER['username'], ODL_CONTROLLER['password']),
            timeout=5
        )
        
        if response.status_code == 200:
            return {"status": "active", "message": "ODL Controller is online"}
        elif response.status_code == 401:
            return {"status": "offline", "message": "ODL Controller authentication failed"}
        else:
            return {"status": "offline", "message": f"ODL Controller returned status {response.status_code}"}
            
    except requests.exceptions.ConnectionError:
        return {"status": "offline", "message": "Cannot connect to ODL Controller"}
    except requests.exceptions.Timeout:
        return {"status": "offline", "message": "ODL Controller connection timeout"}
    except Exception as e:
        return {"status": "offline", "message": f"Error checking ODL status: {str(e)}"}

def get_netconf_topology():
    """Get all NETCONF nodes from ODL topology"""
    url = f"http://{ODL_CONTROLLER['host']}:{ODL_CONTROLLER['port']}/rests/data/network-topology:network-topology/topology=topology-netconf"
    
    try:
        response = requests.get(
            url,
            auth=(ODL_CONTROLLER['username'], ODL_CONTROLLER['password']),
            timeout=5
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except Exception as e:
        print(f"Error getting NETCONF topology: {str(e)}")
        return None

def check_router_status(router_id, router_ip):
    """Check if a router is alive by connecting directly via NETCONF"""
    
    if manager is None:
        return {
            "status": "disconnected",
            "message": "ncclient not available - cannot check router status"
        }
    
    try:
        # Try to connect directly to the router via NETCONF
        with manager.connect(
            host=router_ip,
            port=830,
            username="admin",
            password="admin",
            hostkey_verify=False,
            timeout=5,
            allow_agent=False,
            look_for_keys=False
        ) as m:
            # If connection succeeds, router is alive
            return {
                "status": "connected",
                "message": f"{router_id} ({router_ip}) is connected and responding to NETCONF"
            }
    
    except Exception as e:
        return {
            "status": "disconnected",
            "message": f"{router_id} ({router_ip}) is offline or unreachable"
        }

def update_devices_status():
    """Update device status based on ODL controller health"""
    odl_status = check_odl_status()
    
    # Update ODL device status
    for device in devices:
        if device["id"] == "ODL":
            device["status"] = "active" if odl_status["status"] == "active" else "offline"
        # Check router status through ODL
        elif device["id"] in ["R1", "R2"]:
            router_status = check_router_status(device["id"], device["ip"])
            device["status"] = router_status["status"]

def generate_yang_config(router):
    config = configs[router]
    ospf_bool = "true" if config['ospfEnabled'] else "false"
    return f"""
    module cisco-ios-xe-native {{
  namespace "http://cisco.com/ns/yang/cisco-ios-xe-native";
  prefix ios;

  rpc config-interfaces {{
    input {{
      leaf interface-name {{
        type string;
        default "{config['interface']}";
      }}
      leaf ip-address {{
        type string;
        default "{config['ipAddress']}";
      }}
      leaf subnet-mask {{
        type string;
        default "{config['netmask']}";
      }}
      leaf description {{
        type string;
        default "{config['description']}";
      }}
    }}
  }}

  rpc config-ospf {{
    input {{
      leaf process-id {{
        type uint16;
        default {config['ospfProcessId']};
      }}
      leaf area-id {{
        type uint32;
        default {config['ospfArea']};
      }}
      leaf enabled {{
        type boolean;
        default {ospf_bool};
      }}
    }}
  }}
}}
"""

def generate_restconf_payload(router):
    config = configs[router]
    payload = {
        "native": {
            "hostname": config["hostname"],
            "interface": {
                "GigabitEthernet": [
                    {
                        "name": config["interface"],
                        "description": config["description"],
                        "ip": {
                            "address": {
                                "primary": {
                                    "address": config["ipAddress"],
                                    "mask": config["netmask"]
                                }
                            }
                        }
                    }
                ]
            }
        }
    }
    
    if config["ospfEnabled"]:
        payload["native"]["router"] = {
            "ospf": [
                {
                    "id": config["ospfProcessId"],
                    "area": [
                        {
                            "area-id": config["ospfArea"],
                            "network": [
                                {
                                    "address": config["ipAddress"],
                                    "mask": config["netmask"]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    return payload

@app.route("/")
def index():
    update_devices_status()
    return render_template("index.html", configs=configs, devices=devices)

@app.route("/api/config/<router>")
def get_config(router):
    if router in configs:
        return jsonify(configs[router])
    return jsonify({"error": "Router not found"}), 404

@app.route("/api/odl/status")
def get_odl_status():
    """API endpoint to check ODL controller status"""
    status = check_odl_status()
    return jsonify(status)

@app.route("/api/router/status/<router_id>")
def get_router_status(router_id):
    """API endpoint to check a specific router status"""
    router = next((d for d in devices if d["id"] == router_id), None)
    if not router:
        return jsonify({"error": "Router not found"}), 404
    
    status = check_router_status(router_id, router["ip"])
    return jsonify(status)

@app.route("/api/all-devices/status")
def get_all_devices_status():
    """API endpoint to check all devices status"""
    update_devices_status()
    return jsonify(devices)

@app.route("/api/debug/topology")
def debug_topology():
    """Debug endpoint to see what nodes are registered in ODL"""
    topology = get_netconf_topology()
    if topology:
        nodes = []
        if "topology" in topology:
            for topo in topology["topology"]:
                if "node" in topo:
                    for node in topo["node"]:
                        nodes.append({
                            "node-id": node.get("node-id"),
                            "connection-status": node.get("netconf-node-topology:connection-status"),
                            "host": node.get("netconf-node-topology:host"),
                            "port": node.get("netconf-node-topology:port")
                        })
        return jsonify({"nodes": nodes})
    return jsonify({"error": "Failed to retrieve topology"}), 500

@app.route("/api/update_config", methods=["POST"])
def update_config():
    data = request.json
    router = data.get("router")
    field = data.get("field")
    value = data.get("value")
    
    if router in configs and field in configs[router]:
        if field in ["ospfEnabled"]:
            configs[router][field] = value == "true" or value is True
        elif field in ["ospfProcessId", "ospfArea"]:
            configs[router][field] = int(value)
        else:
            configs[router][field] = value
        return jsonify({"success": True, "config": configs[router]})
    return jsonify({"success": False, "error": "Invalid router or field"}), 400

@app.route("/api/deploy/<router>", methods=["POST"])
def deploy(router):
    # Check ODL status before deployment
    odl_status = check_odl_status()
    if odl_status["status"] != "active":
        return jsonify({
            "type": "error",
            "message": f"Cannot deploy: {odl_status['message']}"
        }), 503
    
    time.sleep(2)
    return jsonify({
        "type": "success",
        "message": f"Configuration deployed successfully to {router}"
    })

@app.route("/api/sync/<router>", methods=["POST"])
def sync(router):
    # Check ODL status before sync
    odl_status = check_odl_status()
    if odl_status["status"] != "active":
        return jsonify({
            "type": "error",
            "message": f"Cannot sync: {odl_status['message']}"
        }), 503
    
    time.sleep(1.5)
    return jsonify({
        "type": "success",
        "message": f"Synced configurations from {router}"
    })

@app.route("/api/yang/<router>")
def yang(router):
    return jsonify({"yang": generate_yang_config(router)})

@app.route("/api/restconf/<router>")
def restconf(router):
    return jsonify({
        "endpoint": f"http://{ODL_CONTROLLER['host']}:{ODL_CONTROLLER['port']}/rests/data/network-topology:network-topology/topology/topology-netconf/node/{router}",
        "payload": generate_restconf_payload(router)
    })

@app.route("/api/curl/<router>")
def curl_command(router):
    payload = generate_restconf_payload(router)
    curl_cmd = f"""curl -X PUT \\
  -H "Content-Type: application/json" \\
  -u {ODL_CONTROLLER['username']}:{ODL_CONTROLLER['password']} \\
  -d '{json.dumps(payload, indent=2)}' \\
  http://{ODL_CONTROLLER['host']}:{ODL_CONTROLLER['port']}/rests/data/network-topology:network-topology/topology/topology-netconf/node/{router}"""
    return jsonify({"curl": curl_cmd})

if __name__ == "__main__":
    app.run(debug=True)