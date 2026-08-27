package edge_lifeline.phase5

import rego.v1

default allow := false

runtime_labels := object.get(object.get(opa.runtime(), "config", {}), "labels", {})
active_policy_hash := object.get(runtime_labels, "policy_hash", "")
active_policy_version := object.get(runtime_labels, "policy_version", "")

allow if {
	input.identity.eligible == true
	input.time.active == true
	input.action in input.authority.actions
	input.resource in input.authority.resources
	input.required_policy_hash == active_policy_hash
	input.required_policy_version == active_policy_version
}

decision := "CONTINUE_LOCALLY" if allow
decision := "DENY_UNSAFE_ACTION" if not allow

obligations := {
	"proof_before_effect": true,
	"record_policy_hash": active_policy_hash,
	"record_policy_version": active_policy_version,
}

result := {
	"allow": allow,
	"decision": decision,
	"obligations": obligations,
	"policy_hash": active_policy_hash,
	"policy_version": active_policy_version,
}
