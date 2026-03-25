SDN-Based Network Automation using YANG, NETCONF & RESTCONF

Overview
This project implements a model-driven network automation system using Software-Defined Networking (SDN). It replaces manual CLI configuration with YANG data models and NETCONF/RESTCONF protocols to enable structured, scalable, and automated network management.
An OpenDaylight SDN controller is used to centrally manage and configure virtual network devices, demonstrating efficient, programmable networking.

Objectives
•	Develop reusable YANG models for network configuration 
•	Implement NETCONF (transactional) and RESTCONF (REST-based) communication 
•	Integrate OpenDaylight for centralized control 
•	Automate configuration of virtual routers 
•	Validate system through simulation and real-time feedback 

System Architecture
The system follows a 3-layer design:
•	Frontend Layer 
o	YANG model creation and validation 
•	Backend Layer 
o	OpenDaylight controller 
o	NETCONF / RESTCONF communication 
•	Hardware Layer 
o	Virtual routers (GNS3 / VirtualBox / VMware) 

Technologies Used
•	YANG Modeling Language 
•	NETCONF / RESTCONF 
•	OpenDaylight SDN Controller 
•	Python (automation scripts) 
•	GNS3 / Mininet / VirtualBox 
•	Ubuntu OS

Methodology
1.	Create and validate YANG models (Pyang) 
2.	Convert models to XML/JSON payloads 
3.	Send configurations via NETCONF/RESTCONF 
4.	Apply configurations using OpenDaylight 
5.	Test on virtual routers 
6.	Monitor and validate system feedback
   
Features
•	Automated device configuration 
•	Centralized network control 
•	Vendor-neutral approach 
•	Real-time monitoring and feedback 
•	Rollback support for failed configurations

Results
•	Successful end-to-end automation 
•	Reduced configuration errors 
•	Faster deployment of network changes 
•	Scalable and reproducible system 

Future Work
•	Develop a web-based user interface 
•	Improve monitoring dashboards 
•	Extend support to multi-vendor environments 
•	Enhance automation intelligence 

Project Structure (Example)
project/
│── yang-models/
│── scripts/
│── configs/
│── docs/
│── README.md

Cost
All tools used are open-source, resulting in zero cost (R0) for development and testing.

Conclusion
This project demonstrates how SDN and model-driven networking can transform traditional network management into a faster, scalable, and reliable automated system ready for modern environments like 5G, IoT, and cloud networks.

