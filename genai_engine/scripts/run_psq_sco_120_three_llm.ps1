param(
    [string]$PythonExe = "python",
    [string]$SitePackages = "",
    [string]$KbDir = (Join-Path (Split-Path -Parent $PSScriptRoot) "output"),
    [string]$RagProfile = "quality",
    [string]$OutputRoot = "output\psq_sco_120_three_llm_full",
    [int]$Limit = 0
)

$ErrorActionPreference = "Continue"

$models = @(
    "qwen2_5_7b",
    "qwen3_8b",
    "mistral_7b"
)

if ($SitePackages) {
    $env:PYTHONPATH = $SitePackages
}
$env:PSQ_KB_DIR = $KbDir
$env:PSQ_RAG_PROFILE = $RagProfile

$startedAt = Get-Date
$batchId = $startedAt.ToString("yyyyMMdd_HHmmss")
$batchRoot = Join-Path $OutputRoot $batchId
New-Item -ItemType Directory -Force -Path $batchRoot | Out-Null

$statusPath = Join-Path $batchRoot "batch_status.json"
$statusRows = @()

foreach ($model in $models) {
    $modelStartedAt = Get-Date
    $modelOut = Join-Path $batchRoot $model
    $logPath = Join-Path $batchRoot "$model.log"
    New-Item -ItemType Directory -Force -Path $modelOut | Out-Null

    "[$($modelStartedAt.ToString("s"))] Starting model $model" | Tee-Object -FilePath $logPath
    "Output directory: $modelOut" | Tee-Object -FilePath $logPath -Append
    "RAG KB: $KbDir" | Tee-Object -FilePath $logPath -Append
    "RAG profile: $RagProfile" | Tee-Object -FilePath $logPath -Append

    $argsList = @(
        "generate_scenarios_sco.py",
        "--case-set", "paper_120",
        "--mode", "both",
        "--limit", "$Limit",
        "--llm", $model,
        "--out-dir", $modelOut
    )

    & $PythonExe @argsList *>&1 | Tee-Object -FilePath $logPath -Append
    $exitCode = $LASTEXITCODE
    $modelFinishedAt = Get-Date

    $statusRows += [ordered]@{
        model = $model
        started_at = $modelStartedAt.ToString("o")
        finished_at = $modelFinishedAt.ToString("o")
        exit_code = $exitCode
        output_dir = $modelOut
        log_path = $logPath
    }

    [ordered]@{
        batch_id = $batchId
        started_at = $startedAt.ToString("o")
        updated_at = (Get-Date).ToString("o")
        output_root = $batchRoot
        case_set = "paper_120"
        mode = "both"
        limit = $Limit
        rag_kb_dir = $KbDir
        rag_profile = $RagProfile
        models = $statusRows
    } | ConvertTo-Json -Depth 8 | Set-Content -Path $statusPath -Encoding UTF8

    "[$($modelFinishedAt.ToString("s"))] Finished model $model with exit code $exitCode" | Tee-Object -FilePath $logPath -Append
}

[ordered]@{
    batch_id = $batchId
    started_at = $startedAt.ToString("o")
    finished_at = (Get-Date).ToString("o")
    output_root = $batchRoot
    case_set = "paper_120"
    mode = "both"
    limit = $Limit
    rag_kb_dir = $KbDir
    rag_profile = $RagProfile
    models = $statusRows
} | ConvertTo-Json -Depth 8 | Set-Content -Path $statusPath -Encoding UTF8

Write-Host "Batch complete: $batchRoot"
