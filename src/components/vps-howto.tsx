const INSTALL = `sudo apt-get update
sudo apt-get install -y python3 git
git clone https://github.com/kbmod/hierarchy.git
cd hierarchy/vps-agent
sudo bash scripts/install-service.sh`;

export function VpsHowto() {
  return (
    <div className="space-y-3 text-[14px] leading-relaxed text-muted">
      <p className="text-fg">
        You do not leave a terminal open. Install it as a background service — it keeps running after you
        log out and after reboot.
      </p>
      <ol className="list-decimal space-y-2 pl-5">
        <li>SSH in. You need Python 3 — no extra packages.</li>
        <li>Run the commands below. The installer prints a URL and a token, then you can disconnect.</li>
        <li>
          Paste the token and a Tailscale <span className="font-medium text-fg">100.x.x.x</span> URL from{" "}
          <span className="font-mono text-[12px] text-fg">tailscale ip -4</span> on the VPS. Do not use the
          .ts.net MagicDNS name in this app — Android cannot resolve it here. The phone needs Tailscale
          connected. You do not open a public firewall port.
        </li>
      </ol>
      <pre className="overflow-x-auto rounded-[16px] bg-elevated p-3 font-mono text-[11px] leading-relaxed text-fg">
        {INSTALL}
      </pre>
      <p>
        Status: <span className="font-mono text-[12px] text-fg">systemctl status hierarchy</span>
        <br />
        Health: <span className="font-mono text-[12px] text-fg">curl http://127.0.0.1:8765/api/health</span>
      </p>
    </div>
  );
}
