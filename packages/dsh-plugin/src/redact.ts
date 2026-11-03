/** Remove the admin token and ticketed URLs from text that may reach a log or a browser. */
export function redact(text: string, token: string): string {
  return text.split(token).join('[redacted]')
    .replace(/\b(?:wss?|https?):\/\/[^\s<>"']*[?&]ticket=[^\s<>"']*/g, '[ticket URL redacted]');
}
