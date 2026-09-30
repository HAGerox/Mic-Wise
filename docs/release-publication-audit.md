# Alpha.4 publication audit

Reviewed on 30 September 2026 before publishing `v0.1.0-alpha.4`.

## Scope and result

No credentials, private show files, recordings, personal contact details in file
contents, or other material requiring removal were found. No history rewrite was
needed. The GitHub repository was already public at the time of this audit.

The review covered every reachable commit and blob from all fetched branches,
tags, GitHub pull-request head/merge refs, and local checkpoint refs: 62 commits,
804 objects and 429 unique file blobs before this release's final additions.
Commit messages, author metadata, historical file paths and text changes were
reviewed alongside current files, documentation, workflows and packaging scripts.
GitHub issues and comments and the six existing alpha.2/alpha.3 release archive
inventories were also inspected. No private show-data, environment, key, database,
recording or log paths appeared in those archives.

Gitleaks 8.30.1 scanned all Git refs with full history, every exported historical
text blob, and the proposed publication files. All three scans reported zero
findings. TruffleHog 3.97.9 scanned the Git repository with verification disabled
and reported zero verified or unverified secrets. Disabling verification avoids
transmitting candidate credentials to external services. GitHub's existing secret
scanning and push protection were enabled; its secret-alert list was empty.

Manual review included credential-like strings, addresses, usernames, filesystem
paths, assistant instruction files, integration documentation, test fixtures and
binary assets. Matches were ordinary source/test identifiers, GitHub Actions'
ephemeral token reference, loopback/test/example network addresses and protocol
examples. Commit attribution uses GitHub no-reply addresses plus a synthetic test
identity. The sole historical image asset had no EXIF or personal metadata.
Release screenshots use a separate synthetic show with generic channel names.
Neither the development show nor locally installed Sound Backup source is part of
the publication.

The frontend dependency audit exposed two related moderate findings in Vitest's
development-only mocking tools. Updating to Vitest 4.1.11 resolved both; `npm audit`
then reported zero findings. The Intel environment initially resolved older
cryptography and Zeroconf wheels with known vulnerabilities. Both were upgraded
to patched source builds, with OpenSSL linked statically for cryptography.
`pip-audit` then reported no known vulnerabilities for either architecture's
installed Python dependency inventory. Minimum patched dependency versions are
required by the source requirements and the Intel release workflow.

Raw inventories, scanner reports, downloaded old installers, temporary show data
and build environments remain in ignored local directories. Only this summary
and the intended source and screenshots are published. Local checkpoint and audit
refs are not pushed.

## Distribution checks

The alpha includes Apple silicon and Intel disk images, drag-to-Applications
installation, SHA-256 checksums, bundled license notices and a matching public
source tag. Shows and photos live outside the app bundle, so quitting and replacing
the `.app` preserves them. macOS 14 or newer is required by bundled native audio
libraries. These builds are ad-hoc signed and are not Apple notarized.

Backend and frontend tests, frozen app startup, audio-engine/meter operation,
archive round trips with photos and mic-check ticks, quit/relaunch, and replacing
the app while retaining show data were checked. Sound Backup's actual network
provider was exercised against Mic-Wise's health and archive endpoints. Intel
runtime checks used Rosetta on Apple silicon; physical Intel hardware and a live
show audio interface still require operator testing.

This records the review performed, not a guarantee that scanners or manual review
can detect every possible sensitive string. Deleted external refs, unreachable
objects and other people's machines are outside its scope.
