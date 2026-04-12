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

$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$envPath = Join-Path $root "backend\.env"

Push-Location $root
try {
    docker compose --profile tunnel up -d --build

    $publicUrl = $null
    for ($i = 0; $i -lt 20; $i++) {
        $matches = docker compose logs --tail=300 cloudflared |
            Select-String -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -AllMatches |
            ForEach-Object { $_.Matches.Value }
        $publicUrl = $matches | Select-Object -Last 1
        if ($publicUrl) {
            break
        }
        Start-Sleep -Seconds 2
    }

    if (-not $publicUrl) {
        throw "Could not find a trycloudflare URL in cloudflared logs."
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
    Write-Output "Dashboard URL: http://localhost:5173"
    Write-Output "API health URL: http://localhost:8000/health"
}
finally {
    Pop-Location
}
