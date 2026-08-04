# Reassemble Context Data v3 archive

The repository stores the validated 5,000-YAML archive as Base64 text parts so it can be committed through the GitHub API without an external file host.

```bash
cat context-expansion-v3-5000.tar.xz.b64.part* | base64 -d > context-expansion-v3-5000.tar.xz
sha256sum context-expansion-v3-5000.tar.xz
tar -xJf context-expansion-v3-5000.tar.xz
```

Expected SHA-256: `06d832a6ce5669f95b4a3f84ad157fce6761e283c030ef410c9c622360cd6406`
Archive bytes: `478888`
Part count: `8`
Internal root: `expansion_v3/`
