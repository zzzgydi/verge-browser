# Human Handoff in the Same Browser

An agent uses CDP to control Chromium. A person views and controls the same browser through noVNC (`xvfb_vnc`) or Xpra.
The base API does not assign control to one client. It does not stop automation or notify the agent when manual work ends.

Keep the session URL and cookie private. Both grant access to the browser.
Do not put them in public issues, logs, or recordings.

## Handoff Procedure

1. Ask all automation clients to stop browser actions.
2. Wait for confirmation that no action is still running.
3. Configure the CLI's service URL and admin token in your management terminal.
4. Issue a session ticket for the same sandbox:

   ```bash
   verge-browser sandbox session codex-demo --mode one_time --ttl-sec 900 --json
   ```

5. Open the returned `url` privately.
6. Confirm the intended tab and account.
7. Complete the manual step yourself. Do not send credentials to the agent.
8. Tell the agent that manual control is complete.
9. Ask the agent to inspect the current tabs.
10. Ask the agent to take a fresh snapshot before continuing.

The one-time URL creates a browser session cookie on first use. That URL cannot be used again.
If you need another entry or the session expires, request a new URL.

The example ticket expires after 900 seconds. Its session cookie uses the ticket's remaining lifetime.
Expiry blocks new authenticated requests and reconnections. It does not automatically close an existing VNC WebSocket.
The default ticket lifetime is 60 seconds.

Do not reuse element references from before the manual step.

## Do Not Pause the Sandbox to Pause the Agent

Stop the **agent's actions**, not the sandbox, for live handoff.
`verge-browser sandbox pause` removes the runtime container. It ends Chromium and disconnects CDP and the visual session.
The workspace remains on disk.

Coordinate all connected automation clients before manual work. The base API has no control lock.
The [dsh plugin](../../packages/dsh-plugin/README.md) stops its own automation bridge during handoff. It does not lock out other clients.

After a browser restart or sandbox resume, obtain fresh access URLs. Inspect the browser state before acting.
See [Persistent Browser Profiles](persistent-profiles.md) and [Codex Integration](../integrations/codex.md).
