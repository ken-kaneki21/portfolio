param(
    [Parameter(Mandatory=$true)][string]$ModelFile,
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$ModelFile = (Resolve-Path -LiteralPath $ModelFile).Path
$Python = (Resolve-Path -LiteralPath $Python).Path
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$image = 'ghcr.io/ggml-org/llama.cpp:server@sha256:7751a6c0dc3d019c231d42678abbb0fac1a13a24c17c956109ed27533139f280'
$expected = '6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e'
$name = 'qwen-loopback-bench-' + [guid]::NewGuid().ToString('N').Substring(0,12)
$record = [ordered]@{status='blocked'; stage='model_hash'; image=$image; model_sha256=$null}
$started = $false
$code = 2
try {
    $record.model_sha256 = (Get-FileHash -LiteralPath $ModelFile -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($record.model_sha256 -ne $expected) { throw 'Model hash differs from accepted Healthcare Qwen artifact' }
    $record.stage = 'docker_engine'
    $engine = & docker version --format '{{.Server.Version}}' 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($engine -join ' ') }
    $record.docker_server = "$engine"
    $record.stage = 'pinned_local_image'
    $imageId = & docker image inspect --format '{{.Id}}' $image 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Accepted pinned image is unavailable locally' }
    $record.image_id = "$imageId"
    $record.stage = 'start_loopback'
    & docker run --detach --rm --pull=never --name $name --publish '127.0.0.1::8080' `
        --mount "type=bind,source=$ModelFile,target=/models/qwen.gguf,readonly" $image `
        --model /models/qwen.gguf --alias qwen2.5-1.5b-instruct-q4_k_m --host 0.0.0.0 --port 8080 `
        --ctx-size 2048 --parallel 1 --threads 5 --n-gpu-layers 0 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Pinned loopback container did not start' }
    $started = $true
    $mapping = & docker port $name 8080/tcp
    if ($LASTEXITCODE -ne 0 -or "$mapping" -notmatch '^127\.0\.0\.1:(\d+)$') {
        throw 'Container lacks an exclusive IPv4 loopback binding'
    }
    $port = [int]$Matches[1]
    $record.stage = 'readiness'
    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    $ready = $false
    do {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 2
            $ready = $health.status -eq 'ok'
        } catch { Start-Sleep -Milliseconds 500 }
    } until ($ready -or [DateTime]::UtcNow -ge $deadline)
    if (-not $ready) { throw 'Loopback health did not become ready' }
    $record.stage = 'streaming_benchmark'
    $client = Join-Path $PSScriptRoot '../experiments/qwen_http.py'
    & $Python $client --port $port --out (Join-Path $OutputDirectory 'benchmark.json') `
        --model-sha256 $record.model_sha256 --image $image
    $code = $LASTEXITCODE
    $record.status = if ($code -eq 0) { 'complete' } else { 'benchmark_failed' }
} catch {
    $record.error = $_.Exception.Message
    Write-Error -ErrorAction Continue $record.error
} finally {
    if ($started) {
        & docker logs --tail 80 $name 2>&1 | Set-Content (Join-Path $OutputDirectory 'server-local.log') -Encoding utf8
        & docker stop --time 5 $name | Out-Null
    }
    $record | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $OutputDirectory 'gate.json') -Encoding utf8
}
exit $code
