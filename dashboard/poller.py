import re
import time
import threading
from datetime import datetime
from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException

# ── Danh sách thiết bị ────────────────────────────────────────────
DEVICES = [
    {"name": "R-HQ",     "host": "192.168.120.134", "location": "HQ"},
    {"name": "R-Branch1","host": "192.168.120.135", "location": "Branch 1"},
    {"name": "R-Branch2","host": "192.168.120.136", "location": "Branch 2"},
]

CREDENTIALS = {
    "device_type": "cisco_ios",
    "username":    "admin",
    "password":    "cisco123",
    "timeout":     10,
}

# ── Kho dữ liệu dùng chung với Flask ─────────────────────────────
data_store = {}
for dev in DEVICES:
    data_store[dev["name"]] = {
        "name":         dev["name"],
        "host":         dev["host"],
        "location":     dev["location"],
        "status":       "unknown",
        "cpu":          None,
        "ram_used":     None,
        "ram_total":    None,
        "interfaces":   [],
        "last_updated": None,
    }

# ── Parse CPU ─────────────────────────────────────────────────────
def parse_cpu(output):
    # "CPU utilization for five seconds: 3%/0%"
    match = re.search(r"five seconds:\s*(\d+)%", output)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)%/\d+%", output)
    if match:
        return int(match.group(1))
    return 0

# ── Parse RAM ─────────────────────────────────────────────────────
def parse_ram(output):
    # "Processor  261904K  +  6076K"  hoặc
    # "Total: 314572800  Used: 177864312"
    match = re.search(r"Total:\s*(\d+).*?Used:\s*(\d+)", output, re.DOTALL)
    if match:
        total = int(match.group(1)) // (1024*1024)
        used  = int(match.group(2)) // (1024*1024)
        return used, total
    # fallback Processor pool
    match = re.search(r"Processor\s+(\d+)\s+\d+\s+(\d+)", output)
    if match:
        total = int(match.group(1)) // 1024
        free  = int(match.group(2)) // 1024
        return total - free, total
    return 0, 0

# ── Parse Interface ───────────────────────────────────────────────
def parse_interfaces(output):
    interfaces = []
    for line in output.strip().splitlines():
        parts = line.split()
        if len(parts) >= 6 and any(line.startswith(p) for p in
                ["Eth","Gi","Fa","Se","Lo","Tu"]):
            interfaces.append({
                "name":   parts[0],
                "ip":     parts[1],
                "status": parts[4],
                "proto":  parts[5],
            })
    return interfaces

# ── Poll 1 thiết bị ───────────────────────────────────────────────
def poll_device(dev):
    name = dev["name"]
    params = {**CREDENTIALS, "host": dev["host"]}
    try:
        with ConnectHandler(**params) as conn:
            cpu_out  = conn.send_command("show processes cpu | include CPU utilization")
            ram_out = conn.send_command("show processes memory")
            intf_out = conn.send_command("show ip interface brief")

        cpu            = parse_cpu(cpu_out)
        ram_used, ram_total = parse_ram(ram_out)
        interfaces     = parse_interfaces(intf_out)

        data_store[name].update({
            "status":       "up",
            "cpu":          cpu,
            "ram_used":     ram_used,
            "ram_total":    ram_total,
            "interfaces":   interfaces,
            "last_updated": datetime.now().strftime("%H:%M:%S"),
        })
        print(f"[OK]  {name} | CPU={cpu}% | RAM={ram_used}/{ram_total}MB | {len(interfaces)} ifaces")

    except (NetmikoTimeoutException, NetmikoAuthenticationException, Exception) as e:
        data_store[name].update({
            "status":       "down",
            "last_updated": datetime.now().strftime("%H:%M:%S"),
        })
        print(f"[ERR] {name} | {e}")

# ── Vòng lặp poll mỗi 30 giây ────────────────────────────────────
def polling_loop(interval=30):
    while True:
        print(f"\n[POLL] Bắt đầu poll lúc {datetime.now().strftime('%H:%M:%S')}")
        threads = [threading.Thread(target=poll_device, args=(dev,), daemon=True)
                   for dev in DEVICES]
        for t in threads: t.start()
        for t in threads: t.join()
        print(f"[POLL] Xong. Chờ {interval}s...\n")
        time.sleep(interval)

def start_poller(interval=30):
    t = threading.Thread(target=polling_loop, args=(interval,), daemon=True)
    t.start()
