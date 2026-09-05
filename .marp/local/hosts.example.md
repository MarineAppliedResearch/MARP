# Local host and credential notes — NOT tracked

Copy to `hosts.md` beside this file and fill in. `.marp/local/` is git-ignored.

Repository files may say *that* a credential exists and where it lives. They may never
hold its value; `marp harness check` fails on that.

Two things follow that are easy to get wrong. Notes *about* a credential are part of the
problem: naming which file or which commit held one is a signpost, and a signpost in a
public repository is worth about as much to a reader as the value. And removing a file
does not remove it from history, so the fix for a disclosed credential is always to
rotate it, never to delete the file and consider it handled.

```text
Jellyfin development instance
  host:      
port:      
  account:   
  password:  
  note:      the live service on this machine is a different port. Do not touch it.

Development database
  produced by `marp db up`; run `marp db env` rather than writing values here.
```
