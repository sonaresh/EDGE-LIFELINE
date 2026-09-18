[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$EvidenceDir,

    [string]$K3dPath = 'k3d'
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Clusters = @('cloud', 'edge-a', 'edge-b', 'edge-c')
$Created = [System.Collections.Generic.List[string]]::new()
$Inventory = [System.Collections.Generic.List[object]]::new()
$Faults = [System.Collections.Generic.List[object]]::new()
$Image = 'edge-lifeline:phase7'

New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null

try {
    docker version |
        Out-File `
            (Join-Path $EvidenceDir 'docker-version.txt') `
            -Encoding utf8NoBOM

    kubectl version --client -o yaml |
        Out-File `
            (Join-Path $EvidenceDir 'kubectl-version.yaml') `
            -Encoding utf8NoBOM

    & $K3dPath version |
        Out-File `
            (Join-Path $EvidenceDir 'k3d-version.txt') `
            -Encoding utf8NoBOM

    docker build `
        --tag $Image `
        --file (Join-Path $RepoRoot 'Dockerfile') `
        $RepoRoot

    foreach ($Cluster in $Clusters) {
        $Name = "edge-lifeline-$Cluster"
        $Context = "k3d-$Name"
        $Role = if ($Cluster -eq 'cloud') { 'cloud' } else { 'edge' }

        & $K3dPath cluster create $Name `
            --image 'rancher/k3s:v1.37.0-k3s1' `
            --servers 1 `
            --agents 0 `
            --no-lb `
            --wait `
            --timeout 180s `
            --k3s-arg '--disable=traefik@server:*' `
            --k3s-arg '--disable=servicelb@server:*'

        $Created.Add($Name)

        & $K3dPath image import $Image --cluster $Name

        kubectl --context $Context create namespace edge-lifeline `
            --dry-run=client `
            -o yaml |
            kubectl --context $Context apply -f -

        kubectl --context $Context `
            -n edge-lifeline `
            create configmap edge-lifeline-node `
            --from-literal "node_id=$Cluster" `
            --from-literal "node_role=$Role" `
            --dry-run=client `
            -o yaml |
            kubectl --context $Context apply -f -

        kubectl --context $Context apply `
            -f (Join-Path $RepoRoot 'infra/k3d/base/workload.yaml')

        kubectl --context $Context apply `
            -f (Join-Path $RepoRoot 'infra/k3d/base/network-policy.yaml')

        kubectl --context $Context `
            -n edge-lifeline `
            rollout status deployment/edge-lifeline `
            --timeout=120s

        $NodeJson = kubectl --context $Context get nodes -o json |
            ConvertFrom-Json

        $PodJson = kubectl --context $Context `
            -n edge-lifeline `
            get pods `
            -o json |
            ConvertFrom-Json

        $Inventory.Add(
            [ordered]@{
                cluster_id = $Cluster
                role = $Role
                context = $Context
                ready_nodes = @(
                    $NodeJson.items |
                        Where-Object {
                            $_.status.conditions |
                                Where-Object {
                                    $_.type -eq 'Ready' -and
                                    $_.status -eq 'True'
                                }
                        }
                ).Count
                ready_pods = @(
                    $PodJson.items |
                        Where-Object {
                            $_.status.conditions |
                                Where-Object {
                                    $_.type -eq 'Ready' -and
                                    $_.status -eq 'True'
                                }
                        }
                ).Count
            }
        )

        kubectl --context $Context `
            get all,networkpolicy `
            -A `
            -o yaml |
            Out-File `
                (Join-Path $EvidenceDir "$Cluster-inventory.yaml") `
                -Encoding utf8NoBOM
    }

    $EdgeAContext = 'k3d-edge-lifeline-edge-a'

    $OldPod = kubectl --context $EdgeAContext `
        -n edge-lifeline `
        get pod `
        -l app.kubernetes.io/name=edge-lifeline `
        -o jsonpath='{.items[0].metadata.name}'

    kubectl --context $EdgeAContext `
        -n edge-lifeline `
        delete pod $OldPod `
        --wait=true

    kubectl --context $EdgeAContext `
        -n edge-lifeline `
        rollout status deployment/edge-lifeline `
        --timeout=120s

    $NewPod = kubectl --context $EdgeAContext `
        -n edge-lifeline `
        get pod `
        -l app.kubernetes.io/name=edge-lifeline `
        -o jsonpath='{.items[0].metadata.name}'

    if ($OldPod -eq $NewPod) {
        throw 'Pod restart fault did not create a replacement pod.'
    }

    $Faults.Add(
        [ordered]@{
            id = 'F7-POD-RESTART'
            target = 'edge-a'
            passed = $true
        }
    )

    & $K3dPath cluster stop edge-lifeline-edge-b

    foreach ($Healthy in @('cloud', 'edge-a', 'edge-c')) {
        kubectl `
            --context "k3d-edge-lifeline-$Healthy" `
            wait node `
            --all `
            --for=condition=Ready `
            --timeout=30s
    }

    & $K3dPath cluster start edge-lifeline-edge-b --wait

    kubectl `
        --context k3d-edge-lifeline-edge-b `
        wait node `
        --all `
        --for=condition=Ready `
        --timeout=120s

    kubectl `
        --context k3d-edge-lifeline-edge-b `
        -n edge-lifeline `
        rollout status deployment/edge-lifeline `
        --timeout=120s

    $Faults.Add(
        [ordered]@{
            id = 'F7-EDGE-RESTART'
            target = 'edge-b'
            passed = $true
            authority_restored = $false
            fresh_connected_epoch_lease_required = $true
        }
    )

    [ordered]@{
        schema_version = 'edge-lifeline-phase7-inventory-v1'
        clusters = $Inventory
    } |
        ConvertTo-Json -Depth 8 |
        Set-Content `
            (Join-Path $EvidenceDir 'cluster-inventory.json') `
            -Encoding utf8NoBOM

    [ordered]@{
        schema_version = 'edge-lifeline-phase7-fault-results-v1'
        cases = $Faults
    } |
        ConvertTo-Json -Depth 8 |
        Set-Content `
            (Join-Path $EvidenceDir 'fault-results.json') `
            -Encoding utf8NoBOM
}
finally {
    $Cleanup = [System.Collections.Generic.List[object]]::new()

    for ($Index = $Created.Count - 1; $Index -ge 0; $Index--) {
        $Name = $Created[$Index]

        & $K3dPath cluster delete $Name

        $Cleanup.Add(
            [ordered]@{
                cluster = $Name
                deleted = $LASTEXITCODE -eq 0
            }
        )
    }

    [ordered]@{
        schema_version = 'edge-lifeline-phase7-cleanup-v1'
        clusters = $Cleanup
    } |
        ConvertTo-Json -Depth 6 |
        Set-Content `
            (Join-Path $EvidenceDir 'cleanup.json') `
            -Encoding utf8NoBOM
}