# Security policy

This is a research prototype, not a production or clinical system.

Do not commit credentials, private keys, patient information, cloud tokens, `.env` files, or real identity records. Report suspected vulnerabilities privately to the repository owner before public disclosure.

Phase 1 has no runtime secrets and no authority-granting endpoint. All published Compose ports bind to loopback. Containers run as UID 10001 with a read-only root filesystem, dropped Linux capabilities, and `no-new-privileges`.

No software-only guarantee survives compromise of the future verifier TCB and its keys. That boundary remains explicit throughout later phases.

