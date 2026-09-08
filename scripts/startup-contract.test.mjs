import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("the preview demo cannot occupy the VPS agent port", async () => {
  const [startup, proxy] = await Promise.all([
    readFile(new URL("../startup.sh", import.meta.url), "utf8"),
    readFile(new URL("../src/lib/server/proxy.ts", import.meta.url), "utf8"),
  ]);

  assert.match(startup, /DEMO_AGENT_PORT=18765/);
  assert.doesNotMatch(startup, /127\.0\.0\.1:8765/);
  assert.match(startup, /--port "\$DEMO_AGENT_PORT"/);
  assert.doesNotMatch(startup, /--port (?:"?)8765/);
  assert.match(proxy, /const DEMO_PORT = "18765"/);
  assert.doesNotMatch(proxy, /const DEMO = "http:\/\/127\.0\.0\.1:8765"/);
  assert.match(proxy, /!isLoopbackHost\(host\)/);
  assert.match(proxy, /path\.startsWith\("\/\/"\)/);
  assert.match(proxy, /url\.origin !== target\.origin/);
});
