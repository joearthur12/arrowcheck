# Security Policy

## Security boundary

ArrowCheck treats raw MechSMILES text and related batch metadata as untrusted
input.

Its main safety boundary is:

```text
raw user input
-> strict ArrowCheck parser
-> typed parsed representation
-> canonical safe MechSMILES reconstruction
-> upstream ChRIMP
```

ArrowCheck does not pass raw user-provided arrow text directly into ChRIMP
after validation, and ArrowCheck must never introduce `eval()` in new code.

## HTML-report stance

ArrowCheck's offline HTML reports display untrusted content such as case IDs,
metadata, raw rows, exception details, and original MechSMILES strings.

Security expectations:

- escape untrusted HTML content before rendering;
- never inject untrusted strings with `innerHTML`;
- never embed unescaped untrusted JSON inside executable script blocks;
- use safe text handling such as DOM `textContent` for client-side filtering.

## Why raw MechSMILES must remain untrusted

Upstream ChRIMP historically uses unsafe parsing patterns internally, including
`eval()` in its own parser path. ArrowCheck exists specifically to reject
unsafe or malformed mechanism text before upstream execution. Any regression in
this boundary should be treated as a security issue.

## Reporting a vulnerability

Please report suspected security issues privately before opening a public issue.

Contact:

- `joearthurganly@gmail.com`

Include:

- the ArrowCheck version or commit SHA;
- a minimal reproducer;
- expected behavior;
- observed behavior;
- whether the issue involves parser bypass, unsafe HTML rendering, or saved
  results regeneration.
