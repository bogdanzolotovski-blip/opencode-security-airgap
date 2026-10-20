import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile, mkdtemp, writeFile, chmod, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const source = await readFile(new URL("../agent-controls/plugins/airgap-firewall.js", import.meta.url), "utf8");
const { checkText, AirgapFirewall } = await import("data:text/javascript;base64," +
  Buffer.from(source + "\nexport {checkText};").toString("base64"));
test("scanner success, error, malformed response, timeout and enforce contract", async () => {
  if (process.platform === "win32") return; // Real subprocess contract runs on Linux CI.
  const temp = await mkdtemp(join(tmpdir(), "airgap-plugin-"));
  try {
    const executable = join(temp, "scanner");
    const set = async body => { await writeFile(executable, "#!/bin/sh\n" + body + "\n"); await chmod(executable, 0o755); };
    await set("cat >/dev/null\nprintf '%s' '{\"decision\":\"allow\",\"status\":\"success\"}'");
    assert.equal((await checkText("safe", executable)).decision, "allow");
    await set("cat >/dev/null\nprintf '%s' '{\"decision\":\"block\",\"status\":\"success\"}'");
    assert.equal((await checkText("test", executable)).decision, "block");
    process.env.AGENT_FIREWALL_BIN = executable;
    process.env.AGENT_FIREWALL_MODE = "enforce";
    const plugin = await AirgapFirewall();
    await assert.rejects(plugin["tool.execute.before"]({ tool: "bash" }, { args: { command: "test" } }));
    process.env.AGENT_FIREWALL_MODE = "monitor";
    await (await AirgapFirewall())["tool.execute.before"]({}, { args: {} });
    await set("exit 2");
    await assert.rejects(checkText("test", executable));
    process.env.AGENT_FIREWALL_MODE = "enforce";
    await assert.rejects((await AirgapFirewall())["tool.execute.before"]({}, { args: {} }));
    await set("cat >/dev/null\nprintf invalid");
    await assert.rejects(checkText("test", executable));
    await set("sleep 2");
    await assert.rejects(checkText("test", executable, 20));
    await assert.rejects(checkText("test", join(temp, "absent")));
  } finally { await rm(temp, { recursive: true, force: true }); }
});
