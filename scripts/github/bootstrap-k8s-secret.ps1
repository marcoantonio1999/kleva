Param(
    [string]$Repo = "marcoantonio1999/kleva",
    [switch]$CheckOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Find-KubeConfigPath {
    $candidates = @(
        (Join-Path $HOME ".kube\config"),
        (Join-Path $HOME ".kube\config.yaml"),
        (Join-Path $HOME ".kube\kubeconfig")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

function Ensure-KubeContext {
    $contexts = kubectl config get-contexts -o name 2>$null
    if (-not $contexts) {
        throw @"
No Kubernetes context found.
Enable or create a cluster first (Docker Desktop Kubernetes, AKS, EKS, GKE, etc.).
Then rerun this script.
"@
    }

    $current = kubectl config current-context 2>$null
    if (-not $current) {
        kubectl config use-context ($contexts | Select-Object -First 1) | Out-Null
    }
}

$kubeConfig = Find-KubeConfigPath
if (-not $kubeConfig) {
    throw @"
Kubeconfig file not found in user profile.
Expected path: $HOME\.kube\config
Create/enable a Kubernetes cluster first, then rerun.
"@
}

Ensure-KubeContext

if ($CheckOnly) {
    Write-Output "Kubeconfig path: $kubeConfig"
    Write-Output "Current context: $(kubectl config current-context)"
    Write-Output "Existing repo secrets:"
    gh secret list --repo $Repo
    exit 0
}

$b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($kubeConfig))
gh secret set KUBE_CONFIG_B64 --repo $Repo --body $b64 | Out-Null

Write-Output "KUBE_CONFIG_B64 configured for $Repo"
Write-Output "Current context: $(kubectl config current-context)"
