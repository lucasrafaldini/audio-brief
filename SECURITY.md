# Security Policy

## Reporting a Vulnerability

Please do **not** open a public issue for security vulnerabilities.
Instead, email the maintainer or open a private security advisory via
GitHub (Security → Advisories → "Report a vulnerability"):

https://github.com/lucasrafaldini/audio-brief/security/advisories/new

You can expect an acknowledgement within a few days. We'll work with you
to understand and fix the issue before any public disclosure.

```mermaid
flowchart TD
    found(["You find a vulnerability"]) --> no_issue["Do NOT open a public issue"]
    no_issue --> email["Email the maintainer"]
    no_issue --> advisory["GitHub private security advisory"]
    email --> ack["Acknowledgement within a few days"]
    advisory --> ack
    ack --> fix["Understand and fix together"]
    fix --> disclose["Public disclosure"]
```
