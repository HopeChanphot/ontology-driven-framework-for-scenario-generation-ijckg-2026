[CmdletBinding()]
param(
    [string]$EngineRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$OntologyPath = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "ontology\ontology\personashield-psq-sco-v9.1.owl"),
    [string]$Python = "",
    [string[]]$Models = @("qwen2_5_7b", "qwen3_8b", "mistral_7b"),
    [string]$RunRoot = "",
    [int]$CaseLimit = 0,
    [switch]$DryRun,
    [switch]$SkipRag
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$experimentName = "paper120_mode4_graph_walk_v1"
$conditionLabel = "C4-Walk: ontology-to-text RAG with deterministic greedy relation walk"
$expectedCaseCount = if ($CaseLimit -gt 0) { [Math]::Min($CaseLimit, 120) } else { 120 }
$ontologyTextDocLimit = 5
$walkDepth = 2

function Write-JsonFile {
    param(
        [Parameter(Mandatory = $true)]$Value,
        [Parameter(Mandatory = $true)][string]$Path
    )
    $Value | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Get-Sha256OrNull {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Get-PropertyValue {
    param(
        $Object,
        [Parameter(Mandatory = $true)][string]$Name
    )
    if ($null -eq $Object) {
        return $null
    }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }
    return $property.Value
}

function Test-PythonExecutable {
    param([string]$Candidate)
    if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) {
        return $false
    }
    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = "SilentlyContinue"
        & $Candidate -c "import sys; raise SystemExit(0)" *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $previousErrorAction
    }
}

function Get-GraphWalkVerification {
    param(
        [Parameter(Mandatory = $true)][string]$ScenarioPath,
        [Parameter(Mandatory = $true)][string]$Model,
        [Parameter(Mandatory = $true)][int]$ExpectedRows,
        [Parameter(Mandatory = $true)][bool]$RequireLive
    )

    if (-not (Test-Path -LiteralPath $ScenarioPath -PathType Leaf)) {
        throw "Expected scenario output was not created: $ScenarioPath"
    }

    $rows = @(
        Get-Content -LiteralPath $ScenarioPath |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            ForEach-Object { $_ | ConvertFrom-Json }
    )

    $missingWalk = [System.Collections.Generic.List[string]]::new()
    $wrongCaseSet = [System.Collections.Generic.List[string]]::new()
    $wrongDocumentCount = [System.Collections.Generic.List[string]]::new()
    $scenarioTraceMissing = [System.Collections.Generic.List[string]]::new()
    $walkRows = 0
    $scenarioTraceRows = 0
    $promptMetadataWalkRows = 0
    $schemaSafeRepairRows = 0
    $validationPassedRows = 0
    $liveRows = 0
    $externalRagRows = 0

    foreach ($row in $rows) {
        $caseObject = Get-PropertyValue -Object $row -Name "case"
        $caseId = [string](Get-PropertyValue -Object $caseObject -Name "case_id")
        if ([string](Get-PropertyValue -Object $caseObject -Name "case_set_id") -ne "psq_sco_paper_120") {
            $wrongCaseSet.Add($caseId)
        }

        $scenarioObject = Get-PropertyValue -Object $row -Name "scenario"
        $generationMeta = Get-PropertyValue -Object $scenarioObject -Name "generation_meta"
        $ontologyTextTrace = Get-PropertyValue -Object $generationMeta -Name "ontology_text_trace"
        $scenarioDocuments = @()
        if ($null -ne $ontologyTextTrace) {
            $scenarioDocuments = @(Get-PropertyValue -Object $ontologyTextTrace -Name "documents")
            $scenarioTraceRows += 1
        } else {
            $scenarioTraceMissing.Add($caseId)
        }

        $promptMetadata = Get-PropertyValue -Object $row -Name "prompt_metadata"
        $promptDocumentTypes = @(Get-PropertyValue -Object $promptMetadata -Name "ontology_text_document_types")
        $promptStrategies = @(Get-PropertyValue -Object $promptMetadata -Name "ontology_text_graph_strategy")
        $promptDocumentCountValue = Get-PropertyValue -Object $promptMetadata -Name "ontology_text_document_count"
        $promptDocumentCount = if ($null -eq $promptDocumentCountValue) { 0 } else { [int]$promptDocumentCountValue }

        $scenarioWalkDocuments = @(
            $scenarioDocuments | Where-Object {
                $_.document_type -eq "selected_subgraph_walk" -and
                $_.graph_text_strategy -eq "deterministic_random_walk_graph_to_text"
            }
        )
        $promptHasWalk = (
            $promptDocumentTypes -contains "selected_subgraph_walk" -and
            $promptStrategies -contains "deterministic_random_walk_graph_to_text"
        )
        if ($promptHasWalk) {
            $promptMetadataWalkRows += 1
        }
        if ($scenarioWalkDocuments.Count -gt 0 -or $promptHasWalk) {
            $walkRows += 1
        } else {
            $missingWalk.Add($caseId)
        }

        $observedDocumentCount = if ($scenarioDocuments.Count -gt 0) { $scenarioDocuments.Count } else { $promptDocumentCount }
        if ($observedDocumentCount -ne 5) {
            $wrongDocumentCount.Add("$caseId=$observedDocumentCount")
        }

        if ($null -ne (Get-PropertyValue -Object $generationMeta -Name "repair_note")) {
            $schemaSafeRepairRows += 1
        }
        if ((Get-PropertyValue -Object $row -Name "validation_passed") -eq $true) {
            $validationPassedRows += 1
        }
        if ((Get-PropertyValue -Object $row -Name "used_live_llm") -eq $true) {
            $liveRows += 1
        }
        $externalCountValue = Get-PropertyValue -Object $promptMetadata -Name "external_rag_example_count"
        if ($null -ne $externalCountValue -and [int]$externalCountValue -gt 0) {
            $externalRagRows += 1
        }
    }

    $errors = [System.Collections.Generic.List[string]]::new()
    $warnings = [System.Collections.Generic.List[string]]::new()
    if ($rows.Count -ne $ExpectedRows) {
        $errors.Add("Expected $ExpectedRows rows but found $($rows.Count).")
    }
    if ($missingWalk.Count -gt 0) {
        $errors.Add("Graph-walk document missing from $($missingWalk.Count) rows.")
    }
    if ($wrongCaseSet.Count -gt 0) {
        $errors.Add("Frozen paper case-set ID missing from $($wrongCaseSet.Count) rows.")
    }
    if ($wrongDocumentCount.Count -gt 0) {
        $errors.Add("Expected exactly five ontology-text documents in every row; $($wrongDocumentCount.Count) rows differ.")
    }
    if ($RequireLive -and $liveRows -ne $ExpectedRows) {
        $errors.Add("Live LLM output required for all rows, but only $liveRows of $ExpectedRows rows are live.")
    }
    if ($scenarioTraceMissing.Count -gt 0) {
        $warnings.Add("Scenario-level ontology trace is absent from $($scenarioTraceMissing.Count) rows; prompt metadata is used to verify graph-walk exposure for those rows.")
    }
    if ($schemaSafeRepairRows -gt 0) {
        $warnings.Add("$schemaSafeRepairRows rows contain the engine's schema-safe repair fallback after a live response failed ScenarioContent validation.")
    }
    $validationFailedRows = $rows.Count - $validationPassedRows
    if ($validationFailedRows -gt 0) {
        $warnings.Add("$validationFailedRows rows failed one or more post-generation quality rules; retain them for transparent evaluation or rerun them under a separately declared recovery policy.")
    }
    if ($externalRagRows -lt $rows.Count) {
        $warnings.Add("External RAG returned at least one example for $externalRagRows of $($rows.Count) rows; ontology graph-walk context was still present in all verified graph-walk rows.")
    }

    return [ordered]@{
        model = $Model
        scenario_file = $ScenarioPath
        scenario_file_sha256 = Get-Sha256OrNull -Path $ScenarioPath
        expected_rows = $ExpectedRows
        observed_rows = $rows.Count
        graph_walk_rows = $walkRows
        graph_walk_coverage = if ($rows.Count -gt 0) { $walkRows / $rows.Count } else { 0.0 }
        prompt_metadata_graph_walk_rows = $promptMetadataWalkRows
        scenario_level_ontology_trace_rows = $scenarioTraceRows
        scenario_level_ontology_trace_missing_rows = $scenarioTraceMissing.Count
        schema_safe_repair_rows = $schemaSafeRepairRows
        validation_passed_rows = $validationPassedRows
        validation_failed_rows = $validationFailedRows
        frozen_case_set_rows = $rows.Count - $wrongCaseSet.Count
        five_document_rows = $rows.Count - $wrongDocumentCount.Count
        live_llm_rows = $liveRows
        external_rag_present_rows = $externalRagRows
        verification_passed = ($errors.Count -eq 0)
        errors = @($errors)
        warnings = @($warnings)
        missing_walk_case_ids = @($missingWalk)
        wrong_case_set_case_ids = @($wrongCaseSet)
        wrong_document_counts = @($wrongDocumentCount)
        scenario_trace_missing_case_ids = @($scenarioTraceMissing)
    }
}

$engineRootResolved = (Resolve-Path -LiteralPath $EngineRoot).Path
$generatorPath = Join-Path $engineRootResolved "generate_scenarios_sco.py"
$caseConfigPath = Join-Path $engineRootResolved "configs\psq_sco_paper_120_cases.json"
$ontologyTextCodePath = Join-Path $engineRootResolved "psq_sco_generation\ontology_text.py"
$engineCodePath = Join-Path $engineRootResolved "psq_sco_generation\engine.py"

foreach ($requiredPath in @($generatorPath, $caseConfigPath, $ontologyTextCodePath, $engineCodePath, $OntologyPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required experiment input does not exist: $requiredPath"
    }
}

if ([string]::IsNullOrWhiteSpace($Python)) {
    $pythonCandidates = @(
        (Join-Path $engineRootResolved ".venv\Scripts\python.exe"),
        (Join-Path $engineRootResolved "venv\Scripts\python.exe"),
        (Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe")
    )
    $pythonExe = $pythonCandidates | Where-Object { Test-PythonExecutable -Candidate $_ } | Select-Object -First 1
    if (-not $pythonExe) {
        $pythonCommand = Get-Command "python" -ErrorAction Stop
        $pythonExe = $pythonCommand.Source
    }
} else {
    $pythonCommand = Get-Command $Python -ErrorAction Stop
    $pythonExe = $pythonCommand.Source
    if (-not (Test-PythonExecutable -Candidate $pythonExe)) {
        throw "The selected Python executable cannot start: $pythonExe"
    }
}

$pythonPathEntries = @(
    (Join-Path $engineRootResolved "venv\Lib\site-packages"),
    (Join-Path $engineRootResolved ".venv\Lib\site-packages"),
    (Join-Path $engineRootResolved ".codex_pydeps")
) | Where-Object { Test-Path -LiteralPath $_ -PathType Container }
if (-not [string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
    $pythonPathEntries += $env:PYTHONPATH
}
$env:PYTHONPATH = $pythonPathEntries -join [System.IO.Path]::PathSeparator

$requiredImports = @("pydantic", "requests")
if (-not $SkipRag) {
    $requiredImports += "chromadb"
}
$importStatement = ($requiredImports | ForEach-Object { "import $_" }) -join "; "
& $pythonExe -c $importStatement
if ($LASTEXITCODE -ne 0) {
    throw "Python preflight failed. Required modules: $($requiredImports -join ', '). Use -Python with a compatible interpreter or repair the repository environment."
}

if ([string]::IsNullOrWhiteSpace($RunRoot)) {
    $runId = Get-Date -Format "yyyyMMdd_HHmmss"
    $RunRoot = Join-Path $engineRootResolved "output\experiments\$experimentName\$runId"
} else {
    $RunRoot = [System.IO.Path]::GetFullPath($RunRoot)
    $runId = Split-Path -Leaf $RunRoot
}
New-Item -ItemType Directory -Path $RunRoot -Force | Out-Null

$manifestPath = Join-Path $RunRoot "experiment_manifest.json"
$combinedScenarioPath = Join-Path $RunRoot "scenarios_mode4_graph_walk_all_models.jsonl"
$startedAt = (Get-Date).ToString("o")

$manifest = [ordered]@{
    experiment_name = $experimentName
    condition_label = $conditionLabel
    run_id = $runId
    run_root = $RunRoot
    status = "running"
    started_at = $startedAt
    completed_at = $null
    design = [ordered]@{
        generation_mode = "ontology_text_rag"
        experiment_variant = "graph_walk_v1"
        case_set = "paper_120"
        case_set_id = "psq_sco_paper_120"
        expected_cases_per_model = $expectedCaseCount
        ontology_text_document_limit = $ontologyTextDocLimit
        required_document_types = @(
            "scenario_template",
            "validation_rule",
            "evidence_source",
            "graph_cot_trace",
            "selected_subgraph_walk"
        )
        graph_walk_algorithm = "deterministic greedy relevance walk"
        graph_walk_legacy_metadata_label = "deterministic_random_walk_graph_to_text"
        graph_walk_depth = $walkDepth
        randomness_in_walk = "none"
    }
    frozen_inputs = [ordered]@{
        case_config_path = $caseConfigPath
        case_config_sha256 = Get-Sha256OrNull -Path $caseConfigPath
        ontology_path = $OntologyPath
        ontology_sha256 = Get-Sha256OrNull -Path $OntologyPath
        ontology_text_code_path = $ontologyTextCodePath
        ontology_text_code_sha256 = Get-Sha256OrNull -Path $ontologyTextCodePath
        engine_code_path = $engineCodePath
        engine_code_sha256 = Get-Sha256OrNull -Path $engineCodePath
    }
    generation_settings = [ordered]@{
        models = @($Models)
        n_rag_examples = 1
        ontology_text_doc_limit = $ontologyTextDocLimit
        llm_timeout_seconds = 1200
        llm_max_tokens = 1800
        llm_context_tokens = 4096
        llm_temperature = 0.2
        llm_parse_retries = 2
        compact_generation_prompt = $true
        require_live_llm = (-not $DryRun)
        dry_run = [bool]$DryRun
        skip_rag = [bool]$SkipRag
        case_limit = $CaseLimit
        python_executable = $pythonExe
        python_path_entries = @($pythonPathEntries)
    }
    model_runs = @()
    combined_scenario_file = $combinedScenarioPath
    combined_scenario_file_sha256 = $null
    total_rows = 0
    total_graph_walk_rows = 0
    error = $null
}
Write-JsonFile -Value $manifest -Path $manifestPath

$combinedLines = [System.Collections.Generic.List[string]]::new()

try {
    Push-Location $engineRootResolved
    try {
        foreach ($model in $Models) {
            $modelRunDir = Join-Path $RunRoot $model
            New-Item -ItemType Directory -Path $modelRunDir -Force | Out-Null

            $arguments = @(
                $generatorPath,
                "--case-set", "paper_120",
                "--limit", [string]$CaseLimit,
                "--mode", "ontology_text_rag",
                "--llm", $model,
                "--ontology-path", $OntologyPath,
                "--n-rag-examples", "1",
                "--ontology-text-doc-limit", [string]$ontologyTextDocLimit,
                "--llm-timeout", "1200",
                "--llm-max-tokens", "1800",
                "--llm-num-ctx", "4096",
                "--llm-temperature", "0.2",
                "--llm-parse-retries", "2",
                "--progress-heartbeat-seconds", "30",
                "--compact-generation-prompt",
                "--resume-dir", $modelRunDir
            )
            if ($DryRun) {
                $arguments += "--dry-run"
            } else {
                $arguments += "--require-live-llm"
            }
            if ($SkipRag) {
                $arguments += "--skip-rag"
            }

            Write-Host "Starting $conditionLabel for $model ($expectedCaseCount frozen cases)." -ForegroundColor Cyan
            & $pythonExe @arguments
            if ($LASTEXITCODE -ne 0) {
                throw "Generation command failed for $model with exit code $LASTEXITCODE. Resume with -RunRoot '$RunRoot'."
            }

            $scenarioPath = Join-Path $modelRunDir "scenarios_ontology_text_rag.jsonl"
            $verification = Get-GraphWalkVerification `
                -ScenarioPath $scenarioPath `
                -Model $model `
                -ExpectedRows $expectedCaseCount `
                -RequireLive (-not $DryRun)

            $verificationPath = Join-Path $modelRunDir "graph_walk_verification.json"
            Write-JsonFile -Value $verification -Path $verificationPath
            if (-not $verification.verification_passed) {
                throw "Graph-walk verification failed for $model. See $verificationPath"
            }

            Get-Content -LiteralPath $scenarioPath | ForEach-Object {
                if (-not [string]::IsNullOrWhiteSpace($_)) {
                    $combinedLines.Add($_)
                }
            }
            $manifest.model_runs += $verification
            $manifest.total_rows += [int]$verification.observed_rows
            $manifest.total_graph_walk_rows += [int]$verification.graph_walk_rows
            Write-JsonFile -Value $manifest -Path $manifestPath
        }
    } finally {
        Pop-Location
    }

    [System.IO.File]::WriteAllLines($combinedScenarioPath, $combinedLines, [System.Text.UTF8Encoding]::new($false))
    $manifest.combined_scenario_file_sha256 = Get-Sha256OrNull -Path $combinedScenarioPath
    $manifest.status = "complete"
    $manifest.completed_at = (Get-Date).ToString("o")
    Write-JsonFile -Value $manifest -Path $manifestPath

    Write-Host "Experiment complete: $RunRoot" -ForegroundColor Green
    Write-Host "Verified graph-walk coverage: $($manifest.total_graph_walk_rows)/$($manifest.total_rows)" -ForegroundColor Green
    Write-Host "Combined scenarios: $combinedScenarioPath" -ForegroundColor Green
} catch {
    $manifest.status = "failed"
    $manifest.completed_at = (Get-Date).ToString("o")
    $manifest.error = $_.Exception.Message
    Write-JsonFile -Value $manifest -Path $manifestPath
    throw
}
