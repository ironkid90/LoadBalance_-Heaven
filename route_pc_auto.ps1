param(
    [ValidateSet("apply", "ensure", "remove", "status")]
    [string]$Action = "apply",
    [string]$TargetIp = "192.168.0.60"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = (Get-Command python).Source
$scriptPath = Join-Path $scriptDir "router_policy_route.py"

$arguments = @($scriptPath, $Action, "--ppp-if", "auto")
if ($Action -ne "status") {
    $arguments += @("--target-ip", $TargetIp)
}

& $python @arguments
exit $LASTEXITCODE
