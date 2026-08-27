package edge_lifeline.phase5_test

import data.edge_lifeline.phase5
import rego.v1

mock_runtime := {
	"config": {
		"labels": {
			"policy_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			"policy_version": "phase5-policy-v1",
		},
	},
}

valid_input := {
	"identity": {"eligible": true},
	"time": {"active": true},
	"action": "dispense",
	"resource": "pump-1",
	"authority": {
		"actions": ["dispense"],
		"resources": ["pump-1"],
	},
	"required_policy_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
	"required_policy_version": "phase5-policy-v1",
}

test_valid_input_allowed if {
	result := phase5.result with input as valid_input with opa.runtime as mock_runtime
	result.allow
	result.decision == "CONTINUE_LOCALLY"
}

test_stale_policy_hash_denied if {
	request := object.union(valid_input, {
		"required_policy_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
	})
	result := phase5.result with input as request with opa.runtime as mock_runtime
	not result.allow
}

test_stale_policy_version_denied if {
	request := object.union(valid_input, {"required_policy_version": "phase5-policy-v0"})
	result := phase5.result with input as request with opa.runtime as mock_runtime
	not result.allow
}

test_ineligible_identity_denied if {
	request := object.union(valid_input, {"identity": {"eligible": false}})
	result := phase5.result with input as request with opa.runtime as mock_runtime
	not result.allow
}

test_inactive_time_denied if {
	request := object.union(valid_input, {"time": {"active": false}})
	result := phase5.result with input as request with opa.runtime as mock_runtime
	not result.allow
}

test_action_outside_authority_denied if {
	request := object.union(valid_input, {"action": "administer"})
	result := phase5.result with input as request with opa.runtime as mock_runtime
	not result.allow
}

test_resource_outside_authority_denied if {
	request := object.union(valid_input, {"resource": "pump-2"})
	result := phase5.result with input as request with opa.runtime as mock_runtime
	not result.allow
}
