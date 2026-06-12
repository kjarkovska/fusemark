# Release Checklist (v1.0.0)

A single page to follow when cutting the first public release. Build mechanics live
in [`installer/README.md`](../installer/README.md); this is the ordered to-do list.

## 0. Name & trademark (do this first)

- [ ] **Decide the final product name.** "FuseMark" is too close to "Obsidian"
      (Dynalist Inc.) and risks confusion/trademark claims. Everything below depends
      on the chosen name.
- [ ] Once chosen, update the name in: `installer/setup.iss`, `README.md`, the Gumroad
      listing, and (if the GitHub repo is renamed) `RELEASES_URL` in `app/updater.py`.

## 1. Code & docs

- [ ] `app/version.py` `VERSION` = `1.0.0`
- [ ] `installer/setup.iss` `MyAppVersion` = `1.0.0` (matches version.py)
- [ ] `<support-email>` filled in `docs/PRIVACY_POLICY.md`
- [ ] `LICENSE` (GPL v3) present at repo root
- [ ] `ruff check app tests` clean and `pytest` green (CI is green)

## 2. Build & sign

- [ ] `pyinstaller installer/build.spec`
- [ ] Smoke-test `dist\FuseMark\FuseMark.exe` with ffmpeg copied alongside —
      window opens **and recording works** (DLL failure point)
- [ ] Sign `dist\FuseMark\FuseMark.exe` with `signtool`
- [ ] Build installer: `iscc installer\setup.iss`
- [ ] Sign `installer\Output\FuseMarkSetup.exe` with `signtool`

## 3. Verify on a clean machine

- [ ] Run the full test checklist in `installer/README.md` on a Windows 10 **and**
      Windows 11 VM with no Python installed
- [ ] Confirm SmartScreen does not block the signed installer
- [ ] (Optional but recommended) Submit the signed installer to the
      [Microsoft malware portal](https://www.microsoft.com/en-us/wdsi/filesubmission)
      to speed up reputation

## 4. Publish

- [ ] Push the source to a **public** GitHub repo (must be public, with `LICENSE`,
      before Gumroad goes live — GPL v3 requires source availability)
- [ ] `git tag v1.0.0 && git push --tags` (triggers the release build workflow)
- [ ] Create the Gumroad product: final name, €19 one-time, **no licence-key
      generation**, upload the signed installer, link the GitHub repo and the privacy
      policy, set the support email
- [ ] Verify the in-app update banner end-to-end against the published GitHub release
