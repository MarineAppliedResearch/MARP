# Local host and credential notes — NOT tracked

Copy to `hosts.md` beside this file and fill in. `.marp/local/` is git-ignored.

Repository files may say *that* a credential exists and where it lives. They may never
hold its value — `marp harness check` fails on that, and the reason it exists is that a
live password sat in a public repository for three weeks.

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
