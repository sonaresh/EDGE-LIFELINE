# Phase 7 limitations

- k3d simulates four K3s clusters on one Docker host; it is not four physical failure domains.
- Pod deletion and cluster restart are controlled mechanism tests, not production availability data.
- No AWS, EKS, hardware root of trust, physical edge device, or WAN impairment is evaluated.
- Kubernetes readiness does not establish identity, policy, time, lease, or effect authority.
- Reconnection never restores authority; a fresh connected-epoch lease is still required.
- Phase 7 evidence does not establish comparative outcomes. Those outcomes were evaluated
  separately under the accepted, preregistered Phase 8 protocol.
