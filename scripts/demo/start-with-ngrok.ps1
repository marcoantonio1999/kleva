Param(
    [switch]$NoTwilioUpdate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-EnvMap {
    param([string]$Path)
    $map = @{}
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            return
        }
        $parts = $line.Split("=", 2)
        $map[$parts[0].Trim()] = $parts[1].Trim()
    }
    return $map
}

function Set-EnvValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Value
    )
    $content = Get-Content $Path -Raw
    $pattern = "(?m)^" + [regex]::Escape($Key) + "=.*$"
    if ([regex]::IsMatch($content, $pattern)) {
        $updated = [regex]::Replace($content, $pattern, "$Key=$Value")
    } else {
        $updated = $content.TrimEnd() + "`r`n$Key=$Value`r`n"
    }
    Set-Content -Path $Path -Value $updated -NoNewline
}

function Update-TwilioWebhook {
    param(
        [string]$EnvPath,
        [string]$VoiceWebhookUrl
    )

    $envMap = Get-EnvMap -Path $EnvPath
    $sid = $envMap["TWILIO_ACCOUNT_SID"]
    $token = $envMap["TWILIO_AUTH_TOKEN"]
    $phoneSid = $envMap["TWILIO_PHONE_NUMBER_SID"]

    if (-not $sid -or -not $token -or -not $phoneSid) {
        throw "Missing TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, or TWILIO_PHONE_NUMBER_SID in backend/.env"
    }

    $pair = "{0}:{1}" -f $sid, $token
    $basic = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($pair))
    $headers = @{ Authorization = "Basic $basic" }
    $api = "https://api.twilio.com/2010-04-01/Accounts/$sid/IncomingPhoneNumbers/$phoneSid.json"
    $body = @{ VoiceUrl = $VoiceWebhookUrl; VoiceMethod = "POST" }

    $resp = Invoke-RestMethod -Method Post -Uri $api -Headers $headers -Body $body
    return $resp.voice_url
}

if ([string]::IsNullOrWhiteSpace($env:NGROK_AUTHTOKEN)) {
    throw "NGROK_AUTHTOKEN is required in environment for the ngrok compose profile."
}

$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$envPath = Join-Path $root "backend\.env"

Push-Location $root
try {
    docker compose --profile ngrok up -d --build

    $publicUrl = $null
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $tunnels = Invoke-RestMethod -Method Get -Uri "http://localhost:4040/api/tunnels"
            $httpsTunnel = $tunnels.tunnels | Where-Object { $_.public_url -like "https://*" } | Select-Object -First 1
            if ($httpsTunnel) {
                $publicUrl = $httpsTunnel.public_url
                break
            }
        }
        catch {
            # Keep waiting for ngrok API.
        }
        Start-Sleep -Seconds 2
    }

    if (-not $publicUrl) {
        throw "Could not get ngrok public URL from http://localhost:4040/api/tunnels"
    }

    Set-EnvValue -Path $envPath -Key "PUBLIC_BASE_URL" -Value $publicUrl
    docker compose up -d backend | Out-Null

    $webhookUrl = "$publicUrl/twilio/voice"
    if (-not $NoTwilioUpdate) {
        $updatedWebhook = Update-TwilioWebhook -EnvPath $envPath -VoiceWebhookUrl $webhookUrl
        Write-Output "Twilio webhook updated: $updatedWebhook"
    }

    Write-Output ""
    Write-Output "Public backend URL: $publicUrl"
    Write-Output "Twilio webhook URL: $webhookUrl"
    Write-Output "Ngrok inspector: http://localhost:4040"
    Write-Output "Dashboard URL: http://localhost:5173"
    Write-Output "API health URL: http://localhost:8000/health"
}
finally {
    Pop-Location
}
