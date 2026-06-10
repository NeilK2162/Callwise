# Create (or update) the five Callwise server tools in ElevenLabs via the public API.
# Bypasses the portal JSON editor entirely. Idempotent: re-running updates existing tools
# by name - so after a tunnel URL change, just re-run this and every tool URL is fixed.
#
# Usage:
#   $env:ELEVENLABS_API_KEY = 'xi-...'   # or let the script prompt you
#   .\elevenlabs_tools.ps1
#
# Reads BASE_URL and AGENT_TOOLS_SECRET from .env automatically.
# After it runs: ElevenLabs portal -> your agent -> Tools -> Add tool -> pick the five
# workspace tools it created (check_availability, check_time, book_appointment,
# take_message, mark_do_not_contact).

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# --- read .env -------------------------------------------------------------
function Read-DotEnv([string]$Path) {
    $map = @{}
    if (-not (Test-Path $Path)) { return $map }
    foreach ($line in Get-Content $Path) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $k, $v = $line.Split('=', 2)
        $v = $v.Trim()
        # strip inline comments (everything from first ' #' onward) and quotes
        $hash = $v.IndexOf(' #')
        if ($hash -ge 0) { $v = $v.Substring(0, $hash) }
        $v = $v.Trim().Trim('"').Trim("'")
        $map[$k.Trim()] = $v
    }
    return $map
}

$envFile = Join-Path $PSScriptRoot '.env'
$dotenv  = Read-DotEnv $envFile
$baseUrl = $dotenv['BASE_URL']
$secret  = $dotenv['AGENT_TOOLS_SECRET']
if (-not $baseUrl)  { Write-Error "BASE_URL missing in .env"; exit 1 }
if (-not $secret)   { Write-Error "AGENT_TOOLS_SECRET missing in .env"; exit 1 }
$baseUrl = $baseUrl.TrimEnd('/')

$apiKey = $env:ELEVENLABS_API_KEY
if (-not $apiKey) { $apiKey = Read-Host 'Paste your ElevenLabs API key (xi-...)' }
$headers = @{ 'xi-api-key' = $apiKey }
$api = 'https://api.elevenlabs.io/v1/convai/tools'

Write-Host "Tool base URL : $baseUrl" -ForegroundColor Cyan
Write-Host ""

# --- tool definitions (public API shape: properties = map, required = array) ---
function New-SysParams {
    # NOTE: the API allows only ONE of description | dynamic_variable | constant_value |
    # is_system_provided | is_omitted per property - so variable-bound params get NO description.
    return @{
        conversation_id = @{ type = 'string'; dynamic_variable = 'system__conversation_id' }
        caller_id       = @{ type = 'string'; dynamic_variable = 'system__caller_id' }
    }
}

$tools = @(
    @{
        name = 'check_availability'
        description = 'Read the next open appointment slots when the caller is flexible about timing. Returns spoken options plus slots[] with slot_iso values to pass to book_appointment.'
        endpoint = '/api/v2/agent-tools/check-availability'
        disable_interruptions = $false
        required = @('conversation_id', 'caller_id')
        props = (New-SysParams) + @{
            preference = @{ type = 'string'; description = "The caller's natural-language timing preference, e.g. 'Saturday morning' or 'next week', if they stated one." }
        }
    },
    @{
        name = 'check_time'
        description = 'Check whether ONE specific time the caller named is open (e.g. Thursday at 3). Confirms it or returns the nearest alternatives that day. Use check_availability instead when the caller is flexible.'
        endpoint = '/api/v2/agent-tools/check-time'
        disable_interruptions = $false
        required = @('desired_iso', 'conversation_id', 'caller_id')
        props = (New-SysParams) + @{
            desired_iso = @{ type = 'string'; description = 'The exact time the caller asked for, as ISO-8601 local clinic time, e.g. 2026-06-12T15:00:00. Derive the date from the conversation (today/tomorrow/Thursday).' }
        }
    },
    @{
        name = 'book_appointment'
        description = 'Book the appointment. Call ONLY after the caller confirmed a specific slot AND you read their full name and email back and they said yes. Use the slot_iso exactly as returned by check_availability or check_time.'
        endpoint = '/api/v2/agent-tools/book-appointment'
        disable_interruptions = $true
        required = @('name', 'email', 'slot_iso', 'conversation_id', 'caller_id')
        props = (New-SysParams) + @{
            name     = @{ type = 'string'; description = "Caller's full name, confirmed by reading it back." }
            email    = @{ type = 'string'; description = "Caller's email address, confirmed by reading it back letter-perfect." }
            slot_iso = @{ type = 'string'; description = 'The chosen slot ISO start time, copied EXACTLY from a slot_iso returned by check_availability or check_time.' }
        }
    },
    @{
        name = 'take_message'
        description = 'Capture a callback message when you cannot complete the request live: no suitable time, caller will not give an email, reschedule or cancel an existing appointment, wants a human, or a question you cannot answer.'
        endpoint = '/api/v2/agent-tools/take-message'
        disable_interruptions = $false
        required = @('name', 'reason', 'conversation_id', 'caller_id')
        props = (New-SysParams) + @{
            name            = @{ type = 'string'; description = "The caller's name." }
            reason          = @{ type = 'string'; description = 'One of: no_suitable_time | book_no_email | reschedule | cancel | wants_human | question.' }
            details         = @{ type = 'string'; description = 'The specifics: the question asked, the time they wanted, etc.' }
            callback_window = @{ type = 'string'; description = 'When they would like to be called back, if they said (e.g. after 5pm).' }
        }
    },
    @{
        name = 'mark_do_not_contact'
        description = 'Honor a request to stop being contacted (stop calling me / remove me from your list). Call immediately when asked, confirm warmly, then end the call.'
        endpoint = '/api/v2/agent-tools/do-not-contact'
        disable_interruptions = $false
        required = @('conversation_id', 'caller_id')
        props = (New-SysParams)
    }
)

# --- list existing tools (for idempotent update-by-name; paginated) ---------
$existing = @{}
try {
    $cursor = $null
    do {
        $uri = $api
        if ($cursor) { $uri = "$api`?cursor=$cursor" }
        $list = Invoke-RestMethod -Method Get -Uri $uri -Headers $headers -TimeoutSec 30
        foreach ($t in $list.tools) { $existing[$t.tool_config.name] = $t.id }
        $cursor = $null
        if ($list.has_more) { $cursor = $list.next_cursor }
    } while ($cursor)
} catch {
    Write-Host "WARN: could not list existing tools ($($_.Exception.Message)) - will try plain creates." -ForegroundColor Yellow
}

$ours = @($tools | Where-Object { $existing.ContainsKey($_.name) })
if ($ours.Count -gt 0) {
    Write-Host ("Found {0} existing Callwise tool(s) - updating them IN PLACE with the URL above." -f $ours.Count) -ForegroundColor Cyan
    Write-Host ""
}

# --- create or update each tool ---------------------------------------------
$results = @()
foreach ($t in $tools) {
    $config = @{
        type = 'webhook'
        name = $t.name
        description = $t.description
        response_timeout_secs = 20
        disable_interruptions = $t.disable_interruptions
        api_schema = @{
            url = "$baseUrl$($t.endpoint)"
            method = 'POST'
            request_headers = @{ 'X-Callwise-Agent-Secret' = $secret }
            request_body_schema = @{
                type = 'object'
                description = "$($t.name) request"
                required = $t.required
                properties = $t.props
            }
        }
    }
    $body = @{ tool_config = $config } | ConvertTo-Json -Depth 15

    $toolUrl = "$baseUrl$($t.endpoint)"
    try {
        if ($existing.ContainsKey($t.name)) {
            $id = $existing[$t.name]
            $r = Invoke-RestMethod -Method Patch -Uri "$api/$id" -Headers $headers -ContentType 'application/json' -Body $body -TimeoutSec 30
            $confirmed = $r.tool_config.api_schema.url   # read back what the portal now has
            if ($confirmed -eq $toolUrl) {
                $results += "UPDATED  $($t.name)  ->  $confirmed"
            } else {
                $results += "FAILED   $($t.name)  -> PATCH returned unexpected url: $confirmed"
            }
        } else {
            $r = Invoke-RestMethod -Method Post -Uri $api -Headers $headers -ContentType 'application/json' -Body $body -TimeoutSec 30
            $results += "CREATED  $($t.name)  (id: $($r.id))  ->  $toolUrl"
        }
    } catch {
        $detail = $_.ErrorDetails.Message
        if (-not $detail) { $detail = $_.Exception.Message }
        $results += "FAILED   $($t.name)  -> $detail"
    }
}

Write-Host ""
Write-Host "=== Results ===" -ForegroundColor Cyan
$results | ForEach-Object {
    $color = 'Green'
    if ($_ -like 'FAILED*') { $color = 'Red' }
    Write-Host $_ -ForegroundColor $color
}
Write-Host ""
Write-Host "If tools were CREATED: portal -> your agent -> Tools -> Add tool -> add the five workspace tools." -ForegroundColor Yellow
Write-Host "If tools were UPDATED: nothing to do in the portal for tools - the agent uses the new URLs immediately." -ForegroundColor Yellow
Write-Host "REMINDER after a tunnel URL change: the post-call webhook URL (Agents -> Settings ->" -ForegroundColor Yellow
Write-Host "Post-call webhooks) is NOT a tool - update that one in the portal by hand." -ForegroundColor Yellow
