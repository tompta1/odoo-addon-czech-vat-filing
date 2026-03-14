# Release And Publishing Runbook

## 1. Validate

Run addon tests before tagging:

```bash
flatpak-spawn --host podman exec -i odoo_web sh -lc \
  "odoo -d odoo19_cz_test -c /etc/odoo/odoo.conf --http-port=10069 --stop-after-init -u l10n_cz_vat_filing --test-enable --test-tags /l10n_cz_vat_filing"
```

Optional smoke export:

```bash
./scripts/odoo_seed_cz_vat_cases.sh
./scripts/odoo_export_cz_vat_filings.sh 2026-03-01 2026-03-31 /tmp/cz-vat-filing
```

## 2. Versioning

Update addon versions in:

- `addons/custom/l10n_cz_vat_filing/__manifest__.py`
- `addons/custom/l10n_cz_vat_oss_bridge/__manifest__.py` (if changed)
- `addons/custom/odoo19_report_compat/__manifest__.py` (if changed)

Record release notes in `CHANGELOG.md`.

## 3. Git Stage, Commit, Tag

If this workspace is not yet a git repository:

```bash
git init
```

Stage and commit:

```bash
git add .
git commit -m "release: v19.0.22.0.0"
```

Create an annotated tag:

```bash
git tag -a v19.0.22.0.0 -m "Czech VAT filing release v19.0.22.0.0"
```

Push once remote is configured:

```bash
git remote add origin <your-github-repo-url>
git push -u origin main
git push origin v19.0.22.0.0
```

## 4. Pack Release Artifacts

Create per-addon zip packages and checksums:

```bash
./scripts/release_pack_addons.sh v19.0.22.0.0
```

Artifacts are written to:

- `dist/v19.0.22.0.0/*.zip`
- `dist/v19.0.22.0.0/SHA256SUMS.txt`

## 5. Publish Targets

### GitHub Release

Create a release from tag `v19.0.22.0.0` and attach:

- `l10n_cz_vat_filing-<version>.zip`
- `l10n_cz_vat_oss_bridge-<version>.zip`
- `odoo19_report_compat-<version>.zip` (only if you publish this compatibility addon)
- `SHA256SUMS.txt`

### Odoo Apps

Upload each addon zip separately (one zip per addon root).
Keep dependency chain clear:

- install `l10n_cz_vat_filing` first
- install `l10n_cz_vat_oss_bridge` only with `l10n_eu_oss`

### OCA (if you later target OCA)

OCA usually requires one repository per addon family, strict CI, and OCA metadata/readme format.
Use this repository as the technical baseline, then prepare an OCA-style PR branch as a separate step.
