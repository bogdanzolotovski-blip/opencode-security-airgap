// Optional local OpenCode plugin. No npm dependencies, HTTP service or cloud calls.
// Text filters are NOT command authorization or an OS sandbox.
import { spawn } from "node:child_process";
import { appendFile, mkdir } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";

function checkText(text, executable, timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    if (Buffer.byteLength(text, "utf8") > 900000) return reject(new Error("Scan input too large"));
    const child = spawn(executable, [], { stdio: ["pipe", "pipe", "ignore"] });
    let output = "", done = false;
    const finish = (error, value) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      error ? reject(error) : resolve(value);
    };
    const timer = setTimeout(() => { child.kill("SIGKILL"); finish(new Error("Scanner timeout")); }, timeoutMs);
    child.on("error", () => finish(new Error("Scanner unavailable")));
    child.stdin.on("error", () => finish(new Error("Scanner stdin failed")));
    child.stdout.on("data", data => {
      output += data.toString();
      if (output.length > 16000) { child.kill("SIGKILL"); finish(new Error("Invalid scanner output")); }
    });
    child.on("close", code => {
      try {
        if (code !== 0) throw new Error("Scanner failed");
        const result = JSON.parse(output);
        if (result.status !== "success" || !["allow", "block", "human_in_the_loop_required"].includes(result.decision))
          throw new Error("Invalid scanner decision");
        finish(null, result);
      } catch { finish(new Error("Scanner failed")); }
    });
    child.stdin.end(JSON.stringify({ text }));
  });
}

// Expose only the plugin factory from the installed file: OpenCode loads exports as factories.
export const AirgapFirewall = async () => {
  const executable = process.env.AGENT_FIREWALL_BIN || join(homedir(), "agent-controls/bin/agent-firewall-scan");
  const mode = process.env.AGENT_FIREWALL_MODE || "monitor";
  if (!["monitor", "enforce"].includes(mode)) throw new Error("Invalid AGENT_FIREWALL_MODE");
  const logdir = join(homedir(), ".local/state/agent-controls");
  await mkdir(logdir, { recursive: true, mode: 0o700 });
  return {
    "tool.execute.before": async (input, output) => {
      let decision;
      try { decision = (await checkText(JSON.stringify(output.args ?? {}), executable)).decision; }
      catch { decision = "error"; }
      // No prompts, arguments, source code, scanner reasons or tool output in this log.
      await appendFile(join(logdir, "firewall.ndjson"), JSON.stringify({
        time: new Date().toISOString(), event: "tool.execute.before", decision, mode
      }) + "\n", { mode: 0o600 });
      if (mode === "enforce" && decision !== "allow") throw new Error("Local text firewall: action requires operator review");
    }
  };
};
