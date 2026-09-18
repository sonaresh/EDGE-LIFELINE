# Security policy

This is a research prototype, not a production or clinical system.

Do not commit credentials, private keys, patient information, cloud tokens, `.env` files, or real identity records. Report suspected vulnerabilities privately to the repository owner before public disclosure.

Phase 1 has no runtime secrets and no authority-granting endpoint. All published Compose ports bind to loopback. Containers run as UID 10001 with a read-only root filesystem, dropped Linux capabilities, and `no-new-privileges`.

No software-only guarantee survives compromise of the verifier TCB and its keys. The E9
full-TCB-compromise profile is detection-only; the project makes no prevention claim for that
case. This boundary remains explicit in the accepted v0.9.0 release.
