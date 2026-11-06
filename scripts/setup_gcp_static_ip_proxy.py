"""
Automated 1-Click GCP Static Outbound IPv4 Proxy Provisioner for CoinDCX API (`Option 1`).
Provisions:
  1. Permanent Static External IPv4 Address (`coindcx-static-ip` in `us-west1`)
  2. Firewall Rule (`allow-coindcx-proxy` on `tcp:8888`)
  3. Free-Tier `e2-micro` VM (`coindcx-static-proxy` in `us-west1-b`) running `tinyproxy` with BasicAuth
  4. Automatically syncs `COINDCX_PROXY_URL` to `Crypto_Trades_Journal` (`_Live_Account_Sync` tab)
     so both `staging` and `main` route all signed CoinDCX requests through the single Static IP forever.
"""
from __future__ import annotations
import json
import os
import secrets
import subprocess
import sys
import tempfile

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "gen-lang-client-0777980903")
REGION = "us-west1"
ZONE = "us-west1-b"
ADDRESS_NAME = "coindcx-static-ip"
FIREWALL_NAME = "allow-coindcx-proxy"
INSTANCE_NAME = "coindcx-static-proxy"
PROXY_PORT = 8888


def _run_gcloud(args: list[str]) -> tuple[int, str, str]:
    env = dict(os.environ)
    env["CLOUDSDK_CORE_PROJECT"] = PROJECT_ID
    cmd = ["gcloud", f"--project={PROJECT_ID}", "--quiet"] + args
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, shell=(os.name == "nt"))
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def provision_static_ip_proxy(enable_api_if_requested: bool = False) -> dict:
    if enable_api_if_requested:
        print(f"[1/5] Enabling Compute Engine API (`compute.googleapis.com`) in `{PROJECT_ID}`...")
        rc, out, err = _run_gcloud(["services", "enable", "compute.googleapis.com"])
        if rc != 0:
            return {"ok": False, "error": f"Failed to enable compute.googleapis.com: {err or out}"}

    print(f"[2/5] Checking/Reserving Static External IPv4 `{ADDRESS_NAME}` in `{REGION}`...")
    rc, out, err = _run_gcloud([
        "compute", "addresses", "list",
        f"--filter=name={ADDRESS_NAME}",
        "--limit=5",
        "--format=json(name,address,region,status)",
    ])
    if rc != 0:
        return {
            "ok": False,
            "error": err or out,
            "enable_url": f"https://console.developers.google.com/apis/api/compute.googleapis.com/overview?project={PROJECT_ID}",
        }

    items = json.loads(out) if out else []
    if not items:
        rc_c, out_c, err_c = _run_gcloud([
            "compute", "addresses", "create", ADDRESS_NAME,
            f"--region={REGION}",
        ])
        if rc_c != 0:
            return {"ok": False, "error": f"Failed to create static IP: {err_c or out_c}"}
        rc, out, err = _run_gcloud([
            "compute", "addresses", "list",
            f"--filter=name={ADDRESS_NAME}",
            "--limit=5",
            "--format=json(name,address,region,status)",
        ])
        items = json.loads(out) if out else []

    if not items or not items[0].get("address"):
        return {"ok": False, "error": "Could not resolve static IP address after creation."}

    static_ip = items[0]["address"]
    print(f"  -> Reserved Permanent Static IP: {static_ip}")

    print(f"[3/5] Ensuring Firewall Rule `{FIREWALL_NAME}` (`tcp:{PROXY_PORT}`)...")
    rc_fw, out_fw, _ = _run_gcloud([
        "compute", "firewall-rules", "list",
        f"--filter=name={FIREWALL_NAME}",
        "--limit=5",
        "--format=json(name)",
    ])
    fw_items = json.loads(out_fw) if (rc_fw == 0 and out_fw) else []
    if not fw_items:
        _run_gcloud([
            "compute", "firewall-rules", "create", FIREWALL_NAME,
            f"--allow=tcp:{PROXY_PORT}",
            "--target-tags=coindcx-proxy",
            "--description=Allow authenticated CoinDCX HTTPS proxy from Streamlit Cloud",
        ])

    proxy_token = secrets.token_hex(12)
    startup_script = (
        "#!/bin/bash\n"
        "export DEBIAN_FRONTEND=noninteractive\n"
        "apt-get update -y && apt-get install -y tinyproxy\n"
        f"sed -i 's/^Port .*/Port {PROXY_PORT}/' /etc/tinyproxy/tinyproxy.conf\n"
        "sed -i 's/^Allow /#Allow /g' /etc/tinyproxy/tinyproxy.conf\n"
        f"grep -q '^BasicAuth ' /etc/tinyproxy/tinyproxy.conf || echo 'BasicAuth coindcx {proxy_token}' >> /etc/tinyproxy/tinyproxy.conf\n"
        "systemctl enable tinyproxy && systemctl restart tinyproxy\n"
    )

    print(f"[4/5] Checking/Creating Free-Tier `e2-micro` Proxy VM `{INSTANCE_NAME}` in `{ZONE}`...")
    rc_vm, out_vm, _ = _run_gcloud([
        "compute", "instances", "list",
        f"--filter=name={INSTANCE_NAME}",
        "--limit=5",
        "--format=json(name,status)",
    ])
    vm_items = json.loads(out_vm) if (rc_vm == 0 and out_vm) else []
    if not vm_items:
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, encoding="utf-8", newline="\n") as tf:
            tf.write(startup_script)
            startup_file = tf.name
        try:
            rc_cv, out_cv, err_cv = _run_gcloud([
                "compute", "instances", "create", INSTANCE_NAME,
                f"--zone={ZONE}",
                "--machine-type=e2-micro",
                f"--address={static_ip}",
                "--tags=coindcx-proxy",
                "--image-family=debian-12",
                "--image-project=debian-cloud",
                f"--metadata-from-file=startup-script={startup_file}",
            ])
        finally:
            try:
                os.remove(startup_file)
            except Exception:
                pass
        if rc_cv != 0:
            return {"ok": False, "error": f"Failed to create proxy VM: {err_cv or out_cv}"}

    proxy_url = f"http://coindcx:{proxy_token}@{static_ip}:{PROXY_PORT}"
    print(f"[5/5] Syncing `COINDCX_PROXY_URL` to `Crypto_Trades_Journal` & local config...")
    try:
        import coindcx_engine as eng
        eng.set_coindcx_proxy_url(proxy_url, sync_to_sheet=True)
    except Exception:
        pass

    return {
        "ok": True,
        "static_ip": static_ip,
        "proxy_url": proxy_url,
    }


if __name__ == "__main__":
    enable_flag = "--enable-api" in sys.argv
    res = provision_static_ip_proxy(enable_api_if_requested=enable_flag)
    print(json.dumps(res, indent=2))
    sys.exit(0 if res.get("ok") else 1)
