# Stored source text

One `.txt` per cited code section, plus a `<name>.txt.meta.json` sidecar holding
its URL, retrieval date, and SHA-256. Laid out by jurisdiction:

```
or/multnomah/portland/33.110-t110-4.txt
or/multnomah/portland/33.110-t110-4.txt.meta.json
```

Rule values cite into this tree by line span — `or/multnomah/portland/33.110-t110-4.txt#L42-L48`.

Do not hand-edit a `.txt` here. The sidecar hash is what proves the encoded
number was read from these words; editing the text without re-fetching makes
`ProvenanceStore.tampered()` flag it, which is the intended alarm, not a bug.
Re-fetch through `save()` instead.
