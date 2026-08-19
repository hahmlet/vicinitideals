# Footnote dispositions

One file per jurisdiction, named for its layer:
`flats/config/footnotes/or/multnomah/gresham.yaml`.

Every footnote in every stored document is captured by
`flats.encode.footnotes` whether or not anybody has looked at it. This
directory is where looking at one gets written down.

```yaml
notes:
  - quote: "or/multnomah/gresham/4.0400.corridor.txt#L217"
    digest: "9f2c1ab34de0"
    state: dismissed
    reason: "governs temporary health hardship dwellings, not a use the pod is"

  - quote: "or/clackamas/happy-valley/16.22.residential.txt#L1035"
    digest: "0c41de99ab72"
    state: encoded
    encoded_as: "SFA setback_front_ft variant, corner lot on a local street"
```

## Rules

**`unread` is never written down.** It is what a footnote is when no ruling
matches it, and it blocks. Writing it would turn a default that is safe by
construction into one somebody has to remember.

**A dismissal states a reason.** A dismissal with no reason is an omission
with extra steps. Reasons are meant to repeat: the same sentence written
across forty notes is a class, and deleting that one reason from these files
returns all forty to `unread` in a single pass. That is what makes the
rejection pass re-runnable instead of a decision nobody can revisit.

**`encoded` names what it became** — the zone and field it turned into — so
the claim can be checked against the encoding rather than believed.

**Rulings bind to the words, not the line.** `digest` is
`flats.encode.dispositions.digest(text)`: whitespace collapsed, case dropped,
first twelve hex characters of the SHA-1. Re-fetching a document moves its
lines and the ruling follows. A codifier amending the note changes the digest,
the ruling stops matching, and the footnote is `unread` again — which is
correct, because the ruling was about a sentence that no longer exists.

`quote` is for the reviewer who wants to open the line. It is not what
matches, and it is allowed to go stale.

## Working the queue

```bash
uv run python -m flats.encode.footnotes --unreconciled   # documents whose capture is in doubt
uv run python -m flats.encode.dispositions               # counts per jurisdiction
uv run python -m flats.encode.dispositions --queue       # every footnote nobody has ruled on
```
