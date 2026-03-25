#!/usr/bin/env python3
"""
Cisco IOS XR Restconf Dual-Router Configuration Tool (GUI)
PyQt5-based interface for interface, OSPF, and router info management
"""

import sys
import xml.etree.ElementTree as ET
from ncclient import manager
from ncclient.operations.rpc import RPCError
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QTabWidget, QLabel, QLineEdit, QPushButton, QComboBox, QTableWidget,
    QTableWidgetItem, QTextEdit, QMessageBox, QGroupBox, QFormLayout,
    QProgressBar
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor
from tabulate import tabulate

# === Device Configuration ===
DEVICES = {
    "R1": {
        "host": "192.168.162.2", "port": 830,
        "username": "cisco", "password": "cisco",
        "hostkey_verify": False, "device_params": {"name": "iosxr"},
        "allow_agent": False, "look_for_keys": False, "timeout": 60,
    },
    "R2": {
        "host": "192.168.162.4", "port": 830,
        "username": "cisco", "password": "cisco",
        "hostkey_verify": False, "device_params": {"name": "iosxr"},
        "allow_agent": False, "look_for_keys": False, "timeout": 60,
    },
}

NS = {
    "base": "urn:ietf:params:xml:ns:netconf:base:1.0",
    "aaa_locald": "http://cisco.com/ns/yang/Cisco-IOS-XR-aaa-locald-cfg",
    "ifmgr": "http://cisco.com/ns/yang/Cisco-IOS-XR-ifmgr-cfg",
    "ipv4": "http://cisco.com/ns/yang/Cisco-IOS-XR-ipv4-io-cfg",
    "ospf": "http://cisco.com/ns/yang/Cisco-IOS-XR-ipv4-ospf-cfg",
}

# === Worker Thread ===
class NetconfWorker(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    success = pyqtSignal(str)
    data_ready = pyqtSignal(dict)

    def __init__(self, operation, device_name, **kwargs):
        super().__init__()
        self.operation = operation
        self.device_name = device_name
        self.kwargs = kwargs

    def run(self):
        try:
            with manager.connect(**DEVICES[self.device_name]) as m:
                if self.operation == "interface_config":
                    self.configure_interface(m)
                elif self.operation == "ospf_config":
                    self.configure_ospf(m)
                elif self.operation == "get_info":
                    self.get_device_info(m)
                self.success.emit("✅ Operation completed successfully!")
        except RPCError as e:
            self.error.emit(f"❌ NETCONF Error: {str(e)[:200]}")
        except Exception as e:
            self.error.emit(f"❌ Error: {str(e)}")
        finally:
            self.finished.emit()

    def configure_interface(self, m):
        iface = self.kwargs['interface']
        ip = self.kwargs['ip']
        mask = self.kwargs['mask']
        desc = self.kwargs['description']

        config = f"""
        <config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
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
        </config>
        """
        m.edit_config(target="candidate", config=config)
        m.commit()

    def configure_ospf(self, m):
        iface = self.kwargs['interface']
        area = self.kwargs['area']
        process = self.kwargs['process']

        config = f"""<config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <ospf xmlns="http://cisco.com/ns/yang/Cisco-IOS-XR-ipv4-ospf-cfg">
    <processes>
      <process>
        <process-name>{process}</process-name>
        <default-vrf>
          <area-addresses>
            <area-area-id>
              <area-id>{area}</area-id>
              <running/>
              <name-scopes>
                <name-scope>
                  <interface-name>{iface}</interface-name>
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
        m.edit_config(target="candidate", config=config)
        m.commit()

    def get_device_info(self, m):
        xml_data = m.get_config(source="running").data_xml
        root = ET.fromstring(xml_data)

        interfaces = []
        for iface in root.findall(f".//{{{NS['ifmgr']}}}interface-configuration"):
            name = iface.findtext(f"{{{NS['ifmgr']}}}interface-name") or "-"
            desc = iface.findtext(f"{{{NS['ifmgr']}}}description") or "-"
            shutdown = "Yes" if iface.find(f"{{{NS['ifmgr']}}}shutdown") is not None else "No"
            ipv4_block = iface.find(f".//{{{NS['ipv4']}}}primary")
            ip = ipv4_block.findtext(f"{{{NS['ipv4']}}}address") if ipv4_block is not None else "unassigned"
            mask = ipv4_block.findtext(f"{{{NS['ipv4']}}}netmask") if ipv4_block is not None else "-"
            interfaces.append({"name": name, "ip": ip, "mask": mask, "shutdown": shutdown, "desc": desc})

        ospf_entries = []
        for proc in root.findall(f".//{{{NS['ospf']}}}process"):
            pid = proc.findtext(f"{{{NS['ospf']}}}process-name") or "-"
            for iface_elem in proc.findall(f".//{{{NS['ospf']}}}interface-name"):
                ospf_entries.append({"process": pid, "interface": iface_elem.text})

        self.data_ready.emit({"interfaces": interfaces, "ospf": ospf_entries})

# === Main GUI Class ===
class NetconfGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cisco IOS XR NETCONF Configuration Tool")
        self.setGeometry(100, 100, 1100, 750)
        self.worker = None
        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout()

        title = QLabel("🔧 Cisco IOS XR NETCONF Configuration Manager")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        main_layout.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self.create_interface_tab(), "Interface Config")
        tabs.addTab(self.create_ospf_tab(), "OSPF Config")
        tabs.addTab(self.create_info_viewer_tab(), "Router Info")
        main_layout.addWidget(tabs)

        central_widget.setLayout(main_layout)

    # === Interface Configuration Tab ===
    def create_interface_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()

        form_group = QGroupBox("Interface Configuration")
        form_layout = QFormLayout()

        self.iface_router = QComboBox()
        self.iface_router.addItems(["R1", "R2"])
        form_layout.addRow("Router:", self.iface_router)

        self.iface_name = QLineEdit()
        self.iface_name.setPlaceholderText("e.g., GigabitEthernet0/0/0/0 or GE0/0/0")
        form_layout.addRow("Interface Name:", self.iface_name)

        self.iface_ip = QLineEdit()
        self.iface_ip.setPlaceholderText("e.g., 192.168.1.1")
        form_layout.addRow("IPv4 Address:", self.iface_ip)

        self.iface_mask = QLineEdit()
        self.iface_mask.setPlaceholderText("e.g., 255.255.255.0")
        form_layout.addRow("Subnet Mask:", self.iface_mask)

        self.iface_desc = QLineEdit()
        self.iface_desc.setText("NETCONF configured")
        form_layout.addRow("Description:", self.iface_desc)

        form_group.setLayout(form_layout)
        layout.addWidget(form_group)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        apply_btn = QPushButton("✅ Apply Configuration")
        apply_btn.clicked.connect(self.apply_interface_config)
        btn_layout.addWidget(apply_btn)
        layout.addLayout(btn_layout)

        self.iface_status = QTextEdit()
        self.iface_status.setReadOnly(True)
        self.iface_status.setMaximumHeight(150)
        layout.addWidget(QLabel("Status:"))
        layout.addWidget(self.iface_status)

        self.iface_progress = QProgressBar()
        self.iface_progress.setVisible(False)
        layout.addWidget(self.iface_progress)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def apply_interface_config(self):
        router = self.iface_router.currentText()
        iface_input = self.iface_name.text().strip()
        ip = self.iface_ip.text().strip()
        mask = self.iface_mask.text().strip()
        desc = self.iface_desc.text().strip()

        if not all([iface_input, ip, mask]):
            QMessageBox.warning(self, "Error", "Please fill all required fields!")
            return

        if iface_input.upper().startswith("GE"):
            iface = f"GigabitEthernet{iface_input.upper()[2:]}/0"
        else:
            iface = iface_input

        self.iface_status.clear()
        self.iface_status.setText(f"⏳ Configuring {router}...\nInterface: {iface}\nIP: {ip}\nMask: {mask}")
        self.iface_progress.setVisible(True)
        self.iface_progress.setMaximum(0)

        self.worker = NetconfWorker(
            "interface_config", router,
            interface=iface, ip=ip, mask=mask, description=desc
        )
        self.worker.success.connect(lambda msg: self.show_iface_success(msg))
        self.worker.error.connect(lambda msg: self.show_iface_error(msg))
        self.worker.start()

    def show_iface_success(self, msg):
        self.iface_progress.setVisible(False)
        self.iface_status.append(f"\n{msg}")
        QMessageBox.information(self, "Success", "Interface configured successfully!")

    def show_iface_error(self, msg):
        self.iface_progress.setVisible(False)
        self.iface_status.append(f"\n{msg}")
        QMessageBox.critical(self, "Error", msg)

    # === OSPF Configuration Tab ===
    def create_ospf_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()

        form_group = QGroupBox("OSPF Configuration")
        form_layout = QFormLayout()

        self.ospf_router = QComboBox()
        self.ospf_router.addItems(["R1", "R2", "Both"])
        form_layout.addRow("Router(s):", self.ospf_router)

        self.ospf_iface = QLineEdit()
        self.ospf_iface.setPlaceholderText("e.g., GigabitEthernet0/0/0/0 or GE0/0/0")
        form_layout.addRow("Interface Name:", self.ospf_iface)

        self.ospf_area = QLineEdit()
        self.ospf_area.setText("0")
        form_layout.addRow("Area ID:", self.ospf_area)

        self.ospf_process = QLineEdit()
        self.ospf_process.setText("1")
        form_layout.addRow("Process ID:", self.ospf_process)

        form_group.setLayout(form_layout)
        layout.addWidget(form_group)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        apply_btn = QPushButton("✅ Apply OSPF Config")
        apply_btn.clicked.connect(self.apply_ospf_config)
        btn_layout.addWidget(apply_btn)
        layout.addLayout(btn_layout)

        self.ospf_status = QTextEdit()
        self.ospf_status.setReadOnly(True)
        self.ospf_status.setMaximumHeight(150)
        layout.addWidget(QLabel("Status:"))
        layout.addWidget(self.ospf_status)

        self.ospf_progress = QProgressBar()
        self.ospf_progress.setVisible(False)
        layout.addWidget(self.ospf_progress)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def apply_ospf_config(self):
        routers = [self.ospf_router.currentText()] if self.ospf_router.currentText() != "Both" else ["R1", "R2"]
        iface_input = self.ospf_iface.text().strip()
        area = self.ospf_area.text().strip()
        process = self.ospf_process.text().strip()

        if not all([iface_input, area, process]):
            QMessageBox.warning(self, "Error", "Please fill all required fields!")
            return

        if iface_input.upper().startswith("GE"):
            iface = f"GigabitEthernet{iface_input.upper()[2:]}/0"
        else:
            iface = iface_input

        self.ospf_status.clear()
        self.ospf_progress.setVisible(True)
        self.ospf_progress.setMaximum(0)

        for router in routers:
            self.ospf_status.append(f"⏳ Configuring {router}...\nInterface: {iface}\nArea: {area}\nProcess: {process}\n")
            self.worker = NetconfWorker(
                "ospf_config", router,
                interface=iface, area=area, process=process
            )
            self.worker.success.connect(lambda msg, r=router: self.ospf_status.append(f"{r}: {msg}"))
            self.worker.error.connect(lambda msg: self.show_ospf_error(msg))
            self.worker.start()

    def show_ospf_error(self, msg):
        self.ospf_progress.setVisible(False)
        self.ospf_status.append(f"\n{msg}")
        QMessageBox.critical(self, "Error", msg)

    # === Router Info Viewer Tab ===
    def create_info_viewer_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()

        ctrl_layout = QHBoxLayout()
        self.info_router = QComboBox()
        self.info_router.addItems(["R1", "R2"])
        refresh_btn = QPushButton("🔄 Refresh Data")
        refresh_btn.clicked.connect(self.refresh_router_info)
        ctrl_layout.addWidget(QLabel("Select Router:"))
        ctrl_layout.addWidget(self.info_router)
        ctrl_layout.addStretch()
        ctrl_layout.addWidget(refresh_btn)
        layout.addLayout(ctrl_layout)

        self.info_table = QTableWidget()
        self.info_table.setColumnCount(5)
        self.info_table.setHorizontalHeaderLabels(["Interface", "IP Address", "Netmask", "Shutdown", "Description"])
        layout.addWidget(QLabel("Interfaces:"))
        layout.addWidget(self.info_table)

        self.ospf_table = QTableWidget()
        self.ospf_table.setColumnCount(2)
        self.ospf_table.setHorizontalHeaderLabels(["Process ID", "Interface"])
        layout.addWidget(QLabel("OSPF Configuration:"))
        layout.addWidget(self.ospf_table)

        self.info_progress = QProgressBar()
        self.info_progress.setVisible(False)
        layout.addWidget(self.info_progress)

        widget.setLayout(layout)
        return widget

    def refresh_router_info(self):
        router = self.info_router.currentText()
        self.info_table.setRowCount(0)
        self.ospf_table.setRowCount(0)

        self.info_progress.setVisible(True)
        self.info_progress.setMaximum(0)

        self.worker = NetconfWorker("get_info", router)
        self.worker.data_ready.connect(self.populate_tables)
        self.worker.error.connect(lambda msg: QMessageBox.critical(self, "Error", msg))
        self.worker.finished.connect(lambda: self.info_progress.setVisible(False))
        self.worker.start()

    def populate_tables(self, data):
        for iface in data.get("interfaces", []):
            row = self.info_table.rowCount()
            self.info_table.insertRow(row)
            self.info_table.setItem(row, 0, QTableWidgetItem(iface["name"]))
            self.info_table.setItem(row, 1, QTableWidgetItem(iface["ip"]))
            self.info_table.setItem(row, 2, QTableWidgetItem(iface["mask"]))
            self.info_table.setItem(row, 3, QTableWidgetItem(iface["shutdown"]))
            self.info_table.setItem(row, 4, QTableWidgetItem(iface["desc"]))

        for ospf in data.get("ospf", []):
            row = self.ospf_table.rowCount()
            self.ospf_table.insertRow(row)
            self.ospf_table.setItem(row, 0, QTableWidgetItem(ospf["process"]))
            self.ospf_table.setItem(row, 1, QTableWidgetItem(ospf["interface"]))

# === Main Application ===
if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = NetconfGUI()
    gui.show()
    sys.exit(app.exec_())