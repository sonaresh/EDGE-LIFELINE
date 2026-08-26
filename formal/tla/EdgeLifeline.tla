---------------------------- MODULE EdgeLifeline ----------------------------
EXTENDS Naturals, FiniteSets, TLC

(***************************************************************************
Phase 2 finite abstraction. Cryptographic primitives are abstracted as
unforgeable/collision-free; COSE and Ed25519 byte verification begins in
Phase 3. Authority is a bounded product: normal authority, parent/child
authority, aggregate budget, time interval, nonce state, proof state,
isolation state, and a distinct emergency branch.
***************************************************************************)

CONSTANTS Edges, PrimaryEdge, Nonces, MaxAuthority, MaxBudget, MaxTime,
          MaxEpoch, EmergencyCeiling,
          CheckParent, UseConservativeTime, RememberNonces,
          ReconnectGrantsAuthority, RequireProof, AutoReplayEffects

ASSUME /\ Cardinality(Edges) = 3
       /\ PrimaryEdge \in Edges
       /\ Cardinality(Nonces) = 2
       /\ MaxAuthority = 2
       /\ MaxBudget = 2
       /\ MaxTime = 2
       /\ MaxEpoch = 2
       /\ EmergencyCeiling <= MaxAuthority

Modes == {"CONNECTED", "ISOLATED_BOUNDED", "DEGRADED_ESSENTIAL",
          "PROTECTIVE_READ_ONLY", "RECONCILIATION_PENDING",
          "QUARANTINED", "SAFE_SHUTDOWN"}
NoNonce == "NO_NONCE"
Bool == {TRUE, FALSE}

VARIABLES mode, epoch, authority, lastAuthority, parentAuthority,
          childAuthority, childDepth, reservedOne, reservedTwo, consumed,
          timeLower, timeUpper, rebooted, usedNonce, effectCount,
          decisionNonce, proofCommitted, effectExecuted,
          reconnectSnapshot, overrideActive, overrideAuthority,
          overrideConsumed, freshAuthorityReceived,
          physicalEffects, replayedEffects

vars == <<mode, epoch, authority, lastAuthority, parentAuthority,
          childAuthority, childDepth, reservedOne, reservedTwo, consumed,
          timeLower, timeUpper, rebooted, usedNonce, effectCount,
          decisionNonce, proofCommitted, effectExecuted,
          reconnectSnapshot, overrideActive, overrideAuthority,
          overrideConsumed, freshAuthorityReceived,
          physicalEffects, replayedEffects>>

Init ==
    /\ mode = [e \in Edges |-> "CONNECTED"]
    /\ epoch = [e \in Edges |-> 1]
    /\ authority = [e \in Edges |->
          IF e = PrimaryEdge THEN MaxAuthority - 1 ELSE MaxAuthority]
    /\ lastAuthority = [e \in Edges |->
          IF e = PrimaryEdge THEN MaxAuthority - 1 ELSE MaxAuthority]
    /\ parentAuthority = [e \in Edges |->
          IF e = PrimaryEdge THEN MaxAuthority - 1 ELSE MaxAuthority]
    /\ childAuthority = [e \in Edges |-> 0]
    /\ childDepth = [e \in Edges |-> 0]
    /\ reservedOne = [e \in Edges |-> 0]
    /\ reservedTwo = [e \in Edges |-> 0]
    /\ consumed = [e \in Edges |-> 0]
    /\ timeLower = [e \in Edges |-> 0]
    /\ timeUpper = [e \in Edges |-> 0]
    /\ rebooted = [e \in Edges |-> FALSE]
    /\ usedNonce = [e \in Edges |-> {}]
    /\ effectCount = [e \in Edges |-> [n \in Nonces |-> 0]]
    /\ decisionNonce = [e \in Edges |-> NoNonce]
    /\ proofCommitted = [e \in Edges |-> FALSE]
    /\ effectExecuted = [e \in Edges |-> FALSE]
    /\ reconnectSnapshot = [e \in Edges |->
          IF e = PrimaryEdge THEN MaxAuthority - 1 ELSE MaxAuthority]
    /\ overrideActive = [e \in Edges |-> FALSE]
    /\ overrideAuthority = [e \in Edges |-> 0]
    /\ overrideConsumed = [e \in Edges |-> FALSE]
    /\ freshAuthorityReceived = [e \in Edges |-> FALSE]
    /\ physicalEffects = [e \in Edges |-> 0]
    /\ replayedEffects = [e \in Edges |-> 0]

Disconnect(e) ==
    /\ mode[e] = "CONNECTED"
    /\ mode' = [mode EXCEPT ![e] = "ISOLATED_BOUNDED"]
    /\ UNCHANGED <<epoch, authority, lastAuthority, parentAuthority,
                    childAuthority, childDepth, reservedOne, reservedTwo,
                    consumed, timeLower, timeUpper, rebooted, usedNonce,
                    effectCount, decisionNonce, proofCommitted,
                    effectExecuted, reconnectSnapshot, overrideActive,
                    overrideAuthority, overrideConsumed, freshAuthorityReceived,
                    physicalEffects, replayedEffects>>

Degrade(e) ==
    /\ mode[e] \in {"ISOLATED_BOUNDED", "DEGRADED_ESSENTIAL"}
    /\ authority[e] > 0
    /\ mode' = [mode EXCEPT ![e] =
          IF @ = "ISOLATED_BOUNDED" THEN "DEGRADED_ESSENTIAL"
          ELSE "PROTECTIVE_READ_ONLY"]
    /\ authority' = [authority EXCEPT ![e] = @ - 1]
    /\ lastAuthority' = [lastAuthority EXCEPT ![e] = authority[e]]
    /\ UNCHANGED <<epoch, parentAuthority, childAuthority, childDepth,
                    reservedOne, reservedTwo, consumed, timeLower, timeUpper,
                    rebooted, usedNonce, effectCount, decisionNonce,
                    proofCommitted, effectExecuted, reconnectSnapshot,
                    overrideActive, overrideAuthority, overrideConsumed,
                    freshAuthorityReceived, physicalEffects, replayedEffects>>

Tick(e) ==
    /\ timeUpper[e] < MaxTime
    /\ LET nextUpper == timeUpper[e] + 1 IN
       /\ timeUpper' = [timeUpper EXCEPT ![e] = nextUpper]
       /\ timeLower' = [timeLower EXCEPT ![e] =
             IF timeLower[e] < MaxTime THEN @ + 1 ELSE @]
       /\ authority' = [authority EXCEPT ![e] =
             IF nextUpper >= MaxTime THEN 0 ELSE @]
       /\ lastAuthority' = [lastAuthority EXCEPT ![e] = authority[e]]
       /\ effectExecuted' = [effectExecuted EXCEPT ![e] = FALSE]
       /\ mode' = [mode EXCEPT ![e] =
             IF nextUpper >= MaxTime THEN "PROTECTIVE_READ_ONLY" ELSE @]
    /\ UNCHANGED <<epoch, parentAuthority, childAuthority, childDepth,
                    reservedOne, reservedTwo, consumed, rebooted, usedNonce,
                    effectCount, decisionNonce, proofCommitted,
                    reconnectSnapshot, overrideActive,
                    overrideAuthority, overrideConsumed, freshAuthorityReceived,
                    physicalEffects, replayedEffects>>

Reboot(e) ==
    /\ mode[e] \notin {"CONNECTED", "SAFE_SHUTDOWN"}
    /\ rebooted' = [rebooted EXCEPT ![e] = TRUE]
    /\ timeLower' = [timeLower EXCEPT ![e] = 0]
    /\ timeUpper' = [timeUpper EXCEPT ![e] = IF UseConservativeTime THEN MaxTime ELSE 0]
    /\ authority' = [authority EXCEPT ![e] = IF UseConservativeTime THEN 0 ELSE @]
    /\ lastAuthority' = [lastAuthority EXCEPT ![e] = authority[e]]
    /\ effectExecuted' = [effectExecuted EXCEPT ![e] = FALSE]
    /\ mode' = [mode EXCEPT ![e] =
          IF UseConservativeTime THEN "PROTECTIVE_READ_ONLY" ELSE @]
    /\ UNCHANGED <<epoch, parentAuthority, childAuthority, childDepth,
                    reservedOne, reservedTwo, consumed, usedNonce, effectCount,
                    decisionNonce, proofCommitted,
                    reconnectSnapshot, overrideActive, overrideAuthority,
                    overrideConsumed, freshAuthorityReceived,
                    physicalEffects, replayedEffects>>

IssueChild(e) ==
    /\ e = PrimaryEdge
    /\ mode[e] \in {"ISOLATED_BOUNDED", "DEGRADED_ESSENTIAL"}
    /\ childDepth[e] < 2
    /\ \E a \in 0..MaxAuthority:
          /\ IF CheckParent THEN a <= parentAuthority[e] ELSE TRUE
          /\ childAuthority' = [childAuthority EXCEPT ![e] = a]
    /\ childDepth' = [childDepth EXCEPT ![e] = @ + 1]
    /\ UNCHANGED <<mode, epoch, authority, lastAuthority, parentAuthority,
                    reservedOne, reservedTwo, consumed, timeLower, timeUpper,
                    rebooted, usedNonce, effectCount, decisionNonce,
                    proofCommitted, effectExecuted, reconnectSnapshot,
                    overrideActive, overrideAuthority, overrideConsumed,
                    freshAuthorityReceived, physicalEffects, replayedEffects>>

ReserveSibling(e, slot, amount) ==
    /\ e = PrimaryEdge
    /\ slot \in {1, 2}
    /\ amount \in 0..MaxBudget
    /\ IF CheckParent
          THEN consumed[e] + reservedOne[e] + reservedTwo[e] + amount <= MaxBudget
          ELSE TRUE
    /\ IF slot = 1
          THEN /\ reservedOne' = [reservedOne EXCEPT ![e] = @ + amount]
               /\ UNCHANGED reservedTwo
          ELSE /\ reservedTwo' = [reservedTwo EXCEPT ![e] = @ + amount]
               /\ UNCHANGED reservedOne
    /\ UNCHANGED <<mode, epoch, authority, lastAuthority, parentAuthority,
                    childAuthority, childDepth, consumed, timeLower, timeUpper,
                    rebooted, usedNonce, effectCount, decisionNonce,
                    proofCommitted, effectExecuted, reconnectSnapshot,
                    overrideActive, overrideAuthority, overrideConsumed,
                    freshAuthorityReceived, physicalEffects, replayedEffects>>

Decide(e, n) ==
    /\ mode[e] \in {"ISOLATED_BOUNDED", "DEGRADED_ESSENTIAL",
                      "PROTECTIVE_READ_ONLY"}
    /\ authority[e] > 0
    /\ n \in Nonces
    /\ n \notin usedNonce[e]
    /\ IF UseConservativeTime THEN timeUpper[e] < MaxTime ELSE timeLower[e] < MaxTime
    /\ decisionNonce' = [decisionNonce EXCEPT ![e] = n]
    /\ usedNonce' = [usedNonce EXCEPT ![e] = IF RememberNonces THEN @ \cup {n} ELSE @]
    /\ proofCommitted' = [proofCommitted EXCEPT ![e] = FALSE]
    /\ effectExecuted' = [effectExecuted EXCEPT ![e] = FALSE]
    /\ UNCHANGED <<mode, epoch, authority, lastAuthority, parentAuthority,
                    childAuthority, childDepth, reservedOne, reservedTwo,
                    consumed, timeLower, timeUpper, rebooted, effectCount,
                    reconnectSnapshot, overrideActive, overrideAuthority,
                    overrideConsumed, freshAuthorityReceived,
                    physicalEffects, replayedEffects>>

CommitProof(e) ==
    /\ decisionNonce[e] \in Nonces
    /\ proofCommitted' = [proofCommitted EXCEPT ![e] = TRUE]
    /\ UNCHANGED <<mode, epoch, authority, lastAuthority, parentAuthority,
                    childAuthority, childDepth, reservedOne, reservedTwo,
                    consumed, timeLower, timeUpper, rebooted, usedNonce,
                    effectCount, decisionNonce, effectExecuted,
                    reconnectSnapshot, overrideActive, overrideAuthority,
                    overrideConsumed, freshAuthorityReceived,
                    physicalEffects, replayedEffects>>

Execute(e) ==
    /\ mode[e] \in {"ISOLATED_BOUNDED", "DEGRADED_ESSENTIAL",
                      "PROTECTIVE_READ_ONLY"}
    /\ decisionNonce[e] \in Nonces
    /\ IF RequireProof THEN proofCommitted[e] ELSE TRUE
    /\ IF UseConservativeTime THEN timeUpper[e] < MaxTime ELSE timeLower[e] < MaxTime
    /\ IF RememberNonces THEN effectCount[e][decisionNonce[e]] = 0 ELSE TRUE
    /\ LET n == decisionNonce[e] IN
       effectCount' = [effectCount EXCEPT ![e][n] = @ + 1]
    /\ effectExecuted' = [effectExecuted EXCEPT ![e] = TRUE]
    /\ physicalEffects' = [physicalEffects EXCEPT ![e] = @ + 1]
    /\ UNCHANGED <<mode, epoch, authority, lastAuthority, parentAuthority,
                    childAuthority, childDepth, reservedOne, reservedTwo,
                    consumed, timeLower, timeUpper, rebooted, usedNonce,
                    decisionNonce, proofCommitted, reconnectSnapshot,
                    overrideActive, overrideAuthority, overrideConsumed,
                    freshAuthorityReceived, replayedEffects>>

ReplayAttempt(e) ==
    /\ decisionNonce[e] \in Nonces
    /\ effectCount[e][decisionNonce[e]] > 0
    /\ IF RememberNonces
          THEN UNCHANGED <<effectCount, physicalEffects>>
          ELSE /\ LET n == decisionNonce[e] IN
                    effectCount' = [effectCount EXCEPT ![e][n] = @ + 1]
               /\ physicalEffects' = [physicalEffects EXCEPT ![e] = @ + 1]
    /\ UNCHANGED <<mode, epoch, authority, lastAuthority, parentAuthority,
                    childAuthority, childDepth, reservedOne, reservedTwo,
                    consumed, timeLower, timeUpper, rebooted, usedNonce,
                    decisionNonce, proofCommitted, effectExecuted,
                    reconnectSnapshot, overrideActive, overrideAuthority,
                    overrideConsumed, freshAuthorityReceived, replayedEffects>>

Reconnect(e) ==
    /\ mode[e] \in {"ISOLATED_BOUNDED", "DEGRADED_ESSENTIAL",
                      "PROTECTIVE_READ_ONLY"}
    /\ reconnectSnapshot' = [reconnectSnapshot EXCEPT ![e] = authority[e]]
    /\ mode' = [mode EXCEPT ![e] = "RECONCILIATION_PENDING"]
    /\ authority' = [authority EXCEPT ![e] =
          IF ReconnectGrantsAuthority THEN MaxAuthority ELSE @]
    /\ lastAuthority' = [lastAuthority EXCEPT ![e] = authority[e]]
    /\ freshAuthorityReceived' = [freshAuthorityReceived EXCEPT ![e] = FALSE]
    /\ decisionNonce' = [decisionNonce EXCEPT ![e] = NoNonce]
    /\ proofCommitted' = [proofCommitted EXCEPT ![e] = FALSE]
    /\ effectExecuted' = [effectExecuted EXCEPT ![e] = FALSE]
    /\ UNCHANGED <<epoch, parentAuthority, childAuthority, childDepth,
                    reservedOne, reservedTwo, consumed, timeLower, timeUpper,
                    rebooted, usedNonce, effectCount, overrideActive,
                    overrideAuthority, overrideConsumed,
                    physicalEffects, replayedEffects>>

ReceiveFreshAuthority(e) ==
    /\ mode[e] = "RECONCILIATION_PENDING"
    /\ freshAuthorityReceived' = [freshAuthorityReceived EXCEPT ![e] = TRUE]
    /\ UNCHANGED <<mode, epoch, authority, lastAuthority, parentAuthority,
                    childAuthority, childDepth, reservedOne, reservedTwo,
                    consumed, timeLower, timeUpper, rebooted, usedNonce,
                    effectCount, decisionNonce, proofCommitted, effectExecuted,
                    reconnectSnapshot, overrideActive, overrideAuthority,
                    overrideConsumed, physicalEffects, replayedEffects>>

ReconcileNewEpoch(e) ==
    /\ mode[e] = "RECONCILIATION_PENDING"
    /\ epoch[e] < MaxEpoch
    /\ freshAuthorityReceived[e]
    /\ mode' = [mode EXCEPT ![e] = "CONNECTED"]
    /\ epoch' = [epoch EXCEPT ![e] = @ + 1]
    /\ authority' = [authority EXCEPT ![e] = parentAuthority[e]]
    /\ lastAuthority' = [lastAuthority EXCEPT ![e] = parentAuthority[e]]
    /\ timeLower' = [timeLower EXCEPT ![e] = 0]
    /\ timeUpper' = [timeUpper EXCEPT ![e] = 0]
    /\ rebooted' = [rebooted EXCEPT ![e] = FALSE]
    /\ usedNonce' = [usedNonce EXCEPT ![e] = {}]
    /\ decisionNonce' = [decisionNonce EXCEPT ![e] = NoNonce]
    /\ proofCommitted' = [proofCommitted EXCEPT ![e] = FALSE]
    /\ effectExecuted' = [effectExecuted EXCEPT ![e] = FALSE]
    /\ freshAuthorityReceived' = [freshAuthorityReceived EXCEPT ![e] = FALSE]
    /\ overrideConsumed' = [overrideConsumed EXCEPT ![e] = FALSE]
    /\ IF AutoReplayEffects
          THEN /\ physicalEffects' = [physicalEffects EXCEPT ![e] = @ + 1]
               /\ replayedEffects' = [replayedEffects EXCEPT ![e] = @ + 1]
          ELSE /\ UNCHANGED <<physicalEffects, replayedEffects>>
    /\ UNCHANGED <<parentAuthority, childAuthority, childDepth,
                    reservedOne, reservedTwo, consumed, effectCount,
                    reconnectSnapshot, overrideActive, overrideAuthority>>

Quarantine(e) ==
    /\ mode[e] \notin {"QUARANTINED", "SAFE_SHUTDOWN"}
    /\ mode' = [mode EXCEPT ![e] = "QUARANTINED"]
    /\ authority' = [authority EXCEPT ![e] = 0]
    /\ lastAuthority' = [lastAuthority EXCEPT ![e] = authority[e]]
    /\ decisionNonce' = [decisionNonce EXCEPT ![e] = NoNonce]
    /\ proofCommitted' = [proofCommitted EXCEPT ![e] = FALSE]
    /\ effectExecuted' = [effectExecuted EXCEPT ![e] = FALSE]
    /\ UNCHANGED <<epoch, parentAuthority, childAuthority, childDepth,
                    reservedOne, reservedTwo, consumed, timeLower, timeUpper,
                    rebooted, usedNonce, effectCount, reconnectSnapshot,
                    overrideActive, overrideAuthority, overrideConsumed,
                    freshAuthorityReceived, physicalEffects, replayedEffects>>

ActivateOverride(e, a) ==
    /\ ~overrideActive[e]
    /\ ~overrideConsumed[e]
    /\ a \in 0..EmergencyCeiling
    /\ overrideActive' = [overrideActive EXCEPT ![e] = TRUE]
    /\ overrideAuthority' = [overrideAuthority EXCEPT ![e] = a]
    /\ UNCHANGED <<mode, epoch, authority, lastAuthority, parentAuthority,
                    childAuthority, childDepth, reservedOne, reservedTwo,
                    consumed, timeLower, timeUpper, rebooted, usedNonce,
                    effectCount, decisionNonce, proofCommitted,
                    effectExecuted, reconnectSnapshot, overrideConsumed,
                    freshAuthorityReceived, physicalEffects, replayedEffects>>

ConsumeOverride(e) ==
    /\ overrideActive[e]
    /\ overrideActive' = [overrideActive EXCEPT ![e] = FALSE]
    /\ overrideAuthority' = [overrideAuthority EXCEPT ![e] = 0]
    /\ overrideConsumed' = [overrideConsumed EXCEPT ![e] = TRUE]
    /\ UNCHANGED <<mode, epoch, authority, lastAuthority, parentAuthority,
                    childAuthority, childDepth, reservedOne, reservedTwo,
                    consumed, timeLower, timeUpper, rebooted, usedNonce,
                    effectCount, decisionNonce, proofCommitted,
                    effectExecuted, reconnectSnapshot, freshAuthorityReceived,
                    physicalEffects, replayedEffects>>

Next ==
    \/ \E e \in Edges: Disconnect(e)
    \/ Degrade(PrimaryEdge)
    \/ Tick(PrimaryEdge)
    \/ Reboot(PrimaryEdge)
    \/ IssueChild(PrimaryEdge)
    \/ \E s \in {1, 2}, a \in 0..MaxBudget: ReserveSibling(PrimaryEdge, s, a)
    \/ \E n \in Nonces: Decide(PrimaryEdge, n)
    \/ CommitProof(PrimaryEdge)
    \/ Execute(PrimaryEdge)
    \/ ReplayAttempt(PrimaryEdge)
    \/ Reconnect(PrimaryEdge)
    \/ ReceiveFreshAuthority(PrimaryEdge)
    \/ ReconcileNewEpoch(PrimaryEdge)
    \/ \E e \in Edges: Quarantine(e)
    \/ \E a \in 0..EmergencyCeiling: ActivateOverride(PrimaryEdge, a)
    \/ ConsumeOverride(PrimaryEdge)

Spec == Init /\ [][Next]_vars

TypeOK ==
    /\ mode \in [Edges -> Modes]
    /\ epoch \in [Edges -> 1..MaxEpoch]
    /\ authority \in [Edges -> 0..MaxAuthority]
    /\ lastAuthority \in [Edges -> 0..MaxAuthority]
    /\ parentAuthority \in [Edges -> 0..MaxAuthority]
    /\ childAuthority \in [Edges -> 0..MaxAuthority]
    /\ childDepth \in [Edges -> 0..2]
    /\ reservedOne \in [Edges -> 0..(2 * MaxBudget)]
    /\ reservedTwo \in [Edges -> 0..(2 * MaxBudget)]
    /\ consumed \in [Edges -> 0..MaxBudget]
    /\ timeLower \in [Edges -> 0..MaxTime]
    /\ timeUpper \in [Edges -> 0..MaxTime]
    /\ rebooted \in [Edges -> Bool]
    /\ usedNonce \in [Edges -> SUBSET Nonces]
    /\ effectCount \in [Edges -> [Nonces -> 0..2]]
    /\ decisionNonce \in [Edges -> (Nonces \cup {NoNonce})]
    /\ proofCommitted \in [Edges -> Bool]
    /\ effectExecuted \in [Edges -> Bool]
    /\ reconnectSnapshot \in [Edges -> 0..MaxAuthority]
    /\ overrideActive \in [Edges -> Bool]
    /\ overrideAuthority \in [Edges -> 0..EmergencyCeiling]
    /\ overrideConsumed \in [Edges -> Bool]
    /\ freshAuthorityReceived \in [Edges -> Bool]

I1_MonotonicContraction ==
    \A e \in Edges: authority[e] <= lastAuthority[e]

I2_ParentBounded ==
    \A e \in Edges: /\ authority[e] <= parentAuthority[e]
                       /\ childAuthority[e] <= parentAuthority[e]

I4_ConservativeTime ==
    \A e \in Edges: effectExecuted[e] => (~rebooted[e] /\ timeUpper[e] < MaxTime)

I5_AntiReplay ==
    \A e \in Edges: \A n \in Nonces: effectCount[e][n] <= 1

I6_ProofBeforeEffect ==
    \A e \in Edges: effectExecuted[e] => proofCommitted[e]

I9_NoReconnectGrant ==
    \A e \in Edges: mode[e] = "RECONCILIATION_PENDING" =>
                       authority[e] <= reconnectSnapshot[e]

I10_NoAutomaticEffectReplay ==
    \A e \in Edges: replayedEffects[e] = 0

I11_OverrideBounded ==
    \A e \in Edges: /\ overrideAuthority[e] <= EmergencyCeiling
                       /\ overrideActive[e] => authority[e] <= lastAuthority[e]

I12_OverrideOneShot ==
    \A e \in Edges: overrideConsumed[e] => ~overrideActive[e]

I13_EffectStateSafe ==
    \A e \in Edges: effectExecuted[e] =>
        mode[e] \in {"ISOLATED_BOUNDED", "DEGRADED_ESSENTIAL",
                      "PROTECTIVE_READ_ONLY"}

I15_AggregateChildBudget ==
    \A e \in Edges: consumed[e] + reservedOne[e] + reservedTwo[e] <= MaxBudget

I16_IssuerCeiling ==
    \A e \in Edges: parentAuthority[e] <= MaxAuthority

=============================================================================
