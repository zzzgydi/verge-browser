# Human Handoff in the Same Browser

Verge Browser lets an agent use CDP while a person sees and controls the same Chromium through noVNC (`xvfb_vnc`) or Xpra. It does not arbitrate control, suspend the agent automatically, or notify the agent that a manual step is complete.

## Handoff Procedure

1. Ask the agent to stop browser actions and wait for confirmation. Opening the viewer alone does not stop an in-flight action.
2. With the CLI's service URL and admin token configured, issue a session ticket for the same sandbox:

   ```bash
   verge-browser sandbox session codex-demo --mode one_time --ttl-sec 900 --json
   ```

3. Open the returned `url` privately. Confirm the intended tab and account before acting. Complete login, MFA, or the requested manual step yourself; do not send credentials to the agent.
4. Tell the agent you are done. It should inspect the current tabs and take a fresh snapshot before continuing, rather than reusing stale element references.

The one-time entry URL is consumed on use and establishes a browser session cookie. If you need another entry or the session has expired, request a new URL. Both the URL and cookie grant access to the browser, so do not publish them in issues, logs, or recordings. The example's 900-second TTL allows time for the manual step; the default ticket TTL is only 60 seconds.

## Do Not Pause the Sandbox to Pause the Agent

`verge-browser sandbox pause` removes the runtime container. It ends Chromium and disconnects CDP and the visual session, while keeping the workspace on disk. To hand off a live browser, stop the **agent's actions**, not the sandbox.

If multiple automation clients are connected, coordinate all of them before manual work. This is a caller responsibility, not a built-in control lock.

After a browser restart or sandbox resume, obtain fresh access URLs and inspect the new browser state. See [Persistent Browser Profiles](persistent-profiles.md) and [Codex Integration](../integrations/codex.md).
